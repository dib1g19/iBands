import io
import os

import pillow_avif  # noqa: F401  registers Pillow's AVIF encoder
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

_CONVERT = {".jpg", ".jpeg", ".png", ".webp"}


def convert_uploaded_images(instance, *field_names):
    """Replace a new jpg/png/webp upload with AVIF. Files already stored are left alone."""
    for name in field_names:
        field_file = getattr(instance, name, None)
        if not field_file or field_file._committed:
            continue
        ext = os.path.splitext(field_file.name or "")[1].lower()
        if ext not in _CONVERT:
            continue
        src = field_file.file
        src.seek(0)
        with Image.open(src) as im:
            buf = io.BytesIO()
            im.save(buf, format="AVIF", quality=60)
        base = os.path.splitext(os.path.basename(field_file.name))[0] or "image"
        setattr(
            instance,
            name,
            SimpleUploadedFile(f"{base}.avif", buf.getvalue(), content_type="image/avif"),
        )
