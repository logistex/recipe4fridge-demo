"""2단계 화면 흐름: 같은 입력은 다시 생성하지 않고, 요청 한도를 확인한 뒤에만 모델을 부른다(PRD F2-12)."""

import hashlib
import json
from collections.abc import Callable, MutableMapping
from dataclasses import asdict

from core.errors import AppError
from core.recipe_gen import Preferences, RecipeResult
from core.usage import DailyLimiter, check_session_rate

CACHE_SIZE = 5


def input_key(ingredients, prefs: Preferences, exclude_titles) -> str:
    data = {"ingredients": ingredients, "prefs": asdict(prefs), "exclude": list(exclude_titles)}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def request_recipes(
    state: MutableMapping,
    ingredients: list[dict],
    prefs: Preferences,
    exclude_titles: list[str],
    *,
    generate: Callable[..., RecipeResult],
    limiter: DailyLimiter,
    per_minute: int,
) -> dict:
    """생성 결과(dict)를 state["recipe_result"]에, 입력을 state["recipe_input"]에 두고 결과를 돌려준다."""
    key = input_key(ingredients, prefs, exclude_titles)
    cache: dict = state.setdefault("recipe_cache", {})
    result = cache.get(key)
    if result is None:
        if not check_session_rate(state, per_minute):
            raise AppError("RATE_LIMITED")
        if not limiter.try_acquire():
            raise AppError("DAILY_LIMIT")
        result = generate(ingredients, prefs, exclude_titles).to_dict()
        cache[key] = result
        while len(cache) > CACHE_SIZE:
            cache.pop(next(iter(cache)))
    state["recipe_result"] = result
    state["recipe_input"] = {"ingredients": ingredients, "preferences": asdict(prefs), "exclude_titles": list(exclude_titles)}
    return result
