"""Convert the images already in the media library to WebP.

    python manage.py convert_images_to_webp --dry-run
    python manage.py convert_images_to_webp --model catalog.ProductImage --quality 75 --max-width 1200

Safe to run again: images that are already WebP are skipped. The old file is deleted only after the new
one is saved and the database points at it (`--keep-originals` keeps it).
"""
from django.apps import apps
from django.core.management import BaseCommand, CommandError

from core.image_service import convert_stored_images


def megabytes(n):
    return f'{n / 1024 / 1024:.2f} MB'


class Command(BaseCommand):
    help = 'Convert stored images to WebP (resize, update the database path, delete the old file).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report only; change nothing.')
        parser.add_argument('--model', help='Only this model, as app_label.Model')
        parser.add_argument('--quality', type=int, help='WebP quality 1-100 (default: settings / per field)')
        parser.add_argument('--max-width', type=int, help='Maximum width in px (default: settings / per field)')
        parser.add_argument('--keep-originals', action='store_true', help='Do not delete the old files.')

    def handle(self, *args, dry_run, model, quality, max_width, keep_originals, **options):
        if model:
            try:
                apps.get_model(model)
            except (LookupError, ValueError) as exc:
                raise CommandError(f'Unknown model {model!r}: use app_label.Model') from exc
        if quality is not None and not 1 <= quality <= 100:
            raise CommandError('--quality must be between 1 and 100')
        if max_width is not None and max_width < 1:
            raise CommandError('--max-width must be positive')

        def progress(done, total):
            if done % 25 == 0 or done == total:
                self.stdout.write(f'  {done}/{total}')

        summary = convert_stored_images(
            label=model, quality=quality, max_width=max_width, keep_originals=keep_originals,
            dry_run=dry_run, progress=progress,
        )
        for error in summary.errors:
            self.stderr.write(f'FAILED {error}')
        verb = 'Would convert' if dry_run else 'Converted'
        self.stdout.write(
            f'{verb}: {summary.converted}   skipped: {summary.skipped}   failed: {summary.failed}   '
            f'{"estimated " if dry_run else ""}saved: {megabytes(summary.bytes_saved)} '
            f'({megabytes(summary.bytes_before)} -> {megabytes(summary.bytes_after)})'
        )
