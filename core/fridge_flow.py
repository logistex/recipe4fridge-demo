"""1단계 화면 흐름: 같은 사진은 다시 인식하지 않고, 요청 한도를 확인한 뒤 모델을 부른다.

Streamlit은 위젯을 조작할 때마다 스크립트 전체를 다시 실행하므로,
모델 호출은 이 함수를 거쳐서만 일어나게 한다(PRD F1-11).
"""

import hashlib
from collections.abc import Callable, MutableMapping

from core.errors import AppError
from core.usage import DailyLimiter, check_session_rate
from core.vision import RecognitionResult

CACHE_SIZE = 5


def image_digest(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def request_recognition(
    state: MutableMapping,
    image_bytes: bytes,
    *,
    recognize: Callable[[bytes], RecognitionResult],
    limiter: DailyLimiter,
    per_minute: int,
) -> dict:
    """인식 결과(dict)를 state["recognition"]에 두고 돌려준다."""
    digest = image_digest(image_bytes)
    cache: dict = state.setdefault("recognition_cache", {})
    result = cache.get(digest)
    if result is None:
        if not check_session_rate(state, per_minute):
            raise AppError("RATE_LIMITED")
        if not limiter.try_acquire():
            raise AppError("DAILY_LIMIT")
        result = recognize(image_bytes).to_dict()
        cache[digest] = result
        while len(cache) > CACHE_SIZE:
            cache.pop(next(iter(cache)))
    state["recognition"] = {"digest": digest, "result": result}
    return state["recognition"]


def to_editor_rows(result: dict) -> list[dict]:
    return [
        {
            "name": ing["name"],
            "quantity": ing["quantity"],
            "unit": ing["unit"],
            "category": ing["category"],
            "check": "⚠ 확인 필요" if ing["confidence"] == "low" else "",
        }
        for ing in result["ingredients"]
    ]


def confirmed_from_rows(rows: list[dict]) -> list[dict]:
    """편집한 표에서 재료명이 있는 행만 2단계 입력 형태로 바꾼다."""
    confirmed = []
    for row in rows:
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        quantity = row.get("quantity")
        if quantity != quantity:  # 빈 칸은 NaN으로 온다
            quantity = None
        unit = row.get("unit")
        unit = unit.strip() if isinstance(unit, str) else ""
        confirmed.append(
            {
                "name": name.strip(),
                "quantity": quantity,
                "unit": unit or None,
                "category": row.get("category") or "기타",
            }
        )
    return confirmed
