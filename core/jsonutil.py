"""모델 응답에서 JSON 꺼내기 (1·2단계 공용)."""

import json
import re


def extract_json(text: str) -> dict:
    """코드 블록이나 설명 문장이 섞인 응답에서 JSON 객체를 꺼낸다."""
    text = (text or "").strip()
    candidates = [text]
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("JSON 객체를 찾지 못함")


def message_text(response: dict) -> str:
    """chat completions 응답의 본문. 일부 제공자는 콘텐츠를 조각 배열로 보낸다."""
    content = response["choices"][0]["message"].get("content")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""
