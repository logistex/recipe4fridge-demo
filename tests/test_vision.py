import io
import os

import pytest
from PIL import Image

from conftest import make_image_bytes
from core import config
from core.errors import AppError
from core.vision import (
    extract_json,
    normalize_ingredients,
    parse_result,
    prepare_image,
    preprocess_image,
    recognize_ingredients,
)

VALID = '{"ingredients": [{"name": "달걀", "quantity": 6, "unit": "개", "category": "유제품·달걀", "confidence": "high"}], "is_food_image": true, "notes": null}'


# --- extract_json -------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        VALID,
        f"```json\n{VALID}\n```",
        f"```\n{VALID}\n```",
        f"사진을 분석했습니다.\n{VALID}\n참고하세요.",
    ],
)
def test_extract_json_handles_fences_and_prose(text):
    assert extract_json(text)["ingredients"][0]["name"] == "달걀"


@pytest.mark.parametrize("text", ["", "재료가 없습니다", "[1, 2]", "{깨진 json"])
def test_extract_json_rejects_non_objects(text):
    with pytest.raises(ValueError):
        extract_json(text)


# --- normalize_ingredients ----------------------------------------------------

def test_normalize_merges_same_name_and_sums_quantity():
    items = [
        {"name": "달걀", "quantity": 4, "unit": "개", "category": "유제품·달걀", "confidence": "high"},
        {"name": " 달 걀 ", "quantity": 2, "unit": "개", "category": "유제품·달걀", "confidence": "low"},
    ]
    [egg] = normalize_ingredients(items)
    assert (egg.name, egg.quantity, egg.unit, egg.confidence) == ("달걀", 6, "개", "high")


def test_normalize_fixes_invalid_values():
    items = [
        {"name": "  대파  ", "quantity": "약간", "unit": "", "category": "야채", "confidence": "sure"},
        {"name": "우유", "quantity": "2병", "unit": "병", "category": "유제품·달걀", "confidence": "medium"},
        {"name": "", "quantity": 1},
        "문자열 항목",
        {"name": "버터", "quantity": -1, "category": "유제품·달걀"},
        {"name": "물", "quantity": True},
    ]
    result = {i.name: i for i in normalize_ingredients(items)}
    assert set(result) == {"대파", "우유", "버터", "물"}
    assert result["대파"].quantity is None and result["대파"].unit is None
    assert result["대파"].category == "채소"  # 잘못된 분류("야채")는 사전 값으로 바로잡힘
    assert result["대파"].confidence == "low"
    assert result["우유"].quantity == 2
    assert result["버터"].quantity is None
    assert result["물"].quantity is None


def test_normalize_keeps_quantity_when_units_differ():
    items = [
        {"name": "우유", "quantity": 1, "unit": "병", "category": "기타", "confidence": "medium"},
        {"name": "우유", "quantity": 500, "unit": "ml", "category": "유제품·달걀", "confidence": "medium"},
    ]
    [milk] = normalize_ingredients(items)
    assert (milk.quantity, milk.unit, milk.category) == (1, "병", "유제품·달걀")


def test_parse_result_infers_is_food_when_missing():
    ingredients, is_food, notes = parse_result({"ingredients": []})
    assert ingredients == [] and is_food is False and notes is None


def test_parse_result_requires_ingredients_list():
    with pytest.raises((KeyError, ValueError)):
        parse_result({"items": []})
    with pytest.raises(ValueError):
        parse_result({"ingredients": "달걀"})


# --- preprocess_image ---------------------------------------------------------

