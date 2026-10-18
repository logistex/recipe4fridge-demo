"""앱 설정과 비밀 값 로딩.

비밀 값은 st.secrets → 환경 변수 → 프로젝트 루트 .env 순서로 찾는다.
"""

import os
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_VISION_MODEL = "google/gemma-4-26b-a4b-it:free"
DEFAULT_TEXT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

# 기본 모델이 429로 막혔을 때 차례로 쓰는 무료 비전 모델. 덜 붐빌 모델을 앞에 둔다.
# OpenRouter API는 모델별 인기(사용량)를 제공하지 않으므로, 2026-10-18 실제 호출 결과로 골랐다.
# - Gemma 4 31B는 기본 모델과 같은 Google 공유 한도를 써서 제외
# - Inkling 계열은 에이전트 도구 전용(403)이라 제외
# - Nemotron 3.5 Super VL은 사용량이 매우 많은 인기 모델이라 마지막에 둔다
DEFAULT_FALLBACK_VISION_MODELS = (
    "dots-studio/dots-3-note-preview:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nvidia/nemotron-3.5-super-vl:free",
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
VISION_ATTEMPT_TIMEOUT_SECONDS = 60
VISION_DEADLINE_SECONDS = 120

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
