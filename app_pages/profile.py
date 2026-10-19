"""3단계: 프로필, 비밀번호 변경, 계정 삭제 (docs/PRD_step3.md 5.3~5.4)."""

import streamlit as st

from core import auth, session
from core.db import is_local
from core.errors import AppError
from core.options import ALLERGY_OPTIONS, CUISINE_OPTIONS, DIET_OPTIONS, SKILL_OPTIONS
from core.repository import get_profile, update_profile
from core.runtime import db_guard, get_engine
from core.ui import show_failure

state = st.session_state
user = state["user"]

st.title("프로필")

try:
    engine = get_engine()
    with db_guard():
        profile = get_profile(engine, user.id)
except AppError as e:
    show_failure("프로필을 불러오지 못했어요", {"message": e.message})
    st.stop()

notice = state.pop("profile_notice", None)
if notice:
    st.success(notice)

skill_labels = {v: k for k, v in SKILL_OPTIONS.items()}
cuisine_labels = {v: k for k, v in CUISINE_OPTIONS.items() if v}

with st.form("profile_form"):
    nickname = st.text_input("닉네임", value=profile.get("nickname", ""), max_chars=20)
    allergies = st.multiselect(
        "알레르기", sorted(set(ALLERGY_OPTIONS) | set(profile.get("allergies", []))), default=profile.get("allergies", []),
        accept_new_options=True, placeholder="없음 (직접 입력 가능)",
        help="추천 레시피에서 항상 제외돼요. 그 재료로 만든 식품(예: 새우 → 새우젓)도 함께 빠져요.",
    )
    diet = st.multiselect(
        "식이 조건", sorted(set(DIET_OPTIONS) | set(profile.get("diet", []))), default=profile.get("diet", []),
        accept_new_options=True, placeholder="없음",
    )
    disliked = st.multiselect(
        "싫어하는 재료", profile.get("disliked", []), default=profile.get("disliked", []),
        accept_new_options=True, placeholder="없음 (직접 입력)", help="가능하면 빼고 만들어요(알레르기처럼 강제로 빼지는 않아요).",
    )
    skill = st.segmented_control(
        "요리 실력", list(SKILL_OPTIONS), default=skill_labels.get(profile.get("skill_level"), "보통"), required=True,
        help="초보로 하면 조리 순서를 더 잘게 나누고 용어를 풀어서 설명해요.",
    )
    servings = st.number_input("기본 인분", min_value=1, max_value=6, value=int(profile.get("default_servings", 2)), step=1)
    cuisines = st.multiselect(
        "선호 요리 종류", list(cuisine_labels.values()),
        default=[cuisine_labels[c] for c in profile.get("cuisines", []) if c in cuisine_labels], placeholder="상관없음",
        help="하나만 고르면 레시피 화면의 요리 종류가 그것으로 미리 정해져요.",
    )
    if st.form_submit_button("프로필 저장", type="primary", width="stretch"):
        try:
            with db_guard():
                update_profile(engine, user.id, {
                    "nickname": nickname, "allergies": allergies, "diet": diet, "disliked": disliked,
                    "skill_level": SKILL_OPTIONS[skill or "보통"], "default_servings": int(servings),
                    "cuisines": [CUISINE_OPTIONS[c] for c in cuisines],
                })
                session.refresh_user(engine, user)
            state.pop("prefs_loaded_for", None)  # 레시피 화면의 조건 기본값을 새 프로필로 다시 채운다
            state["profile_notice"] = "프로필을 저장했어요."
            st.rerun()
        except AppError as e:
            st.error(e.message)

where = "이 컴퓨터의 로컬 개발용 DB(SQLite)" if is_local(engine) else "Supabase 프로젝트의 DB"
account = f"아이디 `{user.username}`" if user.method == "password" else f"Google 계정 `{user.email or ''}`"
st.caption(
    f"수집하는 정보: {account}, 위 프로필(알레르기·식이 조건은 건강 관련 정보), 저장한 레시피. "
    f"저장 위치: {where}. 계정을 삭제하면 모두 즉시 지워져요."
)

if user.method == "password":
    with st.expander("비밀번호 바꾸기"):
        with st.form("password_form", clear_on_submit=True):
            current = st.text_input("현재 비밀번호", type="password", autocomplete="current-password")
            new = st.text_input("새 비밀번호", type="password", help="8~64자, 영문과 숫자를 모두 포함", autocomplete="new-password")
            new2 = st.text_input("새 비밀번호 확인", type="password", autocomplete="new-password")
            if st.form_submit_button("비밀번호 바꾸기"):
                try:
                    with db_guard():
                        auth.change_password(engine, user.id, current, new, new2, state.get("auth_token"))
                    st.success("비밀번호를 바꿨어요. 다른 기기에서 로그인한 세션은 모두 끊었어요.")
                except AppError as e:
                    st.error(e.message)

with st.expander("계정 삭제"):
    st.warning("계정을 삭제하면 프로필과 저장한 레시피가 모두 지워지고 되돌릴 수 없어요.")
    with st.form("delete_form"):
        if user.method == "password":
            secret = st.text_input("비밀번호", type="password", autocomplete="current-password")
        else:
            secret = st.text_input("확인을 위해 '삭제'라고 입력하세요")
            st.caption("Google 계정 자체는 지워지지 않아요. 이 앱에 저장된 정보만 지워져요.")
        if st.form_submit_button("계정 삭제", type="primary"):
            try:
                with db_guard():
                    if user.method == "password":
                        auth.delete_account(engine, user.id, password=secret)
                    else:
                        auth.delete_account(engine, user.id, confirm_text=secret)
                session.log_out(engine, user)
                state["goto"] = "app_pages/fridge.py"
                st.rerun()
            except AppError as e:
                st.error(e.message)
