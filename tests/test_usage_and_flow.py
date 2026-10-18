import math
from datetime import datetime, timedelta, timezone

import pytest

from core.errors import AppError
from core.fridge_flow import confirmed_from_rows, init_rows, new_row, rename_row, request_recognition, row_flag
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


def test_init_rows_keep_quantity_and_give_stable_ids():
    rows = init_rows(fake_result(("달걀", "우유")).to_dict(), "abcd1234")
    assert [r["id"] for r in rows] == ["abcd1234-0", "abcd1234-1"]
    assert rows[0] | {"id": None} == {
        "id": None, "name": "달걀", "quantity": 1, "unit": "개", "category": "기타", "low": True, "original_name": "달걀",
    }


def test_row_flag_low_confidence_clears_when_name_is_edited():
    row = init_rows(fake_result(("김치",)).to_dict(), "p")[0]
    assert row_flag(row) == "low"
    rename_row(row, "배추김치")
    assert row_flag(row) == ""
    assert row["category"] == "반찬·가공식품"  # 이름을 고치면 사전으로 분류도 다시 정함


def test_row_flag_suspicious_name_until_fixed():
    row = init_rows(fake_result(("달strand",)).to_dict(), "p")[0]
    assert row_flag(row) == "name"
    rename_row(row, "달걀")
    assert row_flag(row) == "" and row["category"] == "유제품·달걀"


def test_rename_keeps_category_for_unknown_names():
    row = init_rows(fake_result(("버터",)).to_dict(), "p")[0]
    row["category"] = "유제품·달걀"
    rename_row(row, "무염 발효 버터밀크")
    assert row["category"] == "유제품·달걀"


def test_new_row_uses_dictionary_category():
    assert new_row("x", " 고등어 ", 2.0, " 마리 ") == {
        "id": "x", "name": "고등어", "quantity": 2.0, "unit": "마리", "category": "해산물", "low": False,
        "original_name": "고등어",
    }
    assert new_row("y", "브리오슈", None, "")["category"] == "기타"


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
