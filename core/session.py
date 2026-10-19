"""화면에서 쓰는 로그인 상태: Google(st.user)과 아이디 세션 쿠키를 합쳐 현재 사용자를 정한다(F3-12).

아이디 로그인은 세션 토큰을 브라우저 쿠키에 넣어 새로고침해도 유지한다(F3-6).
- 읽기: st.context.cookies (페이지를 처음 열 때 받은 쿠키)
- 쓰기: st.html(..., unsafe_allow_javascript=True)로 document.cookie를 설정
st.context.cookies는 페이지를 연 뒤로는 바뀌지 않으므로, 로그인·로그아웃 직후의 상태는 세션 상태로 함께 관리한다.
"""

import streamlit as st
from sqlalchemy.engine import Engine

from core import auth, config
from core.auth import User

COOKIE_NAME = "r4f_session"
state = st.session_state


def google_identity() -> dict | None:
    """Google로 로그인했으면 {"sub", "email", "name"}. 테스트에서 이 함수를 바꿔 끼운다."""
    try:
        if config.google_login_configured() and st.user.is_logged_in:
            return {"sub": st.user.get("sub"), "email": st.user.get("email"), "name": st.user.get("name")}
    except Exception:
        pass
    return None


def cookie_token() -> str | None:
    try:
        value = st.context.cookies.get(COOKIE_NAME)
    except Exception:
        return None
    return value if isinstance(value, str) and value else None


def current_user(engine: Engine) -> User | None:
    identity = google_identity()
    if identity and identity.get("sub"):
        cached = state.get("auth_user")
        if cached and state.get("auth_google_sub") == identity["sub"]:
            return cached
        user = auth.load_user(engine, auth.google_user(engine, identity["sub"], identity.get("email"), identity.get("name")))
        state["auth_user"], state["auth_google_sub"], state["auth_token"] = user, identity["sub"], None
        return user

    token = state.get("auth_token")
    if token is None and not state.get("auth_logged_out"):
        token = cookie_token()  # 로그아웃한 뒤에는 처음 받은 쿠키를 다시 쓰지 않는다
    if not token:
        return None
    cached = state.get("auth_user")
    if cached and state.get("auth_token") == token:
        return cached
    user_id = auth.user_id_from_session(engine, token)
    user = auth.load_user(engine, user_id) if user_id else None
    if user:
        state["auth_user"], state["auth_token"], state["auth_google_sub"] = user, token, None
    else:
        _queue_cookie("", 0)  # 만료되었거나 지워진 세션의 쿠키는 정리한다
        state["auth_logged_out"] = True
    return user


def remember_login(engine: Engine, user_id: int) -> None:
    """아이디 로그인 성공 뒤 호출: 세션을 만들고 쿠키를 설정한다."""
    token = auth.create_session(engine, user_id)
    state["auth_token"], state["auth_user"] = token, auth.load_user(engine, user_id)
    state.pop("auth_logged_out", None)
    _queue_cookie(token, auth.SESSION_DAYS * 24 * 3600)


def refresh_user(engine: Engine, user: User) -> None:
    """닉네임 변경 등으로 캐시한 사용자 정보를 다시 읽는다."""
    state["auth_user"] = auth.load_user(engine, user.id)


def log_out(engine: Engine, user: User | None) -> None:
    if user and user.method == "google":
        for key in ("auth_user", "auth_google_sub"):
            state.pop(key, None)
        st.logout()  # Streamlit이 신원 쿠키를 지우고 다시 실행한다
        return
    auth.delete_session(engine, state.get("auth_token"))
    for key in ("auth_user", "auth_token"):
        state.pop(key, None)
    state["auth_logged_out"] = True
    _queue_cookie("", 0)


def _queue_cookie(value: str, max_age: int) -> None:
    # 로그인 직후 페이지를 옮기면(st.switch_page) 이번 실행의 화면 출력이 버려지므로,
    # 다음 실행에서 streamlit_app.py가 flush_cookie()로 쿠키 스크립트를 내보낸다.
    state["auth_cookie"] = (value, max_age)


def flush_cookie() -> None:
    pending = state.pop("auth_cookie", None)
    if pending is None:
        return
    value, max_age = pending
    # 토큰은 token_urlsafe라 따옴표나 세미콜론이 들어가지 않는다
    st.html(
        "<script>document.cookie = '" + COOKIE_NAME + "=" + value + "; path=/; max-age=" + str(max_age)
        + "; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');</script>",
        unsafe_allow_javascript=True,
        width=1,
    )
