from datetime import timedelta

import pytest
from sqlalchemy import select

from core import auth
from core.db import login_attempts, profiles, saved_recipes, sessions, users, utcnow
from core.errors import MESSAGES, AppError
from core.passwords import hash_password, password_problem, username_problem, verify_password


def sign_up(engine, username="cook_kim", password="abcd1234", nickname="김요리"):
    return auth.sign_up(engine, username, password, password, nickname)


# --- 규칙과 해시 -----------------------------------------------------------------------

@pytest.mark.parametrize("name", ["abc", "a" * 21, "kim-cook", "김요리", "cook kim", ""])
def test_bad_usernames(name):
    assert username_problem(name)


@pytest.mark.parametrize("name", ["abcd", "Cook_Kim1", "a" * 20])
def test_good_usernames(name):
    assert username_problem(name) is None


@pytest.mark.parametrize("pw", ["short1", "onlyletters", "12345678", "a1" * 33])
def test_bad_passwords(pw):
    assert password_problem(pw)


def test_password_same_as_username_rejected():
    assert password_problem("cookkim12", "CookKim12")


def test_hash_is_argon2_and_verifies():
    h = hash_password("abcd1234")
    assert h.startswith("$argon2id$") and "abcd1234" not in h
    assert verify_password(h, "abcd1234") and not verify_password(h, "abcd12345")
    assert not verify_password(None, "abcd1234") and not verify_password("not-a-hash", "x")


# --- 가입과 로그인 ----------------------------------------------------------------------

def test_sign_up_stores_hash_and_profile(engine):
    user_id = sign_up(engine, username="Cook_Kim")
    with engine.connect() as c:
        row = c.execute(select(users).where(users.c.id == user_id)).mappings().one()
        prof = c.execute(select(profiles).where(profiles.c.user_id == user_id)).mappings().one()
    assert row["username"] == "cook_kim"  # 소문자로 저장
    assert row["password_hash"].startswith("$argon2id$")
    assert prof["nickname"] == "김요리"


@pytest.mark.parametrize(
    "args,needle",
    [
        (("ab", "abcd1234", "abcd1234", "김요리"), "아이디는"),
        (("cook_kim", "abc", "abc", "김요리"), "8~64자"),
        (("cook_kim", "abcd1234", "abcd9999", "김요리"), "확인이 일치하지"),
        (("cook_kim", "abcd1234", "abcd1234", "김"), "닉네임"),
    ],
)
def test_sign_up_validation(engine, args, needle):
    with pytest.raises(AppError) as exc:
        auth.sign_up(engine, *args)
    assert exc.value.code == "INVALID_INPUT" and needle in exc.value.message


def test_duplicate_username_is_case_insensitive(engine):
    sign_up(engine, username="cook_kim")
    with pytest.raises(AppError) as exc:
        sign_up(engine, username="COOK_KIM")
    assert exc.value.code == "USERNAME_TAKEN"


def test_log_in_success_and_same_message_for_unknown_user_or_wrong_password(engine):
    user_id = sign_up(engine)
    assert auth.log_in(engine, "Cook_Kim", "abcd1234") == user_id
    errors = []
    for username, pw in [("cook_kim", "wrong1234"), ("nobody_here", "abcd1234")]:
        with pytest.raises(AppError) as exc:
            auth.log_in(engine, username, pw)
        errors.append((exc.value.code, exc.value.message))
    assert errors[0] == errors[1] == ("LOGIN_FAILED", MESSAGES["LOGIN_FAILED"])


def test_lockout_after_five_failures_and_unlock_after_15_minutes(engine):
    sign_up(engine)
    t0 = utcnow()
    for i in range(5):
        with pytest.raises(AppError):
            auth.log_in(engine, "cook_kim", "wrong1234", now=t0 + timedelta(seconds=i))
    with pytest.raises(AppError) as exc:  # 맞는 비밀번호여도 막힘
        auth.log_in(engine, "cook_kim", "abcd1234", now=t0 + timedelta(minutes=1))
    assert exc.value.code == "LOGIN_LOCKED"
    assert auth.log_in(engine, "cook_kim", "abcd1234", now=t0 + timedelta(minutes=16))
    with engine.connect() as c:  # 성공하면 실패 기록을 지운다
        assert c.execute(select(login_attempts)).all() == []


