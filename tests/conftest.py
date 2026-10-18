import io

import pytest
from PIL import Image


def make_image_bytes(fmt: str = "PNG", size=(64, 48), color=(200, 30, 30), mode: str = "RGB", exif=None) -> bytes:
    img = Image.new(mode, size, color)
    out = io.BytesIO()
    if exif is not None:
        img.save(out, fmt, exif=exif)
    else:
        img.save(out, fmt)
    return out.getvalue()


@pytest.fixture
def png_bytes() -> bytes:
    return make_image_bytes()
