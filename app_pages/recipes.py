"""2단계: 확정 재료로 레시피 추천 (docs/PRD_step2.md)."""

import re

import streamlit as st

from core import config
from core.errors import MESSAGES, AppError
from core.recipe_flow import input_key, request_recipes
from core.recipe_gen import CUISINES, DIFFICULTIES, REJECT_REASONS, Preferences, generate_recipes
from core.runtime import get_client, get_daily_limiter

FRIDGE_PAGE = "app_pages/fridge.py"

TIME_OPTIONS = {"15분": 15, "30분": 30, "60분": 60, "제한 없음": None}
DIFFICULTY_OPTIONS = {"쉬움": "easy", "보통": "normal", "상관없음": None}
CUISINE_OPTIONS = {"한식": "korean", "양식": "western", "중식": "chinese", "일식": "japanese", "상관없음": None}
MISSING_OPTIONS = {"허용 안 함": 0, "2개까지": 2, "상관없음": None}
DIET_OPTIONS = ["채식", "비건", "글루텐 제외"]
ALLERGY_OPTIONS = ["달걀", "우유", "밀", "대두", "땅콩", "견과류", "새우", "게", "조개", "생선", "오징어", "돼지고기", "소고기", "닭고기", "복숭아", "토마토"]

state = st.session_state


def md(text: str) -> str:
    """모델이 만든 글을 마크다운으로 해석하지 않도록 특수 문자를 이스케이프한다(링크·이미지 문법 차단)."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~])", r"\\\1", text or "")


def _quantity(ing: dict) -> str:
    q = ing.get("quantity")
    if q is None:
        return ing["name"]
    q = int(q) if float(q).is_integer() else q
    return f"{ing['name']} {q}{ing.get('unit') or ''}"


def _timer(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}분 {s}초" if m and s else (f"{m}분" if m else f"{s}초")


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

# --- 가진 재료 --------------------------------------------------------------------
line = st.container(horizontal=True, vertical_alignment="center")
line.markdown("**가진 재료** · " + md(", ".join(_quantity(i) for i in ingredients)), width="stretch")
if line.button("재료 수정", icon=":material/edit:"):
    st.switch_page(FRIDGE_PAGE)

# --- 조건 -------------------------------------------------------------------------
# 위젯 값은 key로 세션에 남는다. 기본값이면 펼치지 않고 바로 추천받을 수 있다.
servings = state.get("pref_servings", 2)
time_label = state.get("pref_time", "제한 없음")
allergies = state.get("pref_allergies", [])
summary = f"조건: {servings}인분 · {time_label}" + (f" · 알레르기 {len(allergies)}개" if allergies else "")
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

prefs = Preferences(
    servings=int(state.get("pref_servings", 2)),
    max_time_minutes=TIME_OPTIONS[state.get("pref_time") or "제한 없음"],
    difficulty=DIFFICULTY_OPTIONS[state.get("pref_difficulty") or "상관없음"],
    cuisine=CUISINE_OPTIONS[state.get("pref_cuisine") or "상관없음"],
    diet=list(state.get("pref_diet", [])),
    allergies=list(state.get("pref_allergies", [])),
    max_missing=MISSING_OPTIONS[state.get("pref_missing") or "2개까지"],
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
                status.write(f"요청이 몰려 {wait}초 뒤 한 번 더 시도합니다.")

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
                status.update(label="레시피를 골랐어요", state="complete", expanded=False)
            except AppError as e:
                state["recipe_error"] = e.message
                status.update(label="레시피를 만들지 못했어요", state="error", expanded=False)
    finally:
        state["recipe_pending"] = None
    st.rerun()

if state.get("recipe_error"):
    st.error(state["recipe_error"])

# --- 결과 -------------------------------------------------------------------------


def render_recipe(r: dict) -> None:
    with st.container(border=True):
        st.markdown(f"#### {md(r['title'])}")
        if r.get("summary"):
            st.markdown(md(r["summary"]))
        meta = [
            f"⏱ {r['time_minutes']}분" if r.get("time_minutes") else None,
            DIFFICULTIES.get(r["difficulty"]),
            f"{r['servings']}인분",
            CUISINES.get(r["cuisine"]) if r["cuisine"] != "other" else None,
        ]
        st.caption(" · ".join(m for m in meta if m))
        missing = r["missing_ingredients"]
        st.markdown(
            f"**가진 재료 {round(r['usage_ratio'] * 100)}% 사용** · "
            + ("추가로 필요: " + md(", ".join(missing)) if missing else "추가로 살 재료 없음")
        )
        with st.expander("자세히 보기"):
            st.markdown("**재료**")
            lines = []
            for ing in r["ingredients"]:
                if ing["is_pantry"]:
                    mark, note = "🧂", " (기본 양념)"
                elif ing["have"]:
                    mark, note = "✓", ""
                else:
                    mark, note = "🛒", " — 구매 필요"
                lines.append(f"- {mark} {md(ing['name'])} {md(ing['amount'])}{note}")
            st.markdown("\n".join(lines))
            st.markdown("**조리 순서**")
            for s in r["steps"]:
                timer = f" ⏱ {_timer(s['timer_seconds'])}" if s.get("timer_seconds") else ""
                st.checkbox(f"{s['order']}\\. {md(s['text'])}{timer}", key=f"step_{r['id']}_{s['order']}")
            if r.get("tips"):
                st.info("💡 " + md(r["tips"]))


result = state.get("recipe_result")
if result:
    if state.get("recipe_basis") != basis:
        st.info("재료나 조건이 바뀌었어요. '레시피 추천받기'를 눌러 새로 추천받으세요.")
    recipes = result["recipes"]
    if not recipes:
        st.warning("조건에 맞는 레시피를 찾지 못했어요. 추가로 사도 되는 재료, 조리 시간, 식이 조건을 조금 넓혀 보세요.")
    rejected = {k: v for k, v in (result.get("rejected") or {}).items() if k != "invalid"}
    if rejected:
        st.caption(
            "조건에 맞지 않아 뺀 레시피: " + ", ".join(f"{REJECT_REASONS[k]} {v}개" for k, v in rejected.items())
        )
    for recipe in recipes:
        render_recipe(recipe)
    st.caption("AI가 만든 레시피입니다. 알레르기와 재료 상태를 꼭 직접 확인하세요.")
    if recipes:
        st.button(
            "다른 레시피 보기", on_click=_start, args=(True,), disabled=bool(busy) or not api_key, width="stretch"
        )
