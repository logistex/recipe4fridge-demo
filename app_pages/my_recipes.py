"""3단계: 내 레시피 목록과 상세 (docs/PRD_step3.md 5.5)."""

import streamlit as st

from core.errors import AppError
from core.recipe_view import render_details, render_summary
from core.repository import SORTS, delete_recipe, get_recipe, list_recipes, restore_recipe, update_recipe
from core.runtime import db_guard, get_engine
from core.ui import md, show_failure

PAGE_SIZE = 20
state = st.session_state
user = state["user"]

st.title("내 레시피")

notice = state.pop("my_notice", None)
if notice:
    st.toast(notice, icon="✅")  # 화면을 밀어내지 않는 알림 (위에 띄우면 펼쳐 둔 상세가 아래로 밀린다)

controls = st.container(horizontal=True, vertical_alignment="bottom")
query = controls.text_input("검색", placeholder="제목이나 재료로 찾기", key="my_query", width="stretch")
sort_label = controls.segmented_control("정렬", list(SORTS.values()), default="최신순", required=True, key="my_sort")
favorite_only = st.toggle("즐겨찾기만 보기", key="my_fav")
sort = next(k for k, v in SORTS.items() if v == sort_label)
limit = state.get("my_limit", PAGE_SIZE)

try:
    engine = get_engine()
    with db_guard():
        rows, total = list_recipes(engine, user.id, sort=sort, favorite_only=favorite_only, query=query, limit=limit)
except AppError as e:
    show_failure("저장한 레시피를 불러오지 못했어요", {"message": e.message})
    st.stop()


def _act(fn, recipe_id: int, message: str, **kwargs) -> None:
    try:
        with db_guard():
            fn(engine, user.id, recipe_id, **kwargs)
        state["my_notice"] = message
    except AppError as e:
        state["my_error"] = e.message


def _rate(recipe_id: int) -> None:
    value = state.get(f"rate_{recipe_id}")
    _act(update_recipe, recipe_id, "별점을 저장했어요.", rating=None if value is None else value + 1)


error = state.pop("my_error", None)
if error:
    show_failure("변경하지 못했어요", {"message": error})

if total == 0:
    if query or favorite_only:
        st.info("조건에 맞는 레시피가 없어요.")
    else:
        st.info("아직 저장한 레시피가 없어요. 냉장고 사진으로 첫 레시피를 찾아보세요.")
        if st.button("냉장고 재료 찾기", type="primary"):
            st.switch_page("app_pages/fridge.py")
    st.stop()

st.caption(f"저장한 레시피 {total}개 중 {len(rows)}개를 보여 줘요.")

for row in rows:
    rid, recipe = row["id"], row["recipe"]
    with st.container(border=True):
        star = "⭐ " if row["is_favorite"] else ""
        st.markdown(f"#### {star}{md(row['title'])}")
        render_summary(recipe)
        # key를 주어야 저장·별점 등으로 다시 실행돼도 펼쳐 둔 상태가 유지된다
        with st.expander("자세히 보기 · 고치기", key=f"open_{rid}"):
            render_details(recipe, f"saved{rid}")

            st.markdown("**별점과 메모**")
            st.feedback(
                "stars", key=f"rate_{rid}", default=row["rating"] - 1 if row["rating"] else None,
                on_change=_rate, args=(rid,),
            )
            with db_guard():
                full = get_recipe(engine, user.id, rid)  # 메모는 목록 조회에 없어서 따로 읽는다
            memo = st.text_area("메모", value=(full or {}).get("memo") or "", max_chars=1000, key=f"memo_{rid}")
            line = st.container(horizontal=True)
            if line.button("메모 저장", key=f"memo_save_{rid}"):
                _act(update_recipe, rid, "메모를 저장했어요.", memo=memo)
                st.rerun()
            if line.button("즐겨찾기 해제" if row["is_favorite"] else "즐겨찾기", key=f"fav_{rid}", icon=":material/star:"):
                _act(update_recipe, rid, "즐겨찾기를 바꿨어요.", is_favorite=not row["is_favorite"])
                st.rerun()

            st.markdown("**레시피 고치기**")
            with st.form(f"edit_{rid}"):
                title = st.text_input("제목", value=recipe["title"], max_chars=40)
                steps = st.text_area("조리 순서 (한 줄에 한 단계)", value="\n".join(s["text"] for s in recipe["steps"]), height=180)
                if st.form_submit_button("고친 내용 저장"):
                    _act(update_recipe, rid, "레시피를 고쳤어요.", title=title, steps=steps.splitlines())
                    st.rerun()
            line = st.container(horizontal=True)
            if line.button("원래대로", key=f"restore_{rid}", help="저장할 때의 내용으로 되돌려요"):
                _act(restore_recipe, rid, "저장할 때의 내용으로 되돌렸어요.")
                st.rerun()
            confirm = line.checkbox("삭제 확인", key=f"del_confirm_{rid}")
            if line.button("삭제", key=f"del_{rid}", disabled=not confirm, icon=":material/delete:"):
                _act(delete_recipe, rid, f"'{row['title']}'을(를) 지웠어요.")
                st.rerun()

if total > len(rows):
    if st.button("더 보기", width="stretch"):
        state["my_limit"] = limit + PAGE_SIZE
        st.rerun()
