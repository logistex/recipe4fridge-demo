"""1단계: 냉장고 사진에서 식재료 인식 (docs/PRD_step1.md)."""

import pandas as pd
import streamlit as st

from core import config
from core.errors import MESSAGES, AppError
from core.fridge_flow import confirmed_from_rows, image_digest, request_recognition, to_editor_rows
from core.runtime import get_client, get_daily_limiter, supports_json_mode, vision_model_plan
from core.vision import CATEGORIES, prepare_image, recognize_ingredients

UPLOAD = "사진 올리기"
CAMERA = "카메라로 찍기"

state = st.session_state


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f}MB" if n >= 1024 * 1024 else f"{max(n // 1024, 1)}KB"


def _short(model: str) -> str:
    return model.split("/")[-1].removesuffix(":free")

st.title("냉장고 재료 찾기")
st.caption("냉장고 사진을 올리면 AI가 식재료를 찾아 줘요. 결과는 직접 고칠 수 있어요.")

api_key = config.get_api_key()
if not api_key:
    st.error(MESSAGES["CONFIG_ERROR"])

# --- 사진 입력 ---------------------------------------------------------------
# 카메라 위젯은 고를 때만 만든다. 미리 만들면 페이지를 열 때마다 카메라 권한을 묻는다.
method = st.segmented_control("사진 입력 방법", [UPLOAD, CAMERA], default=UPLOAD, required=True, label_visibility="collapsed")
if method == CAMERA:
    photo = st.camera_input("냉장고 사진 찍기", resolution=config.CAMERA_RESOLUTION)
else:
    photo = st.file_uploader(
        "냉장고 사진",
        type=["jpg", "jpeg", "png", "webp"],
        max_upload_size=config.MAX_UPLOAD_MB,
        help="JPEG, PNG, WEBP · 최대 10MB. 휴대폰에서는 카메라로 바로 찍을 수도 있어요.",
    )

image_bytes = photo.getvalue() if photo else None
image_error = None
if image_bytes:
    # 올린 사진은 모델에 보내기 전에 자동으로 작게 줄인다. 다시 실행될 때마다 줄이지 않도록 결과를 보관한다.
    digest = image_digest(image_bytes)
    if state.get("prepared", {}).get("digest") != digest:
        try:
            p = prepare_image(image_bytes)
            state["prepared"] = {"digest": digest, "info": p}
        except AppError as e:
            state["prepared"] = {"digest": digest, "error": e.message}
    prepared = state["prepared"]
    image_error = prepared.get("error")
    if image_error:
        st.error(image_error)
    else:
        p = prepared["info"]
        if method == UPLOAD:
            st.image(p.jpeg, width=360)
        st.caption(
            f"AI에 보낼 사진으로 자동 변환했어요: 원본 {_size(p.original_bytes)} ({p.original_width}×{p.original_height})"
            f" → {_size(len(p.jpeg))} ({p.width}×{p.height}, JPEG)"
        )


def _start() -> None:
    state["pending"] = True


busy = state.get("pending", False)
st.button(
    "재료 인식",
    type="primary",
    on_click=_start,
    disabled=busy or not image_bytes or bool(image_error) or not api_key,
    width="stretch",
)

if busy and image_bytes and not image_error:
    try:
        with st.status("재료를 찾고 있어요 (1~2분 걸릴 수 있어요)", expanded=True) as status:

            def on_retry(attempt: int, wait: int) -> None:
                status.write(f"요청이 몰려 {wait}초 뒤 한 번 더 시도합니다.")

            def on_fallback(model: str) -> None:
                status.write(f"기본 모델이 붐벼서 예비 모델({_short(model)})로 다시 시도합니다.")

            def recognize(data: bytes):
                primary, fallbacks, catalog = vision_model_plan(api_key)
                return recognize_ingredients(
                    data,
                    client=get_client(api_key),
                    model=primary,
                    fallback_models=fallbacks,
                    supports_json=lambda m: supports_json_mode(catalog, m),
                    on_retry=on_retry,
                    on_fallback=on_fallback,
                )

            try:
                request_recognition(
                    state,
                    image_bytes,
                    recognize=recognize,
                    limiter=get_daily_limiter(),
                    per_minute=config.SESSION_REQUESTS_PER_MINUTE,
                )
                state.pop("recognition_error", None)
                status.update(label="재료를 찾았어요", state="complete", expanded=False)
            except AppError as e:
                state["recognition_error"] = e.message
                status.update(label="재료를 찾지 못했어요", state="error", expanded=False)
    finally:
        state["pending"] = False
    st.rerun()

if state.get("recognition_error"):
    st.error(state["recognition_error"])

# --- 인식 결과 ---------------------------------------------------------------
recognition = state.get("recognition")
if recognition:
    result = recognition["result"]
    if image_bytes and image_digest(image_bytes) != recognition["digest"]:
        st.info("아래는 이전 사진의 결과예요. 새 사진은 '재료 인식'을 눌러 주세요.")

    st.subheader("찾은 재료")
    if result.get("fallback_used"):
        st.caption(f"기본 모델이 붐벼서 예비 모델({_short(result['model'])})로 인식했어요.")
    if not result["ingredients"]:
        if not result["is_food_image"]:
            st.warning("냉장고나 식재료 사진이 아닌 것 같아요. 냉장고 안이 잘 보이게 다시 찍어 주세요.")
        else:
            st.warning("식재료를 찾지 못했어요. 밝은 곳에서 냉장고 안이 잘 보이게 다시 찍어 주세요.")
        st.caption("아래 표에 재료를 직접 추가할 수도 있어요.")

    suspect = [ing["name"] for ing in result["ingredients"] if ing.get("name_suspect")]
    low = [ing["name"] for ing in result["ingredients"] if ing["confidence"] == "low" and not ing.get("name_suspect")]
    if suspect:
        st.warning("재료 이름이 잘못 인식된 것 같아요. 표에서 바르게 고쳐 주세요: " + ", ".join(suspect))
    if low:
        st.warning("다음 재료는 사진에서 확실하지 않아요. 맞는지 확인해 주세요: " + ", ".join(low))
    if result.get("notes"):
        st.info(result["notes"])

    rows = pd.DataFrame(to_editor_rows(result), columns=["name", "quantity", "unit", "category", "check"])
    rows["quantity"] = pd.to_numeric(rows["quantity"], errors="coerce")  # 수량이 모두 비어도 숫자 열로 유지
    edited = st.data_editor(
        rows,
        key=f"editor_{recognition['digest'][:16]}",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "name": st.column_config.TextColumn("재료명", required=True, max_chars=30),
            "quantity": st.column_config.NumberColumn("수량", min_value=0),
            "unit": st.column_config.TextColumn("단위", max_chars=10),
            "category": st.column_config.SelectboxColumn("분류", options=CATEGORIES, required=True, default="기타"),
            "check": st.column_config.TextColumn("확인", disabled=True),
        },
    )
    state["confirmed_ingredients"] = confirmed_from_rows(edited.to_dict("records"))

    count = len(state["confirmed_ingredients"])
    st.caption(f"확정한 재료 {count}개 · 행을 눌러 고치거나, 맨 아래에서 추가하거나, 체크해서 지울 수 있어요.")
    if st.button("이 재료로 레시피 찾기", type="primary", disabled=count == 0, width="stretch"):
        st.info("레시피 추천은 다음 단계에서 연결됩니다.")
