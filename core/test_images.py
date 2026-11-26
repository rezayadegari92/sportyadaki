"""WebP conversion: the converter, the model field, the bulk command, the admin page and action."""
import shutil
import tempfile
from io import BytesIO, StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageOps

from articles.models import Article
from catalog.models import CarBrand, Product, ProductCategory, ProductImage

from . import image_jobs
from .image_service import convert_stored_images, stats
from .images import convert_to_webp
from .models import HeroBanner, SiteSettings

TEST_CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    'jobs': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'test-jobs'},
}


def make(fmt='PNG', size=(100, 60), mode='RGB', color='red', **save):
    buffer = BytesIO()
    Image.new(mode, size, color).save(buffer, fmt, **save)
    buffer.seek(0)
    return buffer


def opened(converted):
    return Image.open(BytesIO(converted.content.read()))


class ConverterTests(TestCase):
    def test_resizes_to_max_width_keeping_ratio(self):
        out = convert_to_webp(make(size=(400, 200)), max_width=100)
        self.assertEqual((out.width, out.height), (100, 50))
        self.assertEqual(opened(out).format, 'WEBP')

    def test_never_upscales(self):
        out = convert_to_webp(make(size=(80, 40)), max_width=1600)
        self.assertEqual((out.width, out.height), (80, 40))

    def test_keeps_transparency(self):
        image = opened(convert_to_webp(make(mode='RGBA', color=(255, 0, 0, 0))))
        self.assertEqual(image.mode, 'RGBA')
        self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_palette_with_transparency_and_cmyk(self):
        palette = Image.new('RGBA', (10, 10), (0, 255, 0, 0)).convert('P')
        buffer = BytesIO()
        palette.save(buffer, 'PNG', transparency=0)
        self.assertEqual(opened(convert_to_webp(buffer)).mode, 'RGBA')
        cmyk = make('JPEG', mode='CMYK', color=(0, 255, 255, 0))
        self.assertEqual(opened(convert_to_webp(cmyk)).mode, 'RGB')

    def test_applies_exif_rotation(self):
        buffer = BytesIO()
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90 degrees clockwise to display
        Image.new('RGB', (200, 100), 'blue').save(buffer, 'JPEG', exif=exif)
        out = convert_to_webp(buffer, max_width=1600)
        self.assertEqual((out.width, out.height), (100, 200))

    def test_big_jpeg_is_decoded_at_a_reduced_scale(self):
        decoded = []
        real_transpose = ImageOps.exif_transpose

        def spy(img):
            decoded.append(img.size)
            return real_transpose(img)

        with mock.patch('core.images.ImageOps.exif_transpose', side_effect=spy):
            out = convert_to_webp(make('JPEG', size=(4000, 1000)), max_width=900)
        self.assertEqual(decoded, [(1000, 250)])  # 1/4 scale: the smallest that is still >= 900 wide
        self.assertEqual((out.width, out.height), (900, 225))

    def test_rotated_jpeg_draft_keeps_the_upright_width(self):
        buffer = BytesIO()
        exif = Image.Exif()
        exif[0x0112] = 6
        Image.new('RGB', (4000, 2000), 'blue').save(buffer, 'JPEG', exif=exif)
        out = convert_to_webp(buffer, max_width=900)
        self.assertEqual((out.width, out.height), (900, 1800))  # stored height 2000 becomes the width

    def test_small_webp_is_skipped_but_a_big_one_is_shrunk(self):
        self.assertIsNone(convert_to_webp(make('WEBP', size=(100, 50)), max_width=200))
        self.assertEqual(convert_to_webp(make('WEBP', size=(400, 100)), max_width=200).width, 200)

    def test_animation_is_left_alone(self):
        buffer = BytesIO()
        frames = [Image.new('RGB', (20, 20), c) for c in ('red', 'blue')]
        frames[0].save(buffer, 'GIF', save_all=True, append_images=frames[1:])
        self.assertIsNone(convert_to_webp(buffer))

    def test_name_gets_webp_extension(self):
        self.assertEqual(convert_to_webp(make(), name='a/b/photo.final.png').content.name, 'photo.final.webp')


