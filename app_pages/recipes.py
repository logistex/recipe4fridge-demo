"""2단계: 확정 재료로 레시피 추천 (docs/PRD_step2.md). 3단계: 프로필 반영과 저장 (docs/PRD_step3.md)."""

import streamlit as st

from core import config
from core.errors import MESSAGES, AppError
from core.options import (
    ALLERGY_OPTIONS,
    CUISINE_OPTIONS,
    DIET_OPTIONS,
    DIFFICULTY_OPTIONS,
    MISSING_OPTIONS,
    TIME_OPTIONS,
)
from core.recipe_flow import input_key, request_recipes
from core.recipe_gen import REJECT_REASONS, Preferences, generate_recipes
from core.recipe_view import render_details, render_summary
from core.repository import dedupe_key, get_profile, save_recipe, saved_keys
from core.runtime import db_guard, get_client, get_daily_limiter, get_engine
from core.ui import md, show_failure, show_process

FRIDGE_PAGE = "app_pages/fridge.py"
LOGIN_PAGE = "app_pages/login.py"

state = st.session_state
user = state.get("user")  # streamlit_app.py가 정한 현재 사용자 (비로그인이면 None)


def _quantity(ing: dict) -> str:
    q = ing.get("quantity")
    if q is None:
        return ing["name"]
    q = int(q) if float(q).is_integer() else q
    return f"{ing['name']} {q}{ing.get('unit') or ''}"


st.title("레시피 추천")

ingredients = state.get("confirmed_ingredients") or []
if not ingredients:
    st.info("먼저 냉장고 사진으로 재료를 찾아 주세요.")
    if st.button("냉장고 재료 찾기로 가기", type="primary"):
        st.switch_page(FRIDGE_PAGE)
    st.stop()

api_key = config.get_api_key()
if not api_key:
    st.error(MESSAGES["CONFIG_ERROR"])

# --- 프로필 (3단계) -------------------------------------------------------------------
# 로그인했으면 프로필 값을 조건의 기본값으로 한 번 채운다(F3-17). 알레르기는 항상 합쳐서 적용한다(F3-18).
profile = {}
if user:
    try:
        with db_guard():
            profile = get_profile(get_engine(), user.id)
    except AppError as e:
        show_failure("프로필을 불러오지 못했어요", {"message": e.message})
    if profile and state.get("prefs_loaded_for") != user.id:
        state["pref_servings"] = profile.get("default_servings", 2)
        state["pref_diet"] = list(profile.get("diet") or [])
        cuisines = profile.get("cuisines") or []
        if len(cuisines) == 1:
            label = next((k for k, v in CUISINE_OPTIONS.items() if v == cuisines[0]), None)
            if label:
                state["pref_cuisine"] = label
        state["prefs_loaded_for"] = user.id
profile_allergies = list(profile.get("allergies") or [])

# --- 가진 재료 --------------------------------------------------------------------
line = st.container(horizontal=True, vertical_alignment="center")
line.markdown("**가진 재료** · " + md(", ".join(_quantity(i) for i in ingredients)), width="stretch")
if line.button("재료 수정", icon=":material/edit:"):
    st.switch_page(FRIDGE_PAGE)

# --- 조건 -------------------------------------------------------------------------
# 위젯 값은 key로 세션에 남는다. 기본값이면 펼치지 않고 바로 추천받을 수 있다.
servings = state.get("pref_servings", 2)
time_label = state.get("pref_time", "제한 없음")
n_allergies = len(set(state.get("pref_allergies", [])) | set(profile_allergies))
summary = f"조건: {servings}인분 · {time_label}" + (f" · 알레르기 {n_allergies}개" if n_allergies else "")
with st.expander(summary + " (바꾸기)"):
    st.number_input("인분", min_value=1, max_value=6, value=2, step=1, key="pref_servings")
    st.segmented_control("최대 조리 시간", list(TIME_OPTIONS), default="제한 없음", required=True, key="pref_time")
    st.segmented_control("난이도", list(DIFFICULTY_OPTIONS), default="상관없음", required=True, key="pref_difficulty")
    st.segmented_control("요리 종류", list(CUISINE_OPTIONS), default="상관없음", required=True, key="pref_cuisine")
    st.segmented_control("추가로 사도 되는 재료", list(MISSING_OPTIONS), default="2개까지", required=True, key="pref_missing")
    st.multiselect("식이 조건", DIET_OPTIONS, accept_new_options=True, key="pref_diet", placeholder="없음")
    st.multiselect(
        "알레르기", ALLERGY_OPTIONS, accept_new_options=True, key="pref_allergies", placeholder="없음 (직접 입력 가능)",
        help="여기 있는 재료와 그 재료로 만든 식품(예: 새우 → 새우젓)이 들어간 레시피는 보여 주지 않아요.",
    )
    if profile_allergies:
        st.caption("프로필에 적은 알레르기도 항상 함께 적용돼요: " + md(", ".join(profile_allergies)))
    if profile.get("disliked"):
        st.caption("프로필의 싫어하는 재료는 가능하면 빼고 만들어요: " + md(", ".join(profile["disliked"])))

selected_allergies = list(state.get("pref_allergies", []))
prefs = Preferences(
    servings=int(state.get("pref_servings", 2)),
    max_time_minutes=TIME_OPTIONS[state.get("pref_time") or "제한 없음"],
    difficulty=DIFFICULTY_OPTIONS[state.get("pref_difficulty") or "상관없음"],
    cuisine=CUISINE_OPTIONS[state.get("pref_cuisine") or "상관없음"],
    diet=list(state.get("pref_diet", [])),
    allergies=selected_allergies + [a for a in profile_allergies if a not in selected_allergies],
    max_missing=MISSING_OPTIONS[state.get("pref_missing") or "2개까지"],
    disliked=list(profile.get("disliked") or []),
    skill_level=profile.get("skill_level"),
)
basis = input_key(ingredients, prefs, [])


