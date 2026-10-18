"""앱 진입점: 페이지 등록과 공통 설정."""

import logging

import streamlit as st

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(page_title="냉장고 레시피", page_icon="🥬", layout="centered")

pages = [
    st.Page("app_pages/fridge.py", title="냉장고 재료 찾기", icon="🥬", default=True),
    st.Page("app_pages/recipes.py", title="레시피 추천", icon="🍳"),
]
page = st.navigation(pages)

with st.sidebar:
    st.caption("무료 AI 모델을 쓰고 있어서 응답이 늦거나 하루 사용량이 제한될 수 있어요.")

page.run()
