"""계정: 아이디·비밀번호 가입과 로그인, 세션 토큰, Google 계정 (PRD 3단계 5.1~5.3).

Streamlit에 의존하지 않는다. 쿠키와 st.user는 core/session.py가 다룬다.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from core.db import login_attempts, profiles, sessions, users, utcnow
from core.errors import AppError
from core.passwords import hash_password, normalize_username, password_problem, username_problem, verify_password

SESSION_DAYS = 14
MAX_FAILURES = 5
LOCK_MINUTES = 15


@dataclass
class User:
    id: int
    nickname: str
    method: str  # "password" | "google"
    username: str | None = None
    email: str | None = None

    @property
    def method_label(self) -> str:
        return "Google" if self.method == "google" else "아이디"


def nickname_problem(nickname: str) -> str | None:
    if not 2 <= len((nickname or "").strip()) <= 20:
        return "닉네임은 2~20자로 정해 주세요."
    return None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def load_user(engine: Engine, user_id: int) -> User | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(users.c.id, users.c.username, users.c.google_sub, users.c.email, profiles.c.nickname)
            .join(profiles, profiles.c.user_id == users.c.id)
            .where(users.c.id == user_id)
        ).first()
    if row is None:
        return None
    method = "google" if row.google_sub and not row.username else "password"
    return User(row.id, row.nickname, method, row.username, row.email)


# --- 아이디·비밀번호 ------------------------------------------------------------------

def sign_up(engine: Engine, username: str, password: str, password_confirm: str, nickname: str) -> int:
    username = normalize_username(username)
    problem = username_problem(username) or password_problem(password, username) or nickname_problem(nickname)
    if not problem and password != password_confirm:
        problem = "비밀번호 확인이 일치하지 않아요."
    if problem:
        raise AppError("INVALID_INPUT", problem)
    try:
        with engine.begin() as conn:
            user_id = conn.execute(
                insert(users).values(username=username, password_hash=hash_password(password))
            ).inserted_primary_key[0]
            conn.execute(insert(profiles).values(user_id=user_id, nickname=nickname.strip()))
    except IntegrityError:
        raise AppError("USERNAME_TAKEN") from None
    return user_id


def log_in(engine: Engine, username: str, password: str, now: datetime | None = None) -> int:
    """성공하면 user_id. 실패 문구는 아이디가 없든 비밀번호가 틀리든 같다(F3-4)."""
    now = now or utcnow()
    username = normalize_username(username)
    with engine.begin() as conn:
        conn.execute(delete(login_attempts).where(login_attempts.c.attempted_at < now - timedelta(days=1)))
        recent = conn.execute(
            select(func.count()).select_from(login_attempts).where(
                and_(login_attempts.c.username == username,
                     login_attempts.c.attempted_at > now - timedelta(minutes=LOCK_MINUTES))
            )
        ).scalar_one()
        if recent >= MAX_FAILURES:
            raise AppError("LOGIN_LOCKED")
        row = conn.execute(select(users.c.id, users.c.password_hash).where(users.c.username == username)).first()
        if row is None or not verify_password(row.password_hash, password or ""):
            conn.execute(insert(login_attempts).values(username=username, attempted_at=now))
            failed = AppError("LOGIN_FAILED")
        else:
            conn.execute(delete(login_attempts).where(login_attempts.c.username == username))
            return row.id
    raise failed  # 실패 기록은 커밋한 뒤에 알린다


def create_session(engine: Engine, user_id: int, now: datetime | None = None) -> str:
    """새 세션 토큰(쿠키에 넣을 원본)을 돌려준다. DB에는 해시만 저장한다."""
    now = now or utcnow()
    token = secrets.token_urlsafe(32)
    with engine.begin() as conn:
        conn.execute(delete(sessions).where(sessions.c.expires_at < now))
        conn.execute(insert(sessions).values(
            token_hash=_token_hash(token), user_id=user_id, expires_at=now + timedelta(days=SESSION_DAYS), created_at=now,
        ))
    return token


def user_id_from_session(engine: Engine, token: str | None, now: datetime | None = None) -> int | None:
    if not token:
        return None
    with engine.connect() as conn:
        return conn.execute(
            select(sessions.c.user_id).where(
                and_(sessions.c.token_hash == _token_hash(token), sessions.c.expires_at > (now or utcnow()))
            )
        ).scalar_one_or_none()


def delete_session(engine: Engine, token: str | None) -> None:
    if token:
        with engine.begin() as conn:
            conn.execute(delete(sessions).where(sessions.c.token_hash == _token_hash(token)))


def change_password(engine: Engine, user_id: int, current: str, new: str, new_confirm: str, keep_token: str | None) -> None:
    """현재 비밀번호를 확인하고 바꾼다. 지금 기기의 세션만 남기고 나머지는 끊는다(F3-8)."""
    with engine.begin() as conn:
        row = conn.execute(select(users.c.username, users.c.password_hash).where(users.c.id == user_id)).first()
        if row is None or row.password_hash is None:
            raise AppError("INVALID_INPUT", "아이디 계정만 비밀번호를 바꿀 수 있어요.")
        if not verify_password(row.password_hash, current or ""):
            raise AppError("WRONG_PASSWORD")
        problem = password_problem(new, row.username) or (None if new == new_confirm else "새 비밀번호 확인이 일치하지 않아요.")
        if problem:
            raise AppError("INVALID_INPUT", problem)
        conn.execute(update(users).where(users.c.id == user_id).values(password_hash=hash_password(new)))
        others = delete(sessions).where(sessions.c.user_id == user_id)
        if keep_token:
            others = others.where(sessions.c.token_hash != _token_hash(keep_token))
        conn.execute(others)


# --- Google ---------------------------------------------------------------------------

def google_user(engine: Engine, sub: str, email: str | None, name: str | None) -> int:
    """Google 계정을 찾거나 만든다. 같은 이메일의 아이디 계정이 있어도 합치지 않는다(F3-11)."""
    with engine.begin() as conn:
        user_id = conn.execute(select(users.c.id).where(users.c.google_sub == sub)).scalar_one_or_none()
        if user_id is not None:
            return user_id
        nickname = (name or (email or "").split("@")[0] or "사용자").strip()[:20]
        if len(nickname) < 2:
            nickname = (nickname + "님")[:20]
        user_id = conn.execute(insert(users).values(google_sub=sub, email=email)).inserted_primary_key[0]
        conn.execute(insert(profiles).values(user_id=user_id, nickname=nickname))
        return user_id


# --- 계정 삭제 ------------------------------------------------------------------------

def delete_account(engine: Engine, user_id: int, *, password: str | None = None, confirm_text: str | None = None) -> None:
    """아이디 계정은 비밀번호, Google 계정은 확인 문구("삭제")를 받아야 지운다(F3-15)."""
    with engine.begin() as conn:
        row = conn.execute(select(users.c.password_hash).where(users.c.id == user_id)).first()
        if row is None:
            return
        if row.password_hash is not None:
            if not verify_password(row.password_hash, password or ""):
                raise AppError("WRONG_PASSWORD")
        elif (confirm_text or "").strip() != "삭제":
            raise AppError("INVALID_INPUT", "확인 문구로 '삭제'를 입력해 주세요.")
        conn.execute(delete(users).where(users.c.id == user_id))  # 나머지는 ON DELETE CASCADE
