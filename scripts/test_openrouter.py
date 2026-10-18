"""OpenRouter API 동작 테스트: 텍스트 인식과 이미지 인식.

사용법 (프로젝트 루트에서):
    python scripts/test_openrouter.py          # 둘 다 실행
    python scripts/test_openrouter.py text     # 텍스트만
    python scripts/test_openrouter.py image    # 이미지만

API 키는 프로젝트 루트 .env의 OPENROUTER_API_KEY에서 읽으며, 화면에 출력하지 않는다.
"""

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
API_URL = "https://openrouter.ai/api/v1/chat/completions"
TEXT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
VISION_MODEL = "google/gemma-4-26b-a4b-it:free"
TEST_IMAGE = SCRIPT_DIR / "test_image.png"


def load_api_key() -> str:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        sys.exit(".env 파일이 없습니다. .env.example을 참고해 만들어 주세요.")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip().removeprefix("export ").strip() == "OPENROUTER_API_KEY":
            return value.strip().strip('"').strip("'")
    sys.exit(".env에 OPENROUTER_API_KEY가 없습니다.")


def chat(api_key: str, model: str, messages: list, max_tokens: int = 2048, retries: int = 2) -> dict:
    payload = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens}).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": "Study_04 API test",
    }
    for attempt in range(retries + 1):
        req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            # 무료 모델은 429(요청 한도)가 잦으므로 잠시 기다렸다 재시도
            if e.code in (429, 502, 503) and attempt < retries:
                wait = 10 * (attempt + 1)
                print(f"  HTTP {e.code} - {wait}초 후 재시도 ({attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from None
    raise RuntimeError("재시도 횟수 초과")


def print_result(title: str, model: str, data: dict, elapsed: float) -> None:
    choice = data["choices"][0]
    message = choice["message"]
    usage = data.get("usage", {})
    print(f"\n===== {title} =====")
    print(f"모델      : {data.get('model', model)}")
    print(f"제공자    : {data.get('provider', '-')}")
    print(f"소요 시간 : {elapsed:.1f}초")
    print(f"종료 사유 : {choice.get('finish_reason')}")
    print(f"토큰      : 입력 {usage.get('prompt_tokens')} / 출력 {usage.get('completion_tokens')}")
    print("--- 응답 ---")
    print((message.get("content") or "(본문 없음)").strip())


def make_test_image() -> Path:
    """정답을 알고 있는 테스트 이미지를 만든다: 도형 3개 + 글자."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse((40, 60, 180, 200), fill=(220, 30, 30))                 # 빨간 원
    draw.rectangle((230, 60, 370, 200), fill=(30, 80, 220))              # 파란 사각형
    draw.polygon([(490, 60), (420, 200), (560, 200)], fill=(30, 170, 60))  # 초록 삼각형
    try:
        font = ImageFont.truetype("arial.ttf", 56)
    except OSError:
        font = ImageFont.load_default()
    draw.text((120, 270), "HELLO 2026", fill="black", font=font)
    img.save(TEST_IMAGE)
    return TEST_IMAGE


def test_text(api_key: str) -> bool:
    prompt = (
        "다음 문장에서 이름, 날짜, 장소, 구매 물품을 추출해 JSON으로만 답해 줘. "
        '키는 "name", "date", "place", "items"(배열)로 해.\n\n'
        "문장: 김민수는 2026년 10월 3일 부산 해운대 시장에서 고등어 두 마리와 귤 한 상자를 샀다."
    )
    start = time.time()
    data = chat(api_key, TEXT_MODEL, [{"role": "user", "content": prompt}])
    print_result("텍스트 인식 테스트", TEXT_MODEL, data, time.time() - start)
    return True


def test_image(api_key: str) -> bool:
    path = make_test_image()
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "이 이미지에 있는 도형을 왼쪽부터 색상과 모양으로 나열하고, 이미지에 적힌 글자를 그대로 읽어 줘. 한국어로 짧게 답해 줘."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }]
    start = time.time()
    data = chat(api_key, VISION_MODEL, messages)
    print_result("이미지 인식 테스트", VISION_MODEL, data, time.time() - start)
    print("(정답: 빨간 원, 파란 사각형, 초록 삼각형 / 글자 'HELLO 2026')")
    return True


def main() -> None:
    api_key = load_api_key()
    targets = sys.argv[1:] or ["text", "image"]
    tests = {"text": test_text, "image": test_image}
    failed = False
    for name in targets:
        try:
            tests[name](api_key)
        except Exception as e:  # 한 테스트가 실패해도 나머지는 실행
            failed = True
            print(f"\n===== {name} 테스트 실패 =====\n{e}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
