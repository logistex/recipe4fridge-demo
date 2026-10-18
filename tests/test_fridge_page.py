"""Streamlit AppTest로 1단계 화면 흐름을 확인한다. 실제 모델은 부르지 않는다."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import core.config
import core.runtime
import core.vision
from conftest import make_image_bytes
from core.errors import MESSAGES, AppError
from core.runtime import get_daily_limiter
from core.vision import Ingredient, RecognitionResult

PAGE = str(Path(__file__).resolve().parent.parent / "app_pages" / "fridge.py")


class FakeRecognizer:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error
        self.calls = 0

    def __call__(self, image_bytes, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def food_result():
    return RecognitionResult(
        ingredients=[
            Ingredient("달걀", 6, "개", "유제품·달걀", "high"),
            Ingredient("김치", None, None, "반찬·가공식품", "low"),
        ],
        is_food_image=True,
        notes="아래 칸이 가려져 있어요.",
        model="fake",
        elapsed_ms=10,
    )


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(core.config, "get_api_key", lambda: "test-key")
    # 모델 목록 조회(네트워크)를 막고 고정된 계획을 쓴다
    monkeypatch.setattr(core.runtime, "vision_model_plan", lambda key: ("primary/model:free", ["fb/model:free"], None))
    get_daily_limiter.clear()


def button(at, label):
    return next(b for b in at.button if b.label == label)


def upload_and_recognize(at, png_bytes):
    at.run()
    at.file_uploader[0].upload("fridge.png", png_bytes, "image/png").run()
    button(at, "재료 인식").click().run()
    return at


def test_recognition_shows_editable_table(monkeypatch, png_bytes):
    fake = FakeRecognizer(food_result())
    monkeypatch.setattr(core.vision, "recognize_ingredients", fake)
    at = upload_and_recognize(AppTest.from_file(PAGE, default_timeout=15), png_bytes)

    assert not at.exception
    assert fake.calls == 1
    assert any("김치" in w.value for w in at.warning)  # 확인 필요 안내
    assert any("가려져" in i.value for i in at.info)  # 모델 메모
    assert [i["name"] for i in at.session_state["confirmed_ingredients"]] == ["달걀", "김치"]
    assert not button(at, "재료 인식").disabled  # 인식이 끝나면 다시 누를 수 있음
    assert not button(at, "이 재료로 레시피 찾기").disabled


def test_other_interactions_do_not_call_model_again(monkeypatch, png_bytes):
    fake = FakeRecognizer(food_result())
    monkeypatch.setattr(core.vision, "recognize_ingredients", fake)
    at = upload_and_recognize(AppTest.from_file(PAGE, default_timeout=15), png_bytes)

    button(at, "이 재료로 레시피 찾기").click().run()
    assert any("다음 단계" in i.value for i in at.info)
    at.run()
    button(at, "재료 인식").click().run()  # 같은 사진 다시 인식 → 저장된 결과 사용
    assert fake.calls == 1


def test_non_food_image_shows_retake_message(monkeypatch, png_bytes):
    fake = FakeRecognizer(RecognitionResult([], False, None, "fake", 1))
    monkeypatch.setattr(core.vision, "recognize_ingredients", fake)
    at = upload_and_recognize(AppTest.from_file(PAGE, default_timeout=15), png_bytes)

    assert any("식재료 사진이 아닌 것 같아요" in w.value for w in at.warning)
    assert button(at, "이 재료로 레시피 찾기").disabled


def test_model_error_is_shown_and_button_reenabled(monkeypatch, png_bytes):
    fake = FakeRecognizer(error=AppError("MODEL_BUSY"))
    monkeypatch.setattr(core.vision, "recognize_ingredients", fake)
    at = upload_and_recognize(AppTest.from_file(PAGE, default_timeout=15), png_bytes)

    assert any(MESSAGES["MODEL_BUSY"] in e.value for e in at.error)
    assert not button(at, "재료 인식").disabled
    assert "recognition" not in at.session_state


def test_upload_shows_automatic_shrink_info(monkeypatch):
    at = AppTest.from_file(PAGE, default_timeout=15).run()
    at.file_uploader[0].upload("big.png", make_image_bytes("PNG", size=(3000, 2000)), "image/png").run()
    caption = next(c.value for c in at.caption if "자동 변환" in c.value)
    assert "(3000×2000)" in caption and "(1024×683, JPEG)" in caption


def test_invalid_upload_is_rejected_before_recognition(monkeypatch):
    fake = FakeRecognizer(food_result())
    monkeypatch.setattr(core.vision, "recognize_ingredients", fake)
    at = AppTest.from_file(PAGE, default_timeout=15).run()
    at.file_uploader[0].upload("fake.png", b"not an image", "image/png").run()
    assert any(MESSAGES["INVALID_IMAGE"] in e.value for e in at.error)
    assert button(at, "재료 인식").disabled
    assert fake.calls == 0


def test_recognizer_gets_fallback_models_and_result_mentions_fallback(monkeypatch, png_bytes):
    seen = {}

    def fake(image_bytes, **kwargs):
        seen.update(kwargs)
        r = food_result()
        r.model, r.fallback_used = "fb/model:free", True
        return r

    monkeypatch.setattr(core.vision, "recognize_ingredients", fake)
    at = upload_and_recognize(AppTest.from_file(PAGE, default_timeout=15), png_bytes)
    assert seen["model"] == "primary/model:free"
    assert seen["fallback_models"] == ["fb/model:free"]
    assert any("예비 모델(model)" in c.value for c in at.caption)


def test_suspicious_name_gets_its_own_warning(monkeypatch, png_bytes):
    result = food_result()
    result.ingredients.append(Ingredient("달strand", 2, "개", "기타", "low", name_suspect=True))
    monkeypatch.setattr(core.vision, "recognize_ingredients", FakeRecognizer(result))
    at = upload_and_recognize(AppTest.from_file(PAGE, default_timeout=15), png_bytes)
    warnings = [w.value for w in at.warning]
    assert any("이름이 잘못 인식" in w and "달strand" in w for w in warnings)
    assert not any("확실하지 않아요" in w and "달strand" in w for w in warnings)


def test_missing_api_key_disables_recognition(monkeypatch, png_bytes):
    monkeypatch.setattr(core.config, "get_api_key", lambda: None)
    at = AppTest.from_file(PAGE, default_timeout=15).run()
    at.file_uploader[0].upload("fridge.png", png_bytes, "image/png").run()
    assert any(MESSAGES["CONFIG_ERROR"] in e.value for e in at.error)
    assert button(at, "재료 인식").disabled
