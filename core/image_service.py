"""Convert images that are already stored to WebP. Shared by `convert_images_to_webp`, the admin page
(background job, `image_jobs.py`) and the per-model admin action.

One file is handled at a time and rows are read in pk-ordered chunks, so memory stays flat. A failure on
one file is recorded and the run goes on. The old file is deleted only after the new one is saved and the
row points at it, and never while another row still uses it.
"""
import logging
import posixpath
from dataclasses import dataclass, field

from django.apps import apps
from django.db.models import ImageField

from .images import convert_to_webp, field_options, is_excluded

logger = logging.getLogger(__name__)

CHUNK = 200
MAX_ERRORS = 50  # only the first ones are kept for display


@dataclass
class Summary:
    converted: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    errors: list = field(default_factory=list)

    @property
    def bytes_saved(self):
        return self.bytes_before - self.bytes_after

    def add(self, other):
        self.converted += other.converted
        self.skipped += other.skipped
        self.failed += other.failed
        self.bytes_before += other.bytes_before
        self.bytes_after += other.bytes_after
        self.errors += other.errors[:MAX_ERRORS - len(self.errors)]


@dataclass
class Target:
    """One image field plus the rows to look at."""

    model: type
    field: ImageField
    queryset: object

    @property
    def label(self):
        return f'{self.model._meta.label}.{self.field.name}'

    def pending(self):
        """Rows whose image is not WebP yet (SVG is never touched)."""
        name = self.field.name
        qs = self.queryset.exclude(**{name: ''}).exclude(**{f'{name}__isnull': True})
        for ext in ('.webp', '.svg'):
            qs = qs.exclude(**{f'{name}__iendswith': ext})
        return qs


def image_fields(model=None):
    """Convertible image fields of one model class, or of every model."""
    models = [model] if model else apps.get_models()
    for m in models:
        for f in m._meta.get_fields():
            if isinstance(f, ImageField) and not is_excluded(f):
                yield m, f


def targets(label=None, queryset=None):
    """Targets for the whole project, one model ("app.Model"), or the rows of a queryset."""
    if queryset is not None:
        return [
            Target(m, f, queryset.model._default_manager.filter(pk__in=queryset.values('pk')))
            for m, f in image_fields(queryset.model)
        ]
    model = apps.get_model(label) if label else None
    return [Target(m, f, m._default_manager.all()) for m, f in image_fields(model)]


def stats(label=None):
    """How many images are not WebP yet and how much space they take."""
    count = size = 0
    for t in targets(label):
        for _, name in t.pending().values_list('pk', t.field.name).iterator(chunk_size=CHUNK):
            count += 1
            try:
                size += t.field.storage.size(name)
            except OSError:
                pass  # file missing on disk: counted, size unknown
    return {'count': count, 'bytes': size}


def _rows(target):
    """Pending (pk, name) rows in chunks, by pk, so rows changed meanwhile never confuse the paging."""
    last = 0
    while True:
        rows = list(
            target.pending().filter(pk__gt=last).order_by('pk').values_list('pk', target.field.name)[:CHUNK]
        )
        if not rows:
            return
        yield from rows
        last = rows[-1][0]


def _still_used(name):
    return any(t.model._default_manager.filter(**{t.field.name: name}).exists() for t in targets())


def _convert_row(target, pk, name, *, quality, max_width, keep_originals, dry_run):
    """Returns (converted?, bytes before, bytes after)."""
    storage = target.field.storage
    width, qual = field_options(target.field, quality, max_width)
    with storage.open(name) as handle:
        converted = convert_to_webp(handle, max_width=width, quality=qual, name=name)
    if converted is None:
        return False, 0, 0
    before, after = storage.size(name), converted.content.size
    if dry_run:
        return True, before, after

    new_name = storage.save(posixpath.join(posixpath.dirname(name), converted.content.name), converted.content)
    updated = target.model._default_manager.filter(pk=pk, **{target.field.name: name}).update(
        **{target.field.name: new_name}
    )
    if not updated:  # the row changed while we worked: keep its new value, drop our copy
        storage.delete(new_name)
        return False, 0, 0
    if not keep_originals and not _still_used(name):
        storage.delete(name)
    return True, before, after


def convert_stored_images(
    *, label=None, queryset=None, quality=None, max_width=None, keep_originals=False, dry_run=False,
    progress=None,
):
    """Convert every non-WebP image. `progress(done, total)` is called after each file."""
    summary = Summary()
    all_targets = targets(label, queryset)
    total = sum(t.pending().count() for t in all_targets)
    done = 0
    for target in all_targets:
        for pk, name in _rows(target):
            done += 1
            try:
                converted, before, after = _convert_row(
                    target, pk, name,
                    quality=quality, max_width=max_width, keep_originals=keep_originals, dry_run=dry_run,
                )
            except Exception as exc:  # one broken or missing file must not stop the run
                summary.failed += 1
                if len(summary.errors) < MAX_ERRORS:
                    summary.errors.append(f'{target.label} #{pk} {name}: {exc}')
                logger.warning('WebP conversion failed for %s #%s %s', target.label, pk, name, exc_info=True)
            else:
                if converted:
                    summary.converted += 1
                    summary.bytes_before += before
                    summary.bytes_after += after
                else:
                    summary.skipped += 1
            if progress:
                progress(done, total)
    return summary
