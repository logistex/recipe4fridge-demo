"""레시피 한 개를 화면에 그리는 공용 코드 (2단계 추천 화면과 3단계 내 레시피가 함께 씀).

모델이 만든 글과 사용자가 고친 글은 모두 md()로 이스케이프한다.
"""

import streamlit as st

from core.recipe_gen import CUISINES, DIFFICULTIES
from core.ui import md


def _timer(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}분 {s}초" if m and s else (f"{m}분" if m else f"{s}초")


def render_summary(r: dict) -> None:
    """요리 소개, 시간·난이도·인분·종류, 가진 재료 활용률."""
    if r.get("summary"):
        st.markdown(md(r["summary"]))
    meta = [
        f"⏱ {r['time_minutes']}분" if r.get("time_minutes") else None,
        DIFFICULTIES.get(r.get("difficulty")),
        f"{r['servings']}인분" if r.get("servings") else None,
        CUISINES.get(r.get("cuisine")) if r.get("cuisine") != "other" else None,
    ]
    st.caption(" · ".join(m for m in meta if m))
    if "usage_ratio" in r:
        missing = r.get("missing_ingredients") or []
        st.markdown(
            f"**가진 재료 {round(r['usage_ratio'] * 100)}% 사용** · "
            + ("추가로 필요: " + md(", ".join(missing)) if missing else "추가로 살 재료 없음")
        )


def render_details(r: dict, key_prefix: str) -> None:
    """재료(보유·기본 양념·구매 필요), 조리 순서 체크박스, 팁."""
    st.markdown("**재료**")
    lines = []
    for ing in r.get("ingredients", []):
        if ing.get("is_pantry"):
            mark, note = "🧂", " (기본 양념)"
        elif ing.get("have"):
            mark, note = "✓", ""
        else:
            mark, note = "🛒", " — 구매 필요"
        lines.append(f"- {mark} {md(ing['name'])} {md(ing.get('amount'))}{note}")
    st.markdown("\n".join(lines))
    st.markdown("**조리 순서**")
    for s in r.get("steps", []):
        timer = f" ⏱ {_timer(s['timer_seconds'])}" if s.get("timer_seconds") else ""
        st.checkbox(f"{s['order']}\\. {md(s['text'])}{timer}", key=f"step_{key_prefix}_{s['order']}")
    if r.get("tips"):
        st.info("💡 " + md(r["tips"]))
