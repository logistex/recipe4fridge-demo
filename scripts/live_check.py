"""실제 OpenRouter API로 1단계(사진 인식)와 2단계(레시피 생성)를 실행하고 항목별로 점검한다.

CLAUDE.md "실행 시 확인 사항"을 따른다. 무료 한도를 약 2~7회 쓴다.

사용법 (프로젝트 루트에서):
    .venv/Scripts/python scripts/live_check.py              # 1·2단계 모두
    .venv/Scripts/python scripts/live_check.py --vision     # 1단계만
    .venv/Scripts/python scripts/live_check.py --recipe     # 2단계만 (정답 재료 목록으로)

결과에 ❌가 하나라도 있으면 종료 코드 1.
"""

import argparse
import io
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from core import config  # noqa: E402
from core.errors import AppError  # noqa: E402
from core.ingredient_names import category_for, is_suspicious_name  # noqa: E402
from core.openrouter import OpenRouterClient  # noqa: E402
from core.recipe_gen import CUISINES, Preferences, generate_recipes  # noqa: E402
from core.vision import recognize_ingredients  # noqa: E402

# 테스트 사진: 냉장고 칸 3개에 음식 이모지 12개(달걀 2개). 정답은 아래 11가지.
FRIDGE_EMOJI = [["🥚", "🥚", "🥛", "🧀"], ["🥕", "🍅", "🥬", "🧅"], ["🍎", "🍋", "🥩", "🍗"]]
# 정답 재료와 함께 인정하는 이름 (🥬는 상추·양배추·배추 등으로 보는 것이 자연스러움)
EXPECTED = {
    "달걀": ("달걀", "계란"),
    "우유": ("우유",),
    "치즈": ("치즈",),
    "당근": ("당근",),
    "토마토": ("토마토",),
    "잎채소": ("상추", "양상추", "양배추", "배추", "청경채", "케일", "브로콜리"),
    "양파": ("양파",),
    "사과": ("사과",),
    "레몬": ("레몬",),
    "소고기": ("소고기", "쇠고기", "고기", "스테이크"),
    "닭고기": ("닭고기", "닭", "닭다리", "치킨"),
}
# 2단계 점검 조건과, 앱 필터와 따로 확인할 알레르기 단어
RECIPE_PREFS = dict(allergies=["달걀"], cuisine="korean", max_time_minutes=30, max_missing=2)
EGG_WORDS = ("달걀", "계란", "마요네즈", "메추리알", "에그")

results: list[tuple[str, str, str]] = []  # (기호, 항목, 설명)


def check(ok: bool | None, item: str, detail: str = "") -> None:
    mark = "✅" if ok else ("⚠️" if ok is None else "❌")
    results.append((mark, item, detail))
    print(f"  {mark} {item}" + (f" — {detail}" if detail else ""), flush=True)


