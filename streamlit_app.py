"""앱 진입점: 현재 사용자 확인, 페이지 등록, 사이드바."""

import logging

import streamlit as st

from core import session
from core.db import is_local
from core.errors import AppError
from core.runtime import get_engine
from core.ui import md

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(page_title="냉장고 레시피", page_icon="🥬", layout="centered")
state = st.session_state

# --- 현재 사용자 (3단계) --------------------------------------------------------------
# 저장소에 연결하지 못해도 1·2단계는 그대로 쓸 수 있어야 한다(F3-26).
engine, user, db_error = None, None, None
try:
    engine = get_engine()
    user = session.current_user(engine)
except AppError as e:
    db_error = e.message
state["user"] = user

pages = [
    st.Page("app_pages/fridge.py", title="냉장고 재료 찾기", icon="🥬", default=True),
    st.Page("app_pages/recipes.py", title="레시피 추천", icon="🍳"),
]
if user:  # 로그인하지 않으면 내 레시피·프로필은 메뉴에 보이지 않는다(F3-14)
    pages += [
        st.Page("app_pages/my_recipes.py", title="내 레시피", icon="📒"),
        st.Page("app_pages/profile.py", title="프로필", icon="👤"),
    ]
else:
    pages.append(st.Page("app_pages/login.py", title="로그인 / 회원가입", icon="🔑"))
page = st.navigation(pages)

# 콜백이나 로그인 처리에서 "이 페이지로 가라"고 남긴 요청을 처리한다(페이지 목록이 바뀐 뒤여야 함)
goto = state.pop("goto", None)
if goto:
    st.switch_page(goto)

# 로그인·로그아웃 직후의 쿠키 설정. 페이지 이동(st.switch_page)이 일어나는 실행의 화면 출력은 버려지므로,
# 반드시 이동을 처리한 뒤에 내보낸다(그렇지 않으면 쿠키가 설정되지 않아 새로고침하면 로그아웃된다).
session.flush_cookie()

with st.sidebar:
    if user:
        st.markdown(f"**{md(user.nickname)}**님 · {user.method_label}로 로그인")
        if st.button("로그아웃", icon=":material/logout:"):
            session.log_out(engine, user)
            state["goto"] = "app_pages/fridge.py"
            st.rerun()
    elif db_error:
        st.error(f"❌ 저장소 연결 실패 — {db_error} 로그인과 저장은 지금 쓸 수 없지만, 재료 찾기와 레시피 추천은 쓸 수 있어요.")
    if engine is not None and is_local(engine):
        st.caption("로컬 개발용 DB(SQLite)를 쓰고 있어요. 배포에서는 Supabase를 씁니다.")
    st.caption("무료 AI 모델을 쓰고 있어서 응답이 늦거나 하루 사용량이 제한될 수 있어요.")

page.run()