def test_failed_attempts_are_recorded_in_db_not_session(engine):
    sign_up(engine)
    with pytest.raises(AppError):
        auth.log_in(engine, "cook_kim", "wrong1234")
    with engine.connect() as c:
        assert [r.username for r in c.execute(select(login_attempts))] == ["cook_kim"]


# --- 세션 ------------------------------------------------------------------------------

def test_session_token_is_stored_hashed_and_expires(engine):
    user_id = sign_up(engine)
    t0 = utcnow()
    token = auth.create_session(engine, user_id, now=t0)
    with engine.connect() as c:
        stored = c.execute(select(sessions.c.token_hash)).scalar_one()
    assert stored != token and len(stored) == 64
    assert auth.user_id_from_session(engine, token, now=t0 + timedelta(days=13)) == user_id
    assert auth.user_id_from_session(engine, token, now=t0 + timedelta(days=15)) is None
    assert auth.user_id_from_session(engine, "made-up-token") is None
    auth.delete_session(engine, token)
    assert auth.user_id_from_session(engine, token) is None


def test_change_password_keeps_only_current_session(engine):
    user_id = sign_up(engine)
    here, other = auth.create_session(engine, user_id), auth.create_session(engine, user_id)
    with pytest.raises(AppError) as exc:
        auth.change_password(engine, user_id, "wrong1234", "newpass99", "newpass99", here)
    assert exc.value.code == "WRONG_PASSWORD"
    with pytest.raises(AppError):
        auth.change_password(engine, user_id, "abcd1234", "short", "short", here)
    auth.change_password(engine, user_id, "abcd1234", "newpass99", "newpass99", here)
    assert auth.log_in(engine, "cook_kim", "newpass99") == user_id
    assert auth.user_id_from_session(engine, here) == user_id
    assert auth.user_id_from_session(engine, other) is None


# --- Google ----------------------------------------------------------------------------

def test_google_user_is_created_once_and_not_merged_with_password_account(engine):
    password_user = sign_up(engine)
    g1 = auth.google_user(engine, "sub-123", "kim@example.com", "김구글")
    g2 = auth.google_user(engine, "sub-123", "kim@example.com", "김구글")
    assert g1 == g2 != password_user
    user = auth.load_user(engine, g1)
    assert (user.method, user.nickname, user.email, user.method_label) == ("google", "김구글", "kim@example.com", "Google")


def test_google_nickname_falls_back_to_email_and_minimum_length(engine):
    assert auth.load_user(engine, auth.google_user(engine, "s1", "chef@example.com", None)).nickname == "chef"
    assert auth.load_user(engine, auth.google_user(engine, "s2", None, "김")).nickname == "김님"


# --- 계정 삭제 --------------------------------------------------------------------------

def test_delete_password_account_requires_password_and_cascades(engine):
    user_id = sign_up(engine)
    auth.create_session(engine, user_id)
    with pytest.raises(AppError):
        auth.delete_account(engine, user_id, password="wrong1234")
    auth.delete_account(engine, user_id, password="abcd1234")
    with engine.connect() as c:
        for table in (users, profiles, sessions, saved_recipes):
            assert c.execute(select(table)).all() == []


def test_delete_google_account_requires_confirm_text(engine):
    user_id = auth.google_user(engine, "sub-1", "a@b.c", "구글이")
    with pytest.raises(AppError):
        auth.delete_account(engine, user_id, confirm_text="네")
    auth.delete_account(engine, user_id, confirm_text="삭제")
    assert auth.load_user(engine, user_id) is None
