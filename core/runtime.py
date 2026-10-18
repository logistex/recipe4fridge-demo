"""여러 세션이 함께 쓰는 객체(클라이언트, 하루 사용량 카운터, 모델 목록)."""

import logging

import streamlit as st

from core import config
from core.openrouter import OpenRouterClient
from core.usage import DailyLimiter

log = logging.getLogger(__name__)


@st.cache_resource(show_spinner=False)
def get_client(api_key: str) -> OpenRouterClient:
    return OpenRouterClient(api_key)


@st.cache_resource(show_spinner=False)
def get_daily_limiter() -> DailyLimiter:
    return DailyLimiter(config.daily_request_limit())


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def _free_vision_catalog(api_key: str) -> dict[str, set[str]]:
    return get_client(api_key).free_vision_models()  # 실패하면 예외가 나서 캐시에 남지 않는다


def vision_model_plan(api_key: str) -> tuple[str, list[str], dict[str, set[str]] | None]:
    """(기본 모델, 지금 쓸 수 있는 예비 모델들, 무료 비전 모델 목록 또는 None)."""
    try:
        catalog = _free_vision_catalog(api_key)
    except Exception as e:
        log.warning("모델 목록 조회 실패, 설정된 예비 모델을 그대로 씀: %s", type(e).__name__)
        catalog = None
    primary = config.vision_model()
    fallbacks = [m for m in config.fallback_vision_models() if m != primary and (catalog is None or m in catalog)]
    return primary, fallbacks, catalog


def supports_json_mode(catalog: dict[str, set[str]] | None, model: str) -> bool:
    if catalog is None:
        return model == config.DEFAULT_VISION_MODEL  # 목록을 못 받았으면 확인된 기본 모델에만 쓴다
    return "response_format" in catalog.get(model, set())