@override_settings(IMAGE_MAX_WIDTH=1600, CACHES=TEST_CACHES)
class MediaTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # remembered thumbnails point into another test's MEDIA_ROOT
        self.media = tempfile.mkdtemp()
        patcher = override_settings(MEDIA_ROOT=self.media)
        patcher.enable()
        self.addCleanup(patcher.disable)
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        self.storage = ProductCategory._meta.get_field('image').storage
        # FileSystemStorage reads MEDIA_ROOT lazily through its settings-changed handler
        self.assertEqual(str(self.storage.location), self.media)

    def legacy_category(self, name='categories/old.png', **save):
        """A row saved the old way: the file is stored as is, bypassing the field."""
        self.storage.save(name, ContentFile(make(**save).read()))
        return ProductCategory.objects.create(name='فیلتر', slug=f'c{ProductCategory.objects.count()}', image=name)


class FieldTests(MediaTestCase):
    def test_upload_is_stored_as_webp_only(self):
        upload = SimpleUploadedFile('pic.png', make(size=(3000, 1000)).read(), content_type='image/png')
        banner = HeroBanner.objects.create(title='بنر', background_image=upload)
        self.assertTrue(banner.background_image.name.endswith('.webp'))
        self.assertEqual(Image.open(banner.background_image.path).width, 1920)  # per-field override
        self.assertEqual(self.storage.listdir('banners')[1], [banner.background_image.name.split('/')[-1]])

    def test_every_admin_upload_field_converts(self):
        jpeg = make('JPEG', size=(2000, 1000)).read()
        product = Product.objects.create(name='لنت', slug='lent', image=SimpleUploadedFile('a.jpg', jpeg))
        gallery = ProductImage.objects.create(product=product, image=SimpleUploadedFile('b.jpg', jpeg))
        article = Article.objects.create(title='مقاله', slug='a', body='x',
                                         featured_image=SimpleUploadedFile('c.jpg', jpeg))
        brand = CarBrand.objects.create(name='سایپا', slug='saipa', image=SimpleUploadedFile('d.png', make().read()))
        settings_row = SiteSettings.load()
        settings_row.logo = SimpleUploadedFile('logo.png', make(mode='RGBA', color=(0, 0, 0, 0)).read())
        settings_row.save()
        for file in (product.image, gallery.image, article.featured_image, brand.image, settings_row.logo):
            self.assertTrue(file.name.endswith('.webp'), file.name)
        self.assertEqual(Image.open(product.image.path).width, 1600)
        self.assertEqual(Image.open(settings_row.logo.path).mode, 'RGBA')

    def test_garbage_upload_does_not_crash_the_field(self):
        category = ProductCategory.objects.create(name='x', slug='x', image=SimpleUploadedFile('x.png', b'junk'))
        self.assertTrue(category.image.name.endswith('.png'))

    def test_excluded_fields_keep_their_format(self):
        with override_settings(IMAGE_WEBP_EXCLUDE=['core.SiteSettings.logo']):
            row = SiteSettings.load()
            row.logo = SimpleUploadedFile('f.png', make().read())
            row.save()
        self.assertTrue(row.logo.name.endswith('.png'))


class BulkTests(MediaTestCase):
    def test_converts_updates_path_and_deletes_old_file(self):
        category = self.legacy_category(size=(200, 100))
        summary = convert_stored_images()
        category.refresh_from_db()
        self.assertEqual((summary.converted, summary.failed), (1, 0))
        self.assertTrue(category.image.name.endswith('.webp'))
        self.assertTrue(self.storage.exists(category.image.name))
        self.assertFalse(self.storage.exists('categories/old.png'))

    def test_second_run_changes_nothing(self):
        self.legacy_category()
        convert_stored_images()
        again = convert_stored_images()
        self.assertEqual((again.converted, again.failed), (0, 0))

    def test_dry_run_and_keep_originals(self):
        category = self.legacy_category(size=(300, 300))
        self.assertEqual(convert_stored_images(dry_run=True).converted, 1)
        category.refresh_from_db()
        self.assertTrue(category.image.name.endswith('.png'))
        convert_stored_images(keep_originals=True)
        self.assertTrue(self.storage.exists('categories/old.png'))

    def test_broken_and_missing_files_do_not_stop_the_run(self):
        self.storage.save('categories/bad.png', ContentFile(b'junk'))
        ProductCategory.objects.create(name='خراب', slug='bad', image='categories/bad.png')
        ProductCategory.objects.create(name='گم', slug='gone', image='categories/gone.png')
        good = self.legacy_category()
        summary = convert_stored_images()
        self.assertEqual((summary.converted, summary.failed), (1, 2))
        good.refresh_from_db()
        self.assertTrue(good.image.name.endswith('.webp'))

    def test_shared_file_is_kept_until_every_row_moved(self):
        first = self.legacy_category()
        ProductCategory.objects.create(name='دو', slug='two', image=first.image.name)
        convert_stored_images()
        self.assertEqual(ProductCategory.objects.filter(image__iendswith='.png').count(), 0)
        self.assertFalse(self.storage.exists('categories/old.png'))

    def test_stats_counts_only_non_webp(self):
        self.legacy_category()
        self.assertEqual(stats()['count'], 1)
        convert_stored_images()
        self.assertEqual(stats()['count'], 0)


