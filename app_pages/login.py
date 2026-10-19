"""3단계: 로그인 / 회원가입 / Google 로그인 (docs/PRD_step3.md 5.1~5.2)."""

import streamlit as st

from core import auth, config, session
from core.errors import AppError
from core.runtime import db_guard, get_engine
from core.ui import show_failure

state = st.session_state

st.title("로그인")

try:
    engine = get_engine()
except AppError as e:
    show_failure("저장소에 연결하지 못했어요", {"message": e.message})
    st.stop()


def _done(user_id: int, first_time: bool) -> None:
    session.remember_login(engine, user_id)
    state["goto"] = "app_pages/profile.py" if first_time else state.pop("after_login", "app_pages/fridge.py")
    st.rerun()


if state.get("after_login"):
    st.info("레시피를 저장하려면 로그인해 주세요. 로그인하면 보던 레시피 화면으로 돌아가요.")

tab_login, tab_signup, tab_google = st.tabs(["로그인", "회원가입", "Google"])

with tab_login:
    with st.form("login_form"):
        username = st.text_input("아이디", max_chars=20, autocomplete="username")
        password = st.text_input("비밀번호", type="password", max_chars=64, autocomplete="current-password")
        submitted = st.form_submit_button("로그인", type="primary", width="stretch")
    if submitted:
        try:
            with db_guard():
                user_id = auth.log_in(engine, username, password)
            _done(user_id, first_time=False)
        except AppError as e:
            st.error(e.message)

with tab_signup:
    with st.form("signup_form"):
        new_username = st.text_input("아이디", max_chars=20, help="4~20자, 영문 소문자·숫자·밑줄(_)", autocomplete="username")
        new_password = st.text_input(
            "비밀번호", type="password", max_chars=64, help="8~64자, 영문과 숫자를 모두 포함", autocomplete="new-password"
        )
        new_password2 = st.text_input("비밀번호 확인", type="password", max_chars=64, autocomplete="new-password")
        nickname = st.text_input("닉네임", max_chars=20, help="2~20자, 화면에 보이는 이름")
        st.caption("비밀번호를 잊으면 되찾을 수 없어요(이메일을 받지 않기 때문). 꼭 기억해 두세요.")
        signed_up = st.form_submit_button("가입하기", type="primary", width="stretch")
    if signed_up:
        try:
            with db_guard():
                user_id = auth.sign_up(engine, new_username, new_password, new_password2, nickname)
            _done(user_id, first_time=True)
        except AppError as e:
            st.error(e.message)

with tab_google:
    if config.google_login_configured():
        st.caption("Google 로그인 화면을 거쳐 돌아오면서 페이지가 새로 열려요. 지금 화면에 있던 인식 결과나 추천 레시피는 다시 만들어야 해요.")
        if st.button("Google로 로그인", icon=":material/login:", type="primary", width="stretch"):
            st.login("google")
    else:
        st.info(
            "Google 로그인이 아직 설정되지 않았어요. 관리자가 `.streamlit/secrets.toml`에 `[auth]`와 "
            "`[auth.google]` 설정을 넣어야 쓸 수 있어요. 지금은 아이디로 가입해 주세요."
        )
