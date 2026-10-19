"""아이디·비밀번호 규칙과 argon2 해시 (PRD 3단계 F3-1~F3-3)."""

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

USERNAME_RE = re.compile(r"^[a-z0-9_]{4,20}$")
_hasher = PasswordHasher()
# 없는 아이디로 로그인할 때도 같은 시간이 걸리게 해서, 응답 시간으로 아이디 존재 여부를 알 수 없게 한다
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def username_problem(username: str) -> str | None:
    if not USERNAME_RE.fullmatch(normalize_username(username)):
        return "아이디는 4~20자의 영문 소문자, 숫자, 밑줄(_)만 쓸 수 있어요."
    return None


def password_problem(password: str, username: str = "") -> str | None:
    if not isinstance(password, str) or not 8 <= len(password) <= 64:
        return "비밀번호는 8~64자여야 해요."
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        return "비밀번호에는 영문과 숫자가 모두 들어가야 해요."
    if username and password.lower() == normalize_username(username):
        return "아이디와 같은 비밀번호는 쓸 수 없어요."
    return None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
