"""Responsive images: smaller WebP copies of uploaded images, one per display width.

Pages never send the uploaded file where a smaller one will do: `{% image_src product.image 'card' %}` writes
`src`, `srcset` and `sizes` for the preset's widths, and the browser picks the copy that fits the slot and the
screen density. A copy is made the first time it is asked for, stored under media/cache/thumbs/ (served by
nginx like any media file) and remembered in the cache, so later pages cost no disk access. An image that is
already a WebP no wider than the requested width is used as it is.

The copy's name comes from the source's name, and an upload never reuses an existing name, so a replaced
image gets new copies and old ones are never served for it.
"""
import hashlib
import logging
from pathlib import PurePosixPath

from django.core.cache import cache
from django.utils.html import format_html
from PIL import Image

from .images import convert_to_webp

logger = logging.getLogger(__name__)

THUMB_DIR = 'cache/thumbs'
THUMB_QUALITY = 80
CACHE_TTL = 24 * 60 * 60

# preset -> (widths in px, `sizes` attribute). Widths are 1x and 2x of the slot the CSS gives the image.
PRESETS = {
    'card': ((320, 640), '(min-width: 600px) 260px, 50vw'),           # product cards (grid / rails)
    'detail': ((640, 1200), '(min-width: 900px) 600px, 100vw'),       # product page main image
    'gallery': ((160,), '72px'),                                       # product page thumbnails
    'cart': ((180,), '84px'),
    'hero': ((960, 1600, 1920), '100vw'),                              # banners, full width
    'article_card': ((480, 960), '(min-width: 600px) 400px, 100vw'),
    'article_cover': ((800, 1600), '(min-width: 900px) 860px, 100vw'),
    'model': ((320, 640), '(min-width: 600px) 240px, 50vw'),            # car model cards
    'logo': ((240, 480), '200px'),                                     # header logo (38px high)
    'icon': ((64,), '28px'),                                           # car picker
}


def _thumb_name(name, width):
    digest = hashlib.sha1(name.encode()).hexdigest()[:12]
    return f'{THUMB_DIR}/{width}/{digest}-{PurePosixPath(name).stem}.webp'


def thumbnail(file, width):
    """(name, width) of a copy of `file` at most `width` px wide; may be the file itself."""
    name = file.name
    key = f'thumb:{width}:{name}'
    found = cache.get(key)
    if found:
        return found
    storage = file.storage
    target = _thumb_name(name, width)
    if storage.exists(target):
        with storage.open(target) as handle:
            found = (target, Image.open(handle).width)
    else:
        with storage.open(name) as handle:
            converted = convert_to_webp(handle, max_width=width, quality=THUMB_QUALITY, name=target)
            if converted is None:  # already a WebP that is small enough
                handle.seek(0)
                found = (name, Image.open(handle).width)
        if converted is not None:
            saved = storage.save(target, converted.content)
            if saved != target:  # another worker made it meanwhile: keep theirs
                storage.delete(saved)
            found = (target, converted.width)
    cache.set(key, found, CACHE_TTL)
    return found


def thumbnail_url(file, width):
    """URL of a copy at most `width` px wide, or the file's own URL when no copy can be made."""
    try:
        name, _ = thumbnail(file, width)
    except Exception as exc:  # missing or broken file: never break a page for an image
        logger.warning('Thumbnail failed for %s: %s', file.name, exc)
        return file.url
    return file.storage.url(name)


def image_attrs(file, preset):
    """`src`, `srcset` and `sizes` attributes for an <img> showing `file` in a slot of this preset."""
    if not file:
        return ''
    widths, sizes = PRESETS[preset]
    if file.name.lower().endswith('.svg'):
        return format_html('src="{}"', file.url)
    try:
        copies = {}
        for width in widths:
            name, real_width = thumbnail(file, width)
            copies.setdefault(name, real_width)  # a small source can answer several widths
    except Exception as exc:
        logger.warning('Thumbnail failed for %s: %s', file.name, exc)
        return format_html('src="{}"', file.url)
    storage = file.storage
    first = next(iter(copies))
    srcset = ', '.join(f'{storage.url(name)} {width}w' for name, width in copies.items())
    return format_html('src="{}" srcset="{}" sizes="{}"', storage.url(first), srcset, sizes)
