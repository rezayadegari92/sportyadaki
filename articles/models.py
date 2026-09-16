import math

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

WORDS_PER_MINUTE = 200


class ArticleCategory(models.Model):
    """WordPress post `category` — one per car manufacturer."""

    name = models.CharField('نام', max_length=200)
    slug = models.SlugField('نامک', max_length=200, unique=True, allow_unicode=True)
    description = models.TextField('توضیحات', blank=True)
    wp_term_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True, editable=False)

    class Meta:
        ordering = ['name']
        verbose_name = 'دسته‌بندی مقاله'
        verbose_name_plural = 'دسته‌بندی‌های مقاله'

    def __str__(self):
        return self.name


class ArticleQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Article.Status.PUBLISHED, published_at__lte=timezone.now())


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'پیش‌نویس'
        PUBLISHED = 'publish', 'منتشر شده'

    title = models.CharField('عنوان', max_length=255)
    slug = models.SlugField('نامک', max_length=255, unique=True, allow_unicode=True)
    category = models.ForeignKey(
        ArticleCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles', verbose_name='دسته‌بندی',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles', verbose_name='نویسنده',
    )
    excerpt = models.TextField('خلاصه', blank=True)
    body = models.TextField('متن')
    featured_image = models.ImageField('تصویر شاخص', upload_to='articles/%Y/%m/', blank=True)
    status = models.CharField('وضعیت', max_length=20, choices=Status, default=Status.DRAFT)
    published_at = models.DateTimeField('تاریخ انتشار', null=True, blank=True, db_index=True)

    wp_post_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True, editable=False)
    created_at = models.DateTimeField('تاریخ ایجاد', default=timezone.now)
    updated_at = models.DateTimeField('آخرین ویرایش', auto_now=True)

    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at']
        verbose_name = 'مقاله'
        verbose_name_plural = 'مقالات'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('articles:detail', args=[self.slug])

    @property
    def read_time_minutes(self):
        words = len(strip_tags(self.body).split())
        return max(1, math.ceil(words / WORDS_PER_MINUTE))