class CommandTests(MediaTestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command('convert_images_to_webp', *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_dry_run_reports_savings_without_changes(self):
        self.legacy_category(size=(500, 500))
        self.assertIn('Would convert: 1', self.run_command('--dry-run'))
        self.assertTrue(self.storage.exists('categories/old.png'))

    def test_model_filter_quality_and_width(self):
        category = self.legacy_category(size=(400, 200))
        self.run_command('--model', 'articles.Article')
        self.assertTrue(self.storage.exists('categories/old.png'))
        self.run_command('--model', 'catalog.ProductCategory', '--quality', '50', '--max-width', '100')
        category.refresh_from_db()
        self.assertEqual(Image.open(category.image.path).width, 100)

    def test_bad_arguments(self):
        for args in (['--model', 'nope.Nope'], ['--quality', '0'], ['--max-width', '-5']):
            with self.subTest(args=args), self.assertRaises(CommandError):
                self.run_command(*args)


class AdminTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        self.admin_user = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'x')
        self.client.force_login(self.admin_user)
        self.url = reverse('admin:convert_images')

    def test_only_superusers(self):
        staff = get_user_model().objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {'step': 'run'}).status_code, 403)

    def test_page_shows_stats_then_asks_for_confirmation_then_runs(self):
        self.legacy_category()
        self.assertContains(self.client.get(self.url), 'تصاویر غیر WebP')
        confirm = self.client.post(self.url, {'step': 'confirm'})
        self.assertContains(confirm, 'برگشت‌پذیر نیست')
        self.assertEqual(ProductCategory.objects.filter(image__iendswith='.png').count(), 1)  # nothing ran yet

        class Inline:  # run the thread's work in the request instead
            def __init__(self, target, args, **kw):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        # Inline, the job's close_old_connections() would close the test's own connection.
        with (
            mock.patch.object(image_jobs.threading, 'Thread', Inline),
            mock.patch.object(image_jobs, 'close_old_connections'),
        ):
            self.client.post(self.url, {'step': 'run'})
        self.assertEqual(ProductCategory.objects.filter(image__iendswith='.webp').count(), 1)
        page = self.client.get(self.url)
        self.assertTrue(any('تبدیل شد' in str(m) for m in get_messages(page.wsgi_request)))
        self.assertNotContains(self.client.get(self.url), 'تبدیل شد')  # reported once

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin_user)
        self.assertEqual(client.post(self.url, {'step': 'run'}).status_code, 403)

    def test_dashboard_links_to_the_page(self):
        self.assertContains(self.client.get(reverse('admin:index')), self.url)

    def test_admin_action_converts_selected_rows_and_their_gallery(self):
        product = Product.objects.create(name='لنت', slug='lent', image='products/main.png')
        self.storage.save('products/main.png', ContentFile(make().read()))
        self.storage.save('products/g.png', ContentFile(make().read()))
        ProductImage.objects.create(product=product, image='products/g.png')
        other = self.legacy_category()
        response = self.client.post(
            reverse('admin:catalog_product_changelist'),
            {'action': 'convert_selected_images', '_selected_action': [product.pk]},
            follow=True,
        )
        self.assertContains(response, 'تبدیل شد')
        product.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(product.image.name.endswith('.webp'))
        self.assertTrue(product.gallery.get().image.name.endswith('.webp'))
        self.assertTrue(other.image.name.endswith('.png'))

    def test_every_admin_with_images_has_the_action(self):
        from django.contrib import admin

        from .admin_images import convert_selected_images

        for model in (Product, ProductCategory, CarBrand, HeroBanner, SiteSettings, Article):
            with self.subTest(model=model.__name__):
                self.assertIn(convert_selected_images, admin.site._registry[model].actions)


