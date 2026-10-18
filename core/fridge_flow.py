"""1단계 화면 흐름: 같은 사진은 다시 인식하지 않고, 요청 한도를 확인한 뒤 모델을 부른다.

Streamlit은 위젯을 조작할 때마다 스크립트 전체를 다시 실행하므로,
모델 호출은 이 함수를 거쳐서만 일어나게 한다(PRD F1-11).
"""

import hashlib
from collections.abc import Callable, MutableMapping

from core.errors import AppError
from core.ingredient_names import category_for, is_suspicious_name
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


def init_rows(result: dict, prefix: str) -> list[dict]:
    """인식 결과를 화면에서 한 줄씩 고칠 수 있는 행으로 바꾼다. id는 위젯 key에 쓰인다."""
    return [
        {
            "id": f"{prefix}-{i}",
            "name": ing["name"],
            "quantity": ing["quantity"],
            "unit": ing["unit"],
            "category": ing["category"],
            "low": ing["confidence"] == "low",
            "original_name": ing["name"],
        }
        for i, ing in enumerate(result["ingredients"])
    ]


def new_row(row_id: str, name: str, quantity, unit: str | None) -> dict:
    name = name.strip()
    return {
        "id": row_id,
        "name": name,
        "quantity": quantity,
        "unit": (unit or "").strip() or None,
        "category": category_for(name) or "기타",
        "low": False,
        "original_name": name,
    }


def rename_row(row: dict, name: str) -> None:
    """이름을 고치면 사전으로 분류를 다시 정한다(사전에 없으면 기존 분류 유지)."""
    if name != row["name"]:
        row["name"] = name
        row["category"] = category_for(name.strip()) or row["category"]


def row_flag(row: dict) -> str:
    """"name": 이름이 깨진 것 같음, "low": 사진에서 확실하지 않음(이름을 고치면 사라짐), "": 문제 없음."""
    name = (row.get("name") or "").strip()
    if name and is_suspicious_name(name):
        return "name"
    if row.get("low") and name == row.get("original_name"):
        return "low"
    return ""


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