class RecordingClient(OpenRouterClient):
    """요청마다 모델, 결과, 걸린 시간을 기록한다."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts: list[dict] = []

    def _post(self, payload, *, limit):
        start = time.monotonic()
        entry = {"model": payload.get("model"), "limit": limit}
        try:
            status, data = super()._post(payload, limit=limit)
            entry["result"] = status
            return status, data
        except AppError as e:
            entry["result"] = e.code
            raise
        finally:
            entry["seconds"] = round(time.monotonic() - start, 1)
            self.attempts.append(entry)


def short(model: str) -> str:
    return model.split("/")[-1].removesuffix(":free")


def print_attempts(client: RecordingClient, since: int) -> None:
    for i, a in enumerate(client.attempts[since:], 1):
        print(f"     시도 {i}: {short(a['model'])} → {a['result']} ({a['seconds']}초, 제한 {a['limit']:.0f}초)")


def fridge_photo() -> bytes:
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "seguiemj.ttf"
    if not font_path.exists():
        sys.exit("컬러 이모지 글꼴(seguiemj.ttf)이 없어 테스트 사진을 만들 수 없습니다. Windows에서 실행하세요.")
    img = Image.new("RGB", (3000, 2000), (238, 243, 246))
    d = ImageDraw.Draw(img)
    for y in (660, 1320):
        d.rectangle((0, y, 3000, y + 28), fill=(201, 211, 218))
    d.rectangle((15, 15, 2985, 1985), outline=(170, 182, 191), width=30)
    font = ImageFont.truetype(str(font_path), 400)
    for r, row in enumerate(FRIDGE_EMOJI):
        for c, emoji in enumerate(row):
            d.text((140 + c * 720, 130 + r * 660), emoji, font=font, embedded_color=True)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def matched_expected(names: list[str]) -> set[str]:
    found = set()
    for key, aliases in EXPECTED.items():
        if any(any(n.replace(" ", "").endswith(a) for a in aliases) for n in names):
            found.add(key)
    return found


def check_vision(client: RecordingClient) -> list[dict] | None:
    print("\n[1단계] 냉장고 사진 식재료 인식")
    catalog = client.free_vision_models()
    primary = config.vision_model()
    fallbacks = [m for m in config.fallback_vision_models() if m != primary and m in catalog]
    print(f"  기본 모델 {short(primary)}, 지금 쓸 수 있는 예비 모델 {[short(m) for m in fallbacks]}")
    check(primary in catalog, "기본 모델이 무료 이미지 모델 목록에 있음")

    since = len(client.attempts)
    events = []
    try:
        result = recognize_ingredients(
            fridge_photo(), client=client, model=primary, fallback_models=fallbacks,
            supports_json=lambda m: "response_format" in catalog.get(m, set()),
            on_retry=lambda a, w: events.append(f"429 등으로 {w}초 뒤 재시도"),
            on_fallback=lambda m: events.append(f"예비 모델 {short(m)}로 전환"),
        )
    except AppError as e:
        print_attempts(client, since)
        check(False, "인식 결과를 받음", f"{e.code} — 화면 안내: \"{e.message}\"")
        return None
    print_attempts(client, since)
    for ev in events:
        print(f"     · {ev}")

    names = [i.name for i in result.ingredients]
    check(True, "인식 결과를 받음", f"{short(result.model)}{' (예비 모델)' if result.fallback_used else ''}, {result.elapsed_ms / 1000:.1f}초")
    check(result.elapsed_ms <= config.VISION_DEADLINE_SECONDS * 1000, "전체 시간 제한(120초) 안에 끝남")
    check(result.is_food_image, "식재료 사진으로 판단함")
    print(f"     인식한 재료 {len(names)}개: " + ", ".join(f"{i.name}({i.quantity or '?'}{i.unit or ''}, {i.category})" for i in result.ingredients))

    suspicious = [n for n in names if is_suspicious_name(n)]
    check(not suspicious, "재료명이 깨지지 않음", f"깨진 이름: {suspicious}" if suspicious else "")
    wrong_cat = [i.name for i in result.ingredients if category_for(i.name) and category_for(i.name) != i.category]
    check(not wrong_cat, "분류가 사전과 일치", f"불일치: {wrong_cat}" if wrong_cat else "")

    found = matched_expected(names)
    missing = sorted(set(EXPECTED) - found)
    rate = len(found) / len(EXPECTED)
    check(rate >= 0.8, "정답 재료 인식률 80% 이상", f"{len(found)}/{len(EXPECTED)} ({rate:.0%})" + (f", 놓친 것: {missing}" if missing else ""))
    extra = [n for n in names if not matched_expected([n])]
    check(None if extra else True, "사진에 없는 재료를 지어내지 않음", f"정답 밖: {extra}" if extra else "")
    eggs = next((i for i in result.ingredients if i.name in ("달걀", "계란")), None)
    check(eggs is not None and eggs.quantity == 2, "같은 재료(달걀 2개)를 합쳐 수량을 셈", f"달걀 수량: {eggs.quantity if eggs else '없음'}")
    return [{"name": i.name, "quantity": i.quantity, "unit": i.unit, "category": i.category} for i in result.ingredients]


def check_recipe(client: RecordingClient, ingredients: list[dict]) -> None:
    prefs = Preferences(**RECIPE_PREFS)
    print("\n[2단계] 레시피 생성")
    print(f"  재료 {len(ingredients)}개: {', '.join(i['name'] for i in ingredients)}")
    print(f"  조건: 알레르기 {prefs.allergies}, {CUISINES[prefs.cuisine]}, {prefs.max_time_minutes}분 이내, 추가 구매 {prefs.max_missing}개까지")

    since = len(client.attempts)
    events = []
    try:
        result = generate_recipes(
            ingredients, prefs, [], client=client, model=config.text_model(),
            on_retry=lambda a, w: events.append(f"429 등으로 {w}초 뒤 재시도"),
        )
    except AppError as e:
        print_attempts(client, since)
        check(False, "레시피를 받음", f"{e.code} — 화면 안내: \"{e.message}\"")
        return
    print_attempts(client, since)
    for ev in events:
        print(f"     · {ev}")

    recipes = result.recipes
    requests = len(client.attempts) - since
    check(len(recipes) == config.RECIPE_COUNT, f"레시피 {config.RECIPE_COUNT}개를 받음", f"{len(recipes)}개, {result.elapsed_ms / 1000:.1f}초, 요청 {requests}회")
    check(None if result.rejected else True, "모델이 조건을 지킨 레시피만 냄", f"서버가 걸러 낸 것: {result.rejected}" if result.rejected else "")
    owned = {i["name"] for i in ingredients}
    for r in recipes:
        print(f"     - {r['title']} | {CUISINES.get(r['cuisine'], r['cuisine'])} | {r['time_minutes']}분 | 부족 {r['missing_ingredients']}")
        print("       재료: " + ", ".join(f"{i['name']} {i['amount']}" for i in r["ingredients"]))

    texts = {r["title"]: " ".join([r["title"]] + [i["name"] for i in r["ingredients"]] + [s["text"] for s in r["steps"]]) for r in recipes}
    egg_hits = {t: [w for w in EGG_WORDS if w in txt] for t, txt in texts.items()}
    egg_hits = {t: w for t, w in egg_hits.items() if w}
    check(not egg_hits, "알레르기(달걀) 재료가 없음", f"발견: {egg_hits}" if egg_hits else "")
    check(all(r["cuisine"] == prefs.cuisine for r in recipes), "모두 한식")
    over = [r["title"] for r in recipes if r["time_minutes"] and r["time_minutes"] > prefs.max_time_minutes * 1.2]
    check(not over, "조리 시간 30분(+20%) 이내", f"초과: {over}" if over else "")
    too_many = [r["title"] for r in recipes if len(r["missing_ingredients"]) > prefs.max_missing]
    check(not too_many, "추가로 살 재료 2개 이하", f"초과: {too_many}" if too_many else "")
    no_unit = [f"{r['title']}: {i['name']} {i['amount']!r}" for r in recipes for i in r["ingredients"] if re.fullmatch(r"[\d./\s]*", i["amount"])]
    check(not no_unit, "분량에 단위가 있음", f"단위 없음: {no_unit[:5]}" if no_unit else "")
    # 앱의 동의어 판정과 따로, 글자가 겹치는지만 본다. 겹치지 않으면(동의어 등) 사람이 확인하도록 ⚠️로 남긴다.
    flat_owned = [o.replace(" ", "") for o in owned]
    unsure_have = [f"{r['title']}: {i['name']}" for r in recipes for i in r["ingredients"]
                   if i["have"] and not i["is_pantry"]
                   and not any(n in o or o in n for o in flat_owned for n in [i["name"].replace(" ", "")])]
    check(None if unsure_have else True, "'보유'로 표시한 재료가 재료 목록과 글자로 일치", f"동의어 등 확인 필요: {unsure_have}" if unsure_have else "")
    check(all(r["steps"] for r in recipes), "모든 레시피에 조리 순서가 있음")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vision", action="store_true", help="1단계만")
    parser.add_argument("--recipe", action="store_true", help="2단계만 (정답 재료 목록 사용)")
    args = parser.parse_args()
    run_vision, run_recipe = (not args.recipe or args.vision), (not args.vision or args.recipe)

    api_key = config.get_api_key()
    if not api_key:
        sys.exit("OPENROUTER_API_KEY가 없습니다.")
    client = RecordingClient(api_key)
    print(f"점검 시각 {time.strftime('%Y-%m-%d %H:%M:%S')}")

    ingredients = check_vision(client) if run_vision else None
    if run_recipe:
        if ingredients is None:
            ingredients = [{"name": a[0], "quantity": None, "unit": None, "category": "기타"} for a in EXPECTED.values()]
            print("\n  (1단계 결과가 없어 정답 재료 목록으로 2단계를 점검합니다)")
        check_recipe(client, ingredients)

    ok = sum(m == "✅" for m, _, _ in results)
    warn = sum(m == "⚠️" for m, _, _ in results)
    fail = sum(m == "❌" for m, _, _ in results)
    print(f"\n요약: ✅ {ok}  ⚠️ {warn}  ❌ {fail}  · OpenRouter 요청 {len(client.attempts)}회")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
