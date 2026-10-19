"""실패와 처리 과정을 화면에 정직하게 보여 주는 공용 표시 (1·2단계)."""

import re
from collections import Counter

import streamlit as st


def md(text) -> str:
    """사용자 입력·모델 출력을 마크다운으로 해석하지 않도록 특수 문자를 이스케이프한다(링크·이미지 문법 차단)."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~])", r"\\\1", str(text or ""))


def short_model(model: str | None) -> str:
    return (model or "?").split("/")[-1].removesuffix(":free")


def outcome_text(attempt: dict) -> str:
    outcome = attempt.get("outcome")
    if outcome == 200:
        return "응답함"
    if outcome == "unreadable":
        return "응답했지만 약속한 형식이 아니라 읽을 수 없음"
    if outcome == "timeout":
        return f"{attempt.get('limit', '?')}초 안에 응답 없음"
    if outcome == "network":
        return "연결 실패"
    if outcome == 429:
        return "요청 한도 초과로 거절(429)"
    if outcome == 401:
        return "API 키 거절(401)"
    if outcome in (502, 503):
        return f"AI 서버 오류({outcome})"
    return f"요청 실패({outcome})"


def failed(attempt: dict) -> bool:
    return attempt.get("outcome") != 200


def summary(attempts: list[dict]) -> str:
    """예: "AI 요청 5회: 요청 한도 초과로 거절(429) 2회, 30초 안에 응답 없음 3회"."""
    counts = Counter(outcome_text(a) for a in attempts)
    return f"AI 요청 {len(attempts)}회: " + ", ".join(f"{text} {n}회" for text, n in counts.items())


def attempt_lines(attempts: list[dict]) -> str:
    """첫 요청의 모델을 기본 모델로 본다(설정이 아니라 실제로 보낸 순서 기준)."""
    primary = attempts[0].get("model") if attempts else None
    lines = []
    for i, a in enumerate(attempts, 1):
        role = "기본 모델" if a.get("model") == primary else "예비 모델"
        lines.append(f"{i}. {role} `{short_model(a.get('model'))}` — {outcome_text(a)} ({a.get('seconds', '?')}초)")
    return "\n".join(lines)


def show_failure(title: str, error: dict) -> None:
    """실패를 숨기지 않고 무엇이, 왜 실패했는지 보여 준다. error: {"message", "attempts"}."""
    attempts = error.get("attempts") or []
    body = f"**❌ {title}**\n\n{error['message']}"
    if attempts:
        body += f"\n\n{summary(attempts)}"
    st.error(body)
    if attempts:
        with st.expander("시도한 내용 자세히 보기"):
            st.markdown(attempt_lines(attempts))


def show_process(attempts: list[dict]) -> None:
    """성공했더라도 중간에 실패한 요청이 있었으면 그 사실을 알린다."""
    if not any(failed(a) for a in attempts):
        return
    n_failed = sum(failed(a) for a in attempts)
    st.caption(f"처리 과정: AI 요청 {len(attempts)}회 중 {n_failed}회 실패한 뒤 결과를 받았어요.")
    with st.expander("시도한 내용 자세히 보기"):
        st.markdown(attempt_lines(attempts))
