"""앱 설정과 비밀 값 로딩.

비밀 값은 st.secrets → 환경 변수 → 프로젝트 루트 .env 순서로 찾는다.
"""

import os
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_VISION_MODEL = "google/gemma-4-26b-a4b-it:free"
DEFAULT_TEXT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

# 기본 모델이 429로 막혔을 때 차례로 쓰는 무료 비전 모델. 2026-10-18 실제 호출 결과로 골랐다.
# - Nemotron 3.5 Super VL: 4.6초 응답, JSON 형식 정확 → 첫 번째 (인기 모델이지만 속도·품질 우선)
# - dots-3-note-preview: 동작하지만 실제 사진에서 50초 걸리고 재료명이 깨지거나("달strand") 형식을 어긴 적이 있음
# - Nemotron Nano Omni: 확인 시점에 NVIDIA 쪽 처리량이 차 있었음
# 제외: Gemma 4 31B(기본 모델과 같은 Google 공유 한도), Inkling 계열(에이전트 도구 전용, 403)
DEFAULT_FALLBACK_VISION_MODELS = (
    "nvidia/nemotron-3.5-super-vl:free",
    "dots-studio/dots-3-note-preview:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
)

MAX_UPLOAD_MB = 10
# 모델에 보내는 사진: 긴 변 1024px에서 시작해, 300KB 이하가 될 때까지 품질과 크기를 낮춘다
MAX_IMAGE_EDGE = 1024
MIN_IMAGE_EDGE = 640
TARGET_IMAGE_BYTES = 300 * 1024
JPEG_QUALITIES = (85, 75, 65)
CAMERA_RESOLUTION = "720p"

RETRY_DELAYS = (10,)  # 429 등 일시적 오류면 같은 모델로 한 번 더 시도
REQUEST_TIMEOUT_SECONDS = 180
VISION_ATTEMPT_TIMEOUT_SECONDS = 60  # 기본 모델 요청 하나
FALLBACK_ATTEMPT_TIMEOUT_SECONDS = 30  # 예비 모델 요청 하나. 느린 모델은 빨리 건너뛴다
VISION_DEADLINE_SECONDS = 120

RECIPE_ATTEMPT_TIMEOUT_SECONDS = 90  # 추론 모델이라 요청 하나가 길다
RECIPE_DEADLINE_SECONDS = 150
RECIPE_COUNT = 3
MAX_RECIPE_INGREDIENTS = 50

SESSION_REQUESTS_PER_MINUTE = 3
DEFAULT_DAILY_REQUEST_LIMIT = 40


@lru_cache(maxsize=1)
def _dotenv_values() -> dict[str, str]:
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip().removeprefix("export ").strip()] = value.strip().strip('"').strip("'")
    return values


def _from_secrets(name: str) -> str | None:
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # secrets.toml이 없으면 예외가 난다
        pass
    return None


def get_setting(name: str, default: str | None = None) -> str | None:
    for value in (_from_secrets(name), os.environ.get(name), _dotenv_values().get(name)):
        if value:
            return value
    return default


def get_api_key() -> str | None:
    return get_setting("OPENROUTER_API_KEY")


def vision_model() -> str:
    return get_setting("VISION_MODEL", DEFAULT_VISION_MODEL)


def text_model() -> str:
    return get_setting("TEXT_MODEL", DEFAULT_TEXT_MODEL)


def pantry_items() -> tuple[str, ...]:
    """기본 양념(부족한 재료로 세지 않음). 쉼표로 구분한 PANTRY_ITEMS 설정으로 바꿀 수 있다."""
    from core.pantry import DEFAULT_PANTRY

    value = get_setting("PANTRY_ITEMS")
    if not value:
        return DEFAULT_PANTRY
    return tuple(i.strip() for i in value.split(",") if i.strip())


def fallback_vision_models() -> tuple[str, ...]:
    """쉼표로 구분한 FALLBACK_VISION_MODELS 설정으로 바꿀 수 있다. "none"이면 예비 모델을 쓰지 않는다."""
    value = get_setting("FALLBACK_VISION_MODELS")
    if value is None:
        return DEFAULT_FALLBACK_VISION_MODELS
    if value.strip().lower() == "none":
        return ()
    return tuple(m.strip() for m in value.split(",") if m.strip())


def daily_request_limit() -> int:
    try:
        return int(get_setting("DAILY_REQUEST_LIMIT", str(DEFAULT_DAILY_REQUEST_LIMIT)))
    except ValueError:
        return DEFAULT_DAILY_REQUEST_LIMIT
