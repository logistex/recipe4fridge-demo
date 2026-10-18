"""냉장고 사진 식재료 인식: 이미지 전처리, 프롬프트, 응답 파싱과 정규화."""

import base64
import io
import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field

from PIL import Image, ImageOps, UnidentifiedImageError

from core import config
from core.errors import AppError
from core.jsonutil import extract_json, message_text
from core.ingredient_names import category_for, is_suspicious_name
from core.openrouter import FallbackCallback, OpenRouterClient, RetryCallback

CATEGORIES = ("채소", "과일", "육류", "해산물", "유제품·달걀", "곡물·면", "양념·소스", "반찬·가공식품", "음료", "기타")
CONFIDENCES = ("high", "medium", "low")
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

log = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""너는 냉장고 사진에서 식재료를 찾는 도우미다.
규칙:
- 사진에 실제로 보이는 식재료만 나열한다. 확실하지 않은 재료는 confidence를 "low"로 한다.
- 불투명한 용기나 포장처럼 내용물을 알 수 없는 것은 목록에서 빼고, notes에 언급한다.
- 재료명은 한국어 일반 명칭으로 쓴다(상표명 대신 "우유", "케첩"처럼).
- quantity는 숫자로, 알 수 없으면 null로 쓴다. unit은 "개", "단", "팩", "병", "g"처럼 쓰고, 알 수 없으면 null로 쓴다.
- category는 다음 중 하나만 쓴다: {", ".join(CATEGORIES)}
- 냉장고나 식재료 사진이 아니면 is_food_image를 false로, ingredients를 빈 배열로 한다.
- 아래 JSON 형식으로만 답하고, 다른 텍스트는 쓰지 않는다.

