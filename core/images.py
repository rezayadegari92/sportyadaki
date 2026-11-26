"""WebP conversion for uploaded images.

`convert_to_webp()` is the one converter (uploads, the bulk command and the admin page all use it);
`WebPImageField` applies it to every new upload just before the file is saved, so the original is never
stored. Settings (config/settings.py): IMAGE_WEBP_QUALITY, IMAGE_MAX_WIDTH, IMAGE_WEBP_FIELDS (per-field
overrides keyed "app.Model.field") and IMAGE_WEBP_EXCLUDE (fields that must keep their format).
"""
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import ImageField
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

DEFAULT_QUALITY = 80
DEFAULT_MAX_WIDTH = 1600


def default_quality():
    return getattr(settings, 'IMAGE_WEBP_QUALITY', DEFAULT_QUALITY)


def default_max_width():
    return getattr(settings, 'IMAGE_MAX_WIDTH', DEFAULT_MAX_WIDTH)


def field_key(field):
    return f'{field.model._meta.label}.{field.name}'


def is_excluded(field):
    return field_key(field) in getattr(settings, 'IMAGE_WEBP_EXCLUDE', ())


def field_options(field, quality=None, max_width=None):
    """(max_width, quality) for a field: explicit arguments, then the field's own, then settings."""
    override = getattr(settings, 'IMAGE_WEBP_FIELDS', {}).get(field_key(field), {})
    width = max_width or getattr(field, 'max_width', None) or override.get('max_width') or default_max_width()
    qual = quality or getattr(field, 'quality', None) or override.get('quality') or default_quality()
    return width, qual


@dataclass
class Converted:
    content: ContentFile
    width: int
    height: int


def _has_alpha(img):
    return img.mode in ('RGBA', 'LA', 'PA') or 'transparency' in img.info


def _to_srgb(img):
    """CMYK (print JPEGs) to RGB, through the embedded profile when there is one."""
    profile = img.info.get('icc_profile')
    if profile:
        try:
            source = ImageCms.ImageCmsProfile(BytesIO(profile))
            return ImageCms.profileToProfile(img, source, ImageCms.createProfile('sRGB'), outputMode='RGB')
        except (ImageCms.PyCMSError, OSError):
            logger.debug('Bad ICC profile; converting CMYK without it')
    return img.convert('RGB')


def convert_to_webp(source, *, max_width=None, quality=None, name='image'):
    """Convert an image file to WebP; returns `Converted`, or None to leave the file as it is.

    - the EXIF orientation is applied, the width is capped at `max_width` (never upscaled);
    - transparency is kept; palette, grayscale and CMYK images are converted to RGB(A);
    - None for a WebP that is already upright and small enough, and for animations (GIF/APNG/WebP).
    Raises UnidentifiedImageError / OSError when `source` is not an image.
    """
    max_width = max_width or default_max_width()
    quality = quality or default_quality()
    source.seek(0)
    img = Image.open(source)
    original_format = img.format
    if getattr(img, 'n_frames', 1) > 1:
        return None
    orientation = img.getexif().get(0x0112, 1)
    upright = orientation in (None, 0, 1)
    if original_format == 'JPEG':
        # Let libjpeg decode at 1/2, 1/4 or 1/8 scale while the result stays at least `max_width` wide once
        # it is upright (orientations 5-8 turn the height into the width): far less time and memory for
        # camera photos. LANCZOS below does the final resize.
        img.draft(None, (1, max_width) if orientation in (5, 6, 7, 8) else (max_width, 1))
    img = ImageOps.exif_transpose(img)  # also loads the pixels
    if original_format == 'WEBP' and upright and img.width <= max_width:
        return None

    if img.mode == 'CMYK':
        img = _to_srgb(img)
    elif _has_alpha(img):
        img = img.convert('RGBA')
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    if img.width > max_width:
        height = max(1, round(img.height * max_width / img.width))
        img = img.resize((max_width, height), Image.Resampling.LANCZOS)

    out = BytesIO()
    img.save(out, 'WEBP', quality=quality, method=4, icc_profile=img.info.get('icc_profile'))
    stem = PurePosixPath(name).stem or 'image'
    return Converted(ContentFile(out.getvalue(), name=f'{stem}.webp'), img.width, img.height)


class WebPImageField(ImageField):
    """ImageField that stores every new upload as WebP (see the module docstring).

    `max_width` / `quality` are optional per-field overrides; they are not part of the migration state.
    """

    def __init__(self, *args, max_width=None, quality=None, **kwargs):
        self.max_width = max_width
        self.quality = quality
        super().__init__(*args, **kwargs)

    def pre_save(self, model_instance, add):
        file = getattr(model_instance, self.attname)
        if file and not file._committed and not is_excluded(self):
            width, quality = field_options(self)
            try:
                converted = convert_to_webp(file.file, max_width=width, quality=quality, name=file.name)
            except (UnidentifiedImageError, OSError):
                converted = None  # not an image; form validation reports it, never lose the upload here
                logger.warning('Could not convert %s to WebP; storing it unchanged', file.name)
            if converted:
                file.file = converted.content
                file.name = converted.content.name
        return super().pre_save(model_instance, add)
