"""1단계: 냉장고 사진에서 식재료 인식 (docs/PRD_step1.md)."""

import streamlit as st

from core import config
from core.errors import MESSAGES, AppError
from core.fridge_flow import (
    confirmed_from_rows,
    image_digest,
    init_rows,
    new_row,
    rename_row,
    request_recognition,
    row_flag,
)
from core.runtime import get_client, get_daily_limiter, supports_json_mode, vision_model_plan
from core.ui import show_failure, show_process
from core.vision import prepare_image, recognize_ingredients

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

            # 진행 안내도 원인을 단정하지 않는다(예비 모델로 넘어가는 이유는 429, 502, 시간 초과 등 여러 가지다).
            switched = []

            def on_retry(attempt: int, wait: int) -> None:
                status.write(f"기본 모델이 일시적 오류(429·502·503)를 돌려줘서 {wait}초 뒤 한 번 더 시도합니다.")

            def on_fallback(model: str) -> None:
                before = "앞의 예비 모델도" if switched else "기본 모델이"
                switched.append(model)
                status.write(f"{before} 실패해서 예비 모델({_short(model)})로 다시 시도합니다.")

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
                status.update(label="재료 인식 완료", state="complete", expanded=False)
            except AppError as e:
                state["recognition_error"] = {
                    "message": e.message, "attempts": e.attempts, "digest": image_digest(image_bytes),
                }
                status.update(label="재료 인식 실패", state="error", expanded=False)
    finally:
        state["pending"] = False
    st.rerun()

# 실패는 숨기지 않는다. 지금 올린 사진에 대한 실패만 보여 준다(사진을 바꾸면 그 사진은 아직 시도 전이므로).
error = state.get("recognition_error")
failed_now = bool(error and image_bytes and error["digest"] == image_digest(image_bytes))
if failed_now:
    show_failure("재료 인식에 실패했어요", error)

# --- 인식 결과 ---------------------------------------------------------------
recognition = state.get("recognition")
if recognition:
    result = recognition["result"]
    if failed_now:
        st.warning("아래는 이전 사진에서 성공한 인식 결과예요. 방금 올린 사진의 인식은 실패했어요.")
    elif image_bytes and image_digest(image_bytes) != recognition["digest"]:
        st.info("아래는 이전 사진의 결과예요. 새 사진은 '재료 인식'을 눌러 주세요.")

    st.subheader("찾은 재료")
    if result.get("fallback_used"):
        st.caption(f"기본 모델이 실패해서 예비 모델({_short(result['model'])})로 인식했어요.")
    show_process(result.get("attempts") or [])
    if not result["ingredients"]:
        if not result["is_food_image"]:
            st.warning("냉장고나 식재료 사진이 아닌 것 같아요. 냉장고 안이 잘 보이게 다시 찍어 주세요.")
        else:
            st.warning("식재료를 찾지 못했어요. 밝은 곳에서 냉장고 안이 잘 보이게 다시 찍어 주세요.")
        st.caption("아래 '재료 추가' 줄에서 재료를 직접 넣을 수도 있어요.")

    # 인식 결과를 한 줄씩 고칠 수 있는 행으로 바꿔 보관한다. 새 사진을 인식하면 다시 만든다.
    prefix = recognition["digest"][:8]
    if state.get("rows_for") != recognition["digest"]:
        state["ing_rows"] = init_rows(result, prefix)
        state["rows_for"] = recognition["digest"]
        state["row_seq"] = 0
    rows = state["ing_rows"]

    suspect = [r["name"] for r in rows if row_flag(r) == "name"]
    low = [r["name"] for r in rows if row_flag(r) == "low"]
    if suspect:
        st.warning("재료 이름이 잘못 인식된 것 같아요. 바르게 고쳐 주세요: " + ", ".join(suspect))
    if low:
        st.warning("다음 재료는 사진에서 확실하지 않아요. 맞는지 확인해 주세요: " + ", ".join(low))
    if result.get("notes"):
        st.info(result["notes"])

    def _delete_row(row_id: str) -> None:
        state["ing_rows"] = [r for r in state["ing_rows"] if r["id"] != row_id]

    def _add_row() -> None:
        name = (state.get("new_name") or "").strip()
        if not name:
            return
        state["row_seq"] += 1
        state["ing_rows"].append(
            new_row(f"{prefix}-a{state['row_seq']}", name, state.get("new_qty"), state.get("new_unit"))
        )
        state["new_name"], state["new_qty"], state["new_unit"] = "", None, ""

    # 재료명 · 수량 · 단위 · 삭제를 한 줄에 둔다. st.columns는 칸마다 최소 너비가 있어 휴대폰에서 줄이
    # 화면 밖으로 넘치므로, 수평 컨테이너에 수량·단위·단추는 고정 너비로, 재료명은 남는 폭으로 둔다.
    QTY_W, UNIT_W, BTN_W = 130, 56, 40

    def _line():
        return st.container(horizontal=True, wrap=False, vertical_alignment="center", gap="small")

    header = _line()
    header.caption("재료명", width="stretch")
    header.caption("수량", width=QTY_W)
    header.caption("단위", width=UNIT_W)
    header.caption("", width=BTN_W)

    for row in rows:
        line = _line()
        rid = row["id"]
        name = line.text_input(
            "재료명", value=row["name"], key=f"name_{rid}", max_chars=30, label_visibility="collapsed",
            icon=":material/warning:" if row_flag(row) else None, width="stretch",
        )
        rename_row(row, name)
        row["quantity"] = line.number_input(
            "수량", value=None if row["quantity"] is None else float(row["quantity"]), min_value=0.0, step=1.0,
            format="%g", key=f"qty_{rid}", label_visibility="collapsed", placeholder="-", width=QTY_W,
        )
        row["unit"] = line.text_input(
            "단위", value=row["unit"] or "", key=f"unit_{rid}", max_chars=10, label_visibility="collapsed",
            placeholder="단위", width=UNIT_W,
        )
        line.button(
            ":material/delete:", key=f"del_{rid}", help=f"{row['name']} 삭제", on_click=_delete_row, args=(rid,),
            width=BTN_W,
        )

    line = _line()
    line.text_input(
        "새 재료", key="new_name", max_chars=30, label_visibility="collapsed", placeholder="재료 추가", width="stretch"
    )
    line.number_input(
        "새 수량", value=None, min_value=0.0, step=1.0, format="%g", key="new_qty", label_visibility="collapsed",
        placeholder="수량", width=QTY_W,
    )
    line.text_input("새 단위", key="new_unit", max_chars=10, label_visibility="collapsed", placeholder="단위", width=UNIT_W)
    line.button(":material/add:", key="add_row", help="재료 추가", on_click=_add_row, width=BTN_W)

    state["confirmed_ingredients"] = confirmed_from_rows(rows)

    count = len(state["confirmed_ingredients"])
    st.caption(f"확정한 재료 {count}개 · 이름과 수량을 바로 고치고, 휴지통 단추로 지울 수 있어요.")
    if st.button("이 재료로 레시피 찾기", type="primary", disabled=count == 0, width="stretch"):
        st.switch_page("app_pages/recipes.py")
