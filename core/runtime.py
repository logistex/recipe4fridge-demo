"""여러 세션이 함께 쓰는 객체(클라이언트, 하루 사용량 카운터, 모델 목록)."""

import logging
from contextlib import contextmanager

import streamlit as st
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from core import config
from core.db import init_db, make_engine
from core.errors import AppError
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


@st.cache_resource(show_spinner=False)
def _engine(url: str) -> Engine:
    engine = make_engine(url)
    init_db(engine)  # 실패하면 예외가 나서 캐시에 남지 않고, 다음 실행에서 다시 시도한다
    return engine


def get_engine() -> Engine:
    """3단계 저장소. 연결하지 못하면(Supabase 일시 정지 등) AppError("DB_UNAVAILABLE")."""
    with db_guard():
        return _engine(config.database_url())


@contextmanager
def db_guard():
    """DB 오류를 화면에 보여 줄 수 있는 AppError로 바꾼다. 원문(접속 정보가 섞일 수 있음)은 로그에만 남긴다."""
    try:
        yield
    except SQLAlchemyError as e:
        log.warning("DB 오류: %s", type(e).__name__)
        raise AppError("DB_UNAVAILABLE") from None
