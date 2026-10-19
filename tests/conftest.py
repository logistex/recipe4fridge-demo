import io

import pytest
from PIL import Image

import core.config
from core.db import init_db, make_engine


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


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    """테스트는 항상 새 메모리 DB를 쓴다. 로컬 개발 DB(data/local.db)나 Supabase에 절대 닿지 않게 한다."""
    monkeypatch.setattr(core.config, "database_url", lambda: "sqlite://")
    monkeypatch.setattr(core.config, "google_login_configured", lambda: False)
    from core.runtime import _engine

    _engine.clear()
    yield
    _engine.clear()


@pytest.fixture
def engine():
    e = make_engine("sqlite://")
    init_db(e)
    return e