class ThumbnailTests(MediaTestCase):
    def stored(self, name='products/2026/11/big.webp', size=(1600, 800), fmt='WEBP'):
        return self.storage.save(name, ContentFile(make(fmt, size=size).read()))

    def test_srcset_uses_small_copies(self):
        from .thumbnails import image_attrs

        product = Product.objects.create(name='لنت', slug='lent', image=self.stored())
        attrs = str(image_attrs(product.image, 'card'))
        self.assertIn('320w', attrs)
        self.assertIn('640w', attrs)
        self.assertIn('sizes="(min-width: 600px) 260px, 50vw"', attrs)
        self.assertNotIn(product.image.url, attrs)  # the 1600px upload itself is never sent
        copies = self.storage.listdir('cache/thumbs/320')[1]
        self.assertEqual(len(copies), 1)
        self.assertEqual(Image.open(self.storage.path(f'cache/thumbs/320/{copies[0]}')).width, 320)

    def test_small_webp_is_served_as_is(self):
        from .thumbnails import image_attrs

        product = Product.objects.create(name='لنت', slug='lent', image=self.stored(size=(200, 100)))
        attrs = str(image_attrs(product.image, 'card'))
        self.assertIn(f'src="{product.image.url}"', attrs)
        self.assertIn('200w', attrs)
        self.assertFalse(self.storage.exists('cache/thumbs'))

    def test_copies_are_reused_and_remembered(self):
        from .thumbnails import thumbnail

        product = Product.objects.create(name='لنت', slug='lent', image=self.stored())
        first = thumbnail(product.image, 320)
        with mock.patch('core.thumbnails.convert_to_webp') as convert:
            self.assertEqual(thumbnail(product.image, 320), first)
            from django.core.cache import cache

            cache.clear()  # e.g. after a restart: the file on disk is found again, nothing is rebuilt
            self.assertEqual(thumbnail(product.image, 320), first)
        convert.assert_not_called()

    def test_missing_file_falls_back_to_its_url(self):
        from .thumbnails import image_attrs, thumbnail_url

        product = Product(name='لنت', slug='lent', image='products/gone.jpg')
        self.assertEqual(str(image_attrs(product.image, 'card')), f'src="{product.image.url}"')
        self.assertEqual(thumbnail_url(product.image, 200), product.image.url)

    def test_pages_use_the_copies(self):
        product = Product.objects.create(name='لنت', slug='lent', status='publish', image=self.stored())
        ProductImage.objects.create(product=product, image=self.stored('products/2026/11/g.png', fmt='PNG'))
        page = self.client.get(product.get_absolute_url()).content.decode()
        self.assertIn('/media/cache/thumbs/640/', page)
        self.assertIn('/media/cache/thumbs/160/', page)


class MainImageFromGalleryTests(MediaTestCase):
    def test_first_gallery_photo_becomes_the_main_image(self):
        product = Product.objects.create(name='لنت', slug='lent')
        first = ProductImage.objects.create(product=product, image=SimpleUploadedFile('a.png', make().read()))
        ProductImage.objects.create(product=product, image=SimpleUploadedFile('b.png', make().read()))
        product.refresh_from_db()
        self.assertEqual(product.image.name, first.image.name)

    def test_an_existing_main_image_is_kept(self):
        product = Product.objects.create(name='لنت', slug='lent', image=SimpleUploadedFile('m.png', make().read()))
        main = product.image.name
        ProductImage.objects.create(product=product, image=SimpleUploadedFile('a.png', make().read()))
        product.refresh_from_db()
        self.assertEqual(product.image.name, main)

    def test_clearing_the_main_image_falls_back_to_the_gallery(self):
        product = Product.objects.create(name='لنت', slug='lent', image=SimpleUploadedFile('m.png', make().read()))
        photo = ProductImage.objects.create(product=product, image=SimpleUploadedFile('a.png', make().read()),
                                            position=1)
        product.image = ''
        product.save()
        self.assertEqual(product.image.name, photo.image.name)

    def test_admin_list_shows_the_photo_for_a_gallery_only_product(self):
        admin_user = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'x')
        self.client.force_login(admin_user)
        product = Product.objects.create(name='لنت', slug='lent')
        ProductImage.objects.create(product=product, image=SimpleUploadedFile('a.png', make(size=(900, 600)).read()))
        page = self.client.get(reverse('admin:catalog_product_changelist')).content.decode()
        self.assertIn('/media/cache/thumbs/200/', page)