def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def test_preprocess_resizes_long_edge_and_outputs_jpeg():
    out = _open(preprocess_image(make_image_bytes("PNG", size=(3000, 1500))))
    assert out.format == "JPEG"
    assert out.size == (config.MAX_IMAGE_EDGE, config.MAX_IMAGE_EDGE // 2)


def test_prepare_image_reports_conversion():
    data = make_image_bytes("PNG", size=(3000, 1500))
    p = prepare_image(data)
    assert (p.original_width, p.original_height, p.original_bytes) == (3000, 1500, len(data))
    assert (p.width, p.height) == _open(p.jpeg).size


def _noise_photo() -> bytes:
    # 무작위 잡음 사진은 JPEG로 잘 압축되지 않아 용량 줄이기 동작을 확인하기 좋다
    noise = Image.frombytes("RGB", (2000, 1500), os.urandom(2000 * 1500 * 3))
    out = io.BytesIO()
    noise.save(out, "JPEG", quality=95)
    return out.getvalue()


def test_detailed_photo_fits_target_size():
    p = prepare_image(_noise_photo())
    assert len(p.jpeg) <= config.TARGET_IMAGE_BYTES
    assert max(p.width, p.height) <= config.MAX_IMAGE_EDGE


def test_shrinks_dimensions_when_quality_alone_is_not_enough(monkeypatch):
    monkeypatch.setattr(config, "TARGET_IMAGE_BYTES", 120 * 1024)
    p = prepare_image(_noise_photo())
    assert config.MIN_IMAGE_EDGE <= max(p.width, p.height) < config.MAX_IMAGE_EDGE
    assert len(p.jpeg) <= 120 * 1024 or max(p.width, p.height) == config.MIN_IMAGE_EDGE


def test_stops_at_minimum_edge(monkeypatch):
    monkeypatch.setattr(config, "TARGET_IMAGE_BYTES", 1024)  # 도달할 수 없는 목표
    p = prepare_image(_noise_photo())
    assert max(p.width, p.height) == config.MIN_IMAGE_EDGE


def test_preprocess_keeps_small_image_size():
    assert _open(preprocess_image(make_image_bytes("WEBP", size=(400, 300)))).size == (400, 300)


def test_preprocess_applies_orientation_and_strips_exif():
    exif = Image.Exif()
    exif[0x0112] = 6  # 90도 회전해서 보라는 표시
    exif[0x010F] = "TestCamera"
    data = make_image_bytes("JPEG", size=(200, 100), exif=exif)
    out = _open(preprocess_image(data))
    assert out.size == (100, 200)
    assert len(out.getexif()) == 0


def test_preprocess_flattens_transparency_on_white():
    data = make_image_bytes("PNG", size=(10, 10), color=(0, 0, 0, 0), mode="RGBA")
    out = _open(preprocess_image(data)).convert("RGB")
    assert out.getpixel((5, 5))[0] > 240


@pytest.mark.parametrize("data", [b"not an image", make_image_bytes("GIF"), b""])
def test_preprocess_rejects_invalid_images(data):
    with pytest.raises(AppError) as exc:
        preprocess_image(data)
    assert exc.value.code == "INVALID_IMAGE"


def test_preprocess_rejects_too_large():
    with pytest.raises(AppError) as exc:
        preprocess_image(b"0" * (config.MAX_UPLOAD_MB * 1024 * 1024 + 1))
    assert exc.value.code == "IMAGE_TOO_LARGE"


# --- recognize_ingredients ----------------------------------------------------

class FakeClient:
    """chat_with_fallback은 answer_model이 응답한 것처럼 동작한다."""

    def __init__(self, contents, answer_model=None):
        self.contents = list(contents)
        self.answer_model = answer_model
        self.payloads = []
        self.model_lists = []

    def _respond(self, payload):
        self.payloads.append(payload)
        return {"model": "provider-name", "choices": [{"message": {"content": self.contents.pop(0)}}]}

    def chat(self, payload, *, deadline_seconds, on_retry=None, retry_delays=None, attempt_timeout=None, log=None):
        if log is not None:
            log.append({"model": payload["model"], "outcome": 200, "seconds": 1.0, "limit": 30})
        return self._respond(payload)

    def chat_with_fallback(self, build_payload, models, *, deadline_seconds, log=None, **kwargs):
        self.model_lists.append(list(models))
        model = self.answer_model or models[0]
        if log is not None:
            log.append({"model": model, "outcome": 200, "seconds": 1.0, "limit": 60})
        return model, self._respond(build_payload(model))


def test_recognize_builds_vision_payload(png_bytes):
    client = FakeClient([f"```json\n{VALID}\n```"])
    result = recognize_ingredients(png_bytes, client=client, model="m")
    assert [i.name for i in result.ingredients] == ["달걀"]
    assert result.model == "m" and result.is_food_image is True and result.fallback_used is False

    payload = client.payloads[0]
    assert payload["model"] == "m"
    assert payload["response_format"] == {"type": "json_object"}
    image_part = payload["messages"][1]["content"][1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_recognize_retries_once_on_unparseable_response(png_bytes):
    client = FakeClient(["죄송합니다, 형식을 못 맞췄어요", VALID])
    result = recognize_ingredients(png_bytes, client=client, model="m")
    assert len(client.payloads) == 2
    assert result.ingredients[0].name == "달걀"


def test_recognize_gives_parse_failed_after_two_bad_responses(png_bytes):
    client = FakeClient(["엉망", '{"items": []}'])
    with pytest.raises(AppError) as exc:
        recognize_ingredients(png_bytes, client=client, model="m")
    assert exc.value.code == "PARSE_FAILED"
    assert len(client.payloads) == 2


def test_recognize_passes_fallbacks_and_marks_fallback_result(png_bytes):
    client = FakeClient([VALID], answer_model="fb2")
    result = recognize_ingredients(
        png_bytes, client=client, model="m", fallback_models=["fb1", "fb2"], supports_json=lambda m: m == "m"
    )
    assert client.model_lists == [["m", "fb1", "fb2"]]
    assert result.model == "fb2" and result.fallback_used is True
    assert "response_format" not in client.payloads[0]  # fb2는 JSON 모드를 지원하지 않음


def test_parse_retry_goes_to_the_model_that_answered(png_bytes):
    client = FakeClient(["엉망", VALID], answer_model="fb1")
    result = recognize_ingredients(png_bytes, client=client, model="m", fallback_models=["fb1"])
    assert len(client.model_lists) == 1  # 기본 모델부터 다시 시작하지 않음
    assert [p["model"] for p in client.payloads] == ["fb1", "fb1"]
    assert result.model == "fb1"


def test_attempts_are_reported_on_success_and_unreadable_marked(png_bytes):
    client = FakeClient(["엉망", VALID], answer_model="fb1")
    result = recognize_ingredients(png_bytes, client=client, model="m", fallback_models=["fb1"])
    assert [a["outcome"] for a in result.attempts] == ["unreadable", 200]


def test_attempts_are_attached_to_failure(png_bytes):
    client = FakeClient(["엉망", "또 엉망"])
    with pytest.raises(AppError) as exc:
        recognize_ingredients(png_bytes, client=client, model="m")
    assert [a["outcome"] for a in exc.value.attempts] == ["unreadable", "unreadable"]


def test_recognize_rejects_invalid_image_before_calling_model():
    client = FakeClient([VALID])
    with pytest.raises(AppError):
        recognize_ingredients(b"not an image", client=client, model="m")
    assert client.payloads == []