# --- 생성 -------------------------------------------------------------------------
def _start(more: bool) -> None:
    state["recipe_pending"] = "more" if more else "new"


busy = state.get("recipe_pending")
st.button(
    "레시피 추천받기", type="primary", on_click=_start, args=(False,), disabled=bool(busy) or not api_key, width="stretch"
)

if busy:
    more = busy == "more"
    exclude = list(state.get("shown_titles", [])) if more else []
    try:
        with st.status("레시피를 고르는 중이에요 (30초~1분 걸릴 수 있어요)", expanded=True) as status:

            def on_retry(attempt: int, wait: int) -> None:
                status.write(f"AI 모델이 일시적 오류(429·502·503)를 돌려줘서 {wait}초 뒤 한 번 더 시도합니다.")

            def generate(ings, p, ex):
                return generate_recipes(
                    ings, p, ex, client=get_client(api_key), model=config.text_model(), on_retry=on_retry
                )

            try:
                result = request_recipes(
                    state, ingredients, prefs, exclude,
                    generate=generate, limiter=get_daily_limiter(), per_minute=config.SESSION_REQUESTS_PER_MINUTE,
                )
                state["shown_titles"] = exclude + [r["title"] for r in result["recipes"]]
                state["recipe_basis"] = basis
                state.pop("recipe_error", None)
                status.update(label="레시피 추천 완료", state="complete", expanded=False)
            except AppError as e:
                state["recipe_error"] = {"message": e.message, "attempts": e.attempts, "more": more, "basis": basis}
                status.update(label="레시피 추천 실패", state="error", expanded=False)
    finally:
        state["recipe_pending"] = None
    st.rerun()

# 실패는 숨기지 않는다. 지금 재료·조건으로 한 요청의 실패만 보여 준다.
error = state.get("recipe_error")
failed_now = bool(error and error["basis"] == basis)
if failed_now:
    show_failure("다른 레시피를 가져오지 못했어요" if error["more"] else "레시피 추천에 실패했어요", error)


# --- 저장 (3단계) ---------------------------------------------------------------------
def _save(recipe: dict, model: str) -> None:
    if not user:
        state["after_login"] = "app_pages/recipes.py"
        state["goto"] = LOGIN_PAGE
        return
    try:
        with db_guard():
            save_recipe(get_engine(), user.id, recipe, state.get("recipe_input") or {}, model)
        state["save_notice"] = ("success", f"'{recipe['title']}'을(를) 내 레시피에 저장했어요.")
    except AppError as e:
        state["save_notice"] = ("info" if e.code == "ALREADY_SAVED" else "error", e.message)


saved = set()
if user:
    try:
        with db_guard():
            saved = saved_keys(get_engine(), user.id)
    except AppError:
        pass  # 저장 표시만 못 할 뿐이다. 저장을 누르면 실패가 그대로 보인다.

# --- 결과 -------------------------------------------------------------------------
notice = state.pop("save_notice", None)
if notice:
    kind, text = notice
    if kind == "success":
        st.success(text)
    elif kind == "info":
        st.info(text)
    else:
        show_failure("레시피를 저장하지 못했어요", {"message": text})

result = state.get("recipe_result")
if result:
    if failed_now:
        st.warning("아래는 이전에 추천받은 레시피예요. 방금 한 요청은 실패했어요.")
    elif state.get("recipe_basis") != basis:
        st.info("재료나 조건이 바뀌었어요. '레시피 추천받기'를 눌러 새로 추천받으세요.")
    recipes = result["recipes"]
    rejected = result.get("rejected") or {}
    reasons = [f"{REJECT_REASONS[k]} {v}개" for k, v in rejected.items()]
    detail = ("AI가 만든 레시피 중 뺀 것: " + ", ".join(reasons) + ".") if reasons else ""
    if result.get("followup_error"):
        detail += f" 모자란 레시피를 채우려고 다시 요청했지만 실패했어요: {result['followup_error']}"
    if not recipes:
        st.error(
            "**❌ 조건에 맞는 레시피를 하나도 만들지 못했어요.**\n\n" + (detail + "\n\n" if detail else "")
            + "추가로 사도 되는 재료, 조리 시간, 식이 조건을 조금 넓혀서 다시 시도해 보세요."
        )
    elif len(recipes) < config.RECIPE_COUNT:
        st.warning(f"**⚠️ 레시피를 {config.RECIPE_COUNT}개 만들지 못하고 {len(recipes)}개만 만들었어요.** {detail}")
    elif reasons:
        st.caption(detail)
    show_process(result.get("attempts") or [])
    for r in recipes:
        with st.container(border=True):
            st.markdown(f"#### {md(r['title'])}")
            render_summary(r)
            with st.expander("자세히 보기"):
                render_details(r, r["id"])
            if user and dedupe_key(r) in saved:
                st.button("저장됨 ✓", key=f"save_{r['id']}", disabled=True)
            else:
                st.button(
                    "저장" if user else "저장 (로그인 필요)", key=f"save_{r['id']}", icon=":material/bookmark:",
                    on_click=_save, args=(r, result.get("model", "")),
                )
    st.caption("AI가 만든 레시피입니다. 알레르기와 재료 상태를 꼭 직접 확인하세요.")
    if recipes:
        st.button(
            "다른 레시피 보기", on_click=_start, args=(True,), disabled=bool(busy) or not api_key, width="stretch"
        )