{{"ingredients": [{{"name": "달걀", "quantity": 6, "unit": "개", "category": "유제품·달걀", "confidence": "high"}}],
 "is_food_image": true,
 "notes": "인식에 참고할 점이 있으면 한 문장, 없으면 null"}}"""

USER_PROMPT = "이 냉장고 사진의 식재료를 JSON으로 알려 줘."


@dataclass
class Ingredient:
    name: str
    quantity: int | float | None
    unit: str | None
    category: str
    confidence: str
    name_suspect: bool = False  # 재료명에 다른 문자가 섞여 사용자가 확인해야 함


@dataclass
class RecognitionResult:
    ingredients: list[Ingredient]
    is_food_image: bool
    notes: str | None
    model: str
    elapsed_ms: int
    fallback_used: bool = False
    attempts: list[dict] = field(default_factory=list)  # 성공하기까지 보낸 요청들 (실패한 시도 포함)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PreparedImage:
    """모델에 보낼 수 있게 줄인 사진과, 화면에 보여 줄 변환 정보."""

    jpeg: bytes
    width: int
    height: int
    original_bytes: int
    original_width: int
    original_height: int


def _encode_jpeg(img: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality)  # exif를 넘기지 않으므로 메타데이터가 빠진다
    return out.getvalue()


def _shrink(img: Image.Image) -> tuple[bytes, Image.Image]:
    """긴 변 MAX_IMAGE_EDGE에서 시작해, 목표 용량 이하가 될 때까지 품질을 낮추고 그래도 크면 크기를 줄인다."""
    edge = config.MAX_IMAGE_EDGE
    while True:
        resized = img.copy()
        resized.thumbnail((edge, edge))
        for quality in config.JPEG_QUALITIES:
            data = _encode_jpeg(resized, quality)
            if len(data) <= config.TARGET_IMAGE_BYTES:
                return data, resized
        if edge <= config.MIN_IMAGE_EDGE:
            return data, resized  # 최소 크기에서도 목표를 넘으면 가장 작은 결과를 쓴다
        edge = max(int(edge * 0.8), config.MIN_IMAGE_EDGE)


def prepare_image(data: bytes) -> PreparedImage:
    """사진을 작게 줄이고 EXIF를 지운 JPEG로 다시 인코딩한다."""
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise AppError("IMAGE_TOO_LARGE")
    try:
        with Image.open(io.BytesIO(data)) as src:
            if src.format not in ALLOWED_FORMATS:
                raise AppError("INVALID_IMAGE")
            img = ImageOps.exif_transpose(src)  # 회전 정보를 먼저 반영해야 사진이 눕지 않는다
            if img.mode != "RGB":
                rgba = img.convert("RGBA")
                img = Image.new("RGB", rgba.size, "white")
                img.paste(rgba, mask=rgba.getchannel("A"))
            original_width, original_height = img.size
            jpeg, resized = _shrink(img)
            return PreparedImage(jpeg, *resized.size, len(data), original_width, original_height)
    except AppError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise AppError("INVALID_IMAGE") from None


def preprocess_image(data: bytes) -> bytes:
    return prepare_image(data).jpeg


def _clean_text(value, max_len: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_len] or None


def _to_quantity(value) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        match = re.match(r"\s*(\d+(?:\.\d+)?)", value)
        if not match:
            return None
        value = float(match.group(1))
    if not isinstance(value, (int, float)) or value < 0:
        return None
    return int(value) if float(value).is_integer() else round(float(value), 2)


def normalize_ingredients(items) -> list[Ingredient]:
    """공백 정리, 이름 검사, 사전으로 분류 바로잡기, 같은 재료 합치기, 허용되지 않은 값 바로잡기."""
    if not isinstance(items, list):
        raise ValueError("ingredients가 배열이 아님")
    rank = {c: i for i, c in enumerate(CONFIDENCES)}
    merged: dict[str, Ingredient] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name"), 30)
        if not name:
            continue
        category = category_for(name) or (item.get("category") if item.get("category") in CATEGORIES else "기타")
        confidence = item.get("confidence") if item.get("confidence") in CONFIDENCES else "low"
        suspect = is_suspicious_name(name)
        if suspect:
            confidence = "low"
        ing = Ingredient(
            name, _to_quantity(item.get("quantity")), _clean_text(item.get("unit"), 10), category, confidence, suspect
        )

        key = name.replace(" ", "")
        prev = merged.get(key)
        if prev is None:
            merged[key] = ing
            continue
        if prev.quantity is not None and ing.quantity is not None and prev.unit == ing.unit:
            prev.quantity = _to_quantity(prev.quantity + ing.quantity)
        elif prev.quantity is None:
            prev.quantity, prev.unit = ing.quantity, ing.unit
        if rank[ing.confidence] < rank[prev.confidence]:
            prev.confidence = ing.confidence
        if prev.category == "기타":
            prev.category = ing.category
    return list(merged.values())


def parse_result(data: dict) -> tuple[list[Ingredient], bool, str | None]:
    ingredients = normalize_ingredients(data["ingredients"])
    is_food = data.get("is_food_image")
    if not isinstance(is_food, bool):
        is_food = bool(ingredients)
    return ingredients, is_food, _clean_text(data.get("notes"), 300)


def build_payload(model: str, data_url: str, *, json_mode: bool) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 4096,  # 예비 모델 중 추론 모델은 보이지 않는 추론 토큰도 출력으로 센다
    }
    if json_mode:  # 지원하지 않는 모델에 보내면 처리할 제공자가 없다는 오류가 날 수 있다
        payload["response_format"] = {"type": "json_object"}
    return payload


def recognize_ingredients(
    image_bytes: bytes,
    *,
    client: OpenRouterClient,
    model: str,
    fallback_models: Sequence[str] = (),
    supports_json: Callable[[str], bool] = lambda m: True,
    on_retry: RetryCallback | None = None,
    on_fallback: FallbackCallback | None = None,
    deadline_seconds: float = config.VISION_DEADLINE_SECONDS,
) -> RecognitionResult:
    """기본 모델이 429로 막히면 한 번 더 시도하고, 그래도 안 되면 예비 모델로 넘어간다."""
    start = time.monotonic()
    jpeg = preprocess_image(image_bytes)
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")

    def payload_for(m: str) -> dict:
        return build_payload(m, data_url, json_mode=supports_json(m))

    attempts: list[dict] = []  # 화면에 "무엇을 시도했는지" 보여 주기 위한 요청 기록
    used_model = None
    try:
        for attempt in range(2):  # 응답을 해석하지 못하면 1회 다시 요청한다
            remaining = deadline_seconds - (time.monotonic() - start)
            if remaining <= 0:
                raise AppError("MODEL_TIMEOUT")
            if used_model is None:
                used_model, response = client.chat_with_fallback(
                    payload_for,
                    [model, *fallback_models],
                    deadline_seconds=remaining,
                    attempt_timeout=config.VISION_ATTEMPT_TIMEOUT_SECONDS,
                    fallback_attempt_timeout=config.FALLBACK_ATTEMPT_TIMEOUT_SECONDS,
                    on_retry=on_retry,
                    on_fallback=on_fallback,
                    log=attempts,
                )
            else:  # 다시 요청할 때는 방금 응답한 모델에 바로 보낸다
                timeout = (
                    config.VISION_ATTEMPT_TIMEOUT_SECONDS if used_model == model else config.FALLBACK_ATTEMPT_TIMEOUT_SECONDS
                )
                response = client.chat(
                    payload_for(used_model), deadline_seconds=remaining, retry_delays=(), attempt_timeout=timeout,
                    log=attempts,
                )
            try:
                ingredients, is_food, notes = parse_result(extract_json(message_text(response)))
                break
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                log.warning("인식 응답 파싱 실패 (모델 %s, 시도 %d)", used_model, attempt + 1)
                if attempts:
                    attempts[-1]["outcome"] = "unreadable"
        else:
            raise AppError("PARSE_FAILED")
    except AppError as e:
        e.attempts = attempts
        raise

    return RecognitionResult(
        ingredients=ingredients,
        is_food_image=is_food,
        notes=notes,
        model=used_model,
        elapsed_ms=int((time.monotonic() - start) * 1000),
        fallback_used=used_model != model,
        attempts=attempts,
    )
