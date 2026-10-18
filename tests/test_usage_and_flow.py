import math
from datetime import datetime, timedelta, timezone

import pytest

from core.errors import AppError
from core.fridge_flow import confirmed_from_rows, request_recognition, to_editor_rows
from core.usage import DailyLimiter, check_session_rate
from core.vision import Ingredient, RecognitionResult


def test_daily_limiter_caps_and_resets_next_utc_day():
    now = [datetime(2026, 10, 18, 23, 0, tzinfo=timezone.utc)]
    limiter = DailyLimiter(2, now=lambda: now[0])
    assert limiter.try_acquire() and limiter.try_acquire()
    assert not limiter.try_acquire()
    assert limiter.remaining() == 0
    now[0] += timedelta(hours=2)
    assert limiter.remaining() == 2
    assert limiter.try_acquire()


def test_session_rate_allows_n_per_minute():
    state, t = {}, [0.0]
    clock = lambda: t[0]
    assert all(check_session_rate(state, 3, now=clock) for _ in range(3))
    assert not check_session_rate(state, 3, now=clock)
    t[0] = 61
    assert check_session_rate(state, 3, now=clock)


def fake_result(names=("달걀",)) -> RecognitionResult:
    return RecognitionResult(
        ingredients=[Ingredient(n, 1, "개", "기타", "low") for n in names],
        is_food_image=True,
        notes=None,
        model="m",
        elapsed_ms=1,
    )


class Counter:
    def __init__(self):
        self.calls = 0

    def __call__(self, data):
        self.calls += 1
        return fake_result()


def test_same_image_is_not_recognized_twice():
    state, recognize = {}, Counter()
    limiter = DailyLimiter(10)
    first = request_recognition(state, b"img", recognize=recognize, limiter=limiter, per_minute=3)
    second = request_recognition(state, b"img", recognize=recognize, limiter=limiter, per_minute=3)
    assert recognize.calls == 1
    assert first["result"] == second["result"]
    assert limiter.remaining() == 9


def test_daily_limit_blocks_before_calling_model():
    state, recognize = {}, Counter()
    with pytest.raises(AppError) as exc:
        request_recognition(state, b"img", recognize=recognize, limiter=DailyLimiter(0), per_minute=3)
    assert exc.value.code == "DAILY_LIMIT"
    assert recognize.calls == 0


def test_session_rate_limit_blocks_before_calling_model():
    state, recognize = {}, Counter()
    limiter = DailyLimiter(10)
    for i in range(3):
        request_recognition(state, f"img{i}".encode(), recognize=recognize, limiter=limiter, per_minute=3)
    with pytest.raises(AppError) as exc:
        request_recognition(state, b"img-new", recognize=recognize, limiter=limiter, per_minute=3)
    assert exc.value.code == "RATE_LIMITED"
    assert recognize.calls == 3


def test_editor_rows_mark_low_confidence():
    rows = to_editor_rows(fake_result().to_dict())
    assert rows == [{"name": "달걀", "quantity": 1, "unit": "개", "category": "기타", "check": "⚠ 확인 필요"}]


def test_editor_rows_mark_suspicious_names_separately():
    result = fake_result(("달strand",)).to_dict()
    result["ingredients"][0]["name_suspect"] = True
    assert to_editor_rows(result)[0]["check"] == "⚠ 이름 확인"


def test_confirmed_rows_skip_blank_names_and_clean_values():
    rows = [
        {"name": " 달걀 ", "quantity": 6.0, "unit": "개", "category": "유제품·달걀", "check": ""},
        {"name": "대파", "quantity": math.nan, "unit": math.nan, "category": None, "check": None},
        {"name": "", "quantity": 1, "unit": "개", "category": "기타"},
        {"name": None, "quantity": None, "unit": None, "category": None},
        {"name": "버터", "quantity": None, "unit": "  ", "category": "유제품·달걀"},
    ]
    assert confirmed_from_rows(rows) == [
        {"name": "달걀", "quantity": 6.0, "unit": "개", "category": "유제품·달걀"},
        {"name": "대파", "quantity": None, "unit": None, "category": "기타"},
        {"name": "버터", "quantity": None, "unit": None, "category": "유제품·달걀"},
    ]
