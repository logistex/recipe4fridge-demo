"""Streamlit AppTest로 2단계 화면 흐름을 확인한다. 실제 모델은 부르지 않는다."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import core.config
import core.recipe_gen
from core.errors import MESSAGES, AppError
from core.recipe_gen import RecipeResult
from core.runtime import get_daily_limiter

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")
RECIPES_PAGE = "app_pages/recipes.py"
INGREDIENTS = [
    {"name": "달걀", "quantity": 6, "unit": "개", "category": "유제품·달걀"},
    {"name": "대파", "quantity": None, "unit": None, "category": "채소"},
]


def recipe(title, rid, missing=()):
    return {
        "id": rid, "title": title, "summary": "[링크](http://evil.example) 요약", "cuisine": "korean", "servings": 2,
        "time_minutes": 15, "difficulty": "easy",
        "ingredients": [
            {"name": "달걀", "amount": "2개", "have": True, "is_pantry": False},
            {"name": "소금", "amount": "약간", "have": True, "is_pantry": True},
        ] + [{"name": m, "amount": "1개", "have": False, "is_pantry": False} for m in missing],
        "missing_ingredients": list(missing), "usage_ratio": 0.5 if missing else 1.0,
        "steps": [{"order": 1, "text": "달걀을 푼다.", "timer_seconds": None}, {"order": 2, "text": "끓인다.", "timer_seconds": 300}],
        "tips": "약불로.",
    }


class FakeGenerate:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, ingredients, prefs, exclude_titles, **kwargs):
        self.calls.append({"prefs": prefs, "exclude": list(exclude_titles)})
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(core.config, "get_api_key", lambda: "test-key")
    get_daily_limiter.clear()


def open_recipes(ingredients=INGREDIENTS):
    at = AppTest.from_file(APP, default_timeout=15)
    if ingredients is not None:
        at.session_state["confirmed_ingredients"] = ingredients
    return at.switch_page(RECIPES_PAGE).run()


def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_without_ingredients_guides_to_step1():
    at = open_recipes(ingredients=None)
    assert any("냉장고 사진으로 재료를 찾아" in i.value for i in at.info)
    button(at, "냉장고 재료 찾기로 가기").click().run()
    assert at.title[0].value == "냉장고 재료 찾기"


def test_generate_shows_recipe_cards(monkeypatch):
    fake = FakeGenerate(RecipeResult([recipe("달걀국", "tmp_a"), recipe("볶음밥", "tmp_b", missing=["밥"])], "m", 1, {"allergy": 1}))
    monkeypatch.setattr(core.recipe_gen, "generate_recipes", fake)
    at = open_recipes()
    assert "달걀 6개, 대파" in at.markdown[0].value.replace("\\", "")
    button(at, "레시피 추천받기").click().run()

    assert not at.exception
    assert len(fake.calls) == 1 and fake.calls[0]["exclude"] == []
    headings = [m.value for m in at.markdown if m.value.startswith("####")]
    assert headings == ["#### 달걀국", "#### 볶음밥"]
    assert any("추가로 필요: 밥" in m.value for m in at.markdown)
    assert any("알레르기 재료가 들어 있음 1개" in c.value for c in at.caption)
    assert not any("](http" in m.value for m in at.markdown)  # 모델 글의 링크 문법은 이스케이프됨


def test_checkbox_and_expander_do_not_call_model_again(monkeypatch):
    fake = FakeGenerate(RecipeResult([recipe("달걀국", "tmp_a")], "m", 1))
    monkeypatch.setattr(core.recipe_gen, "generate_recipes", fake)
    at = open_recipes()
    button(at, "레시피 추천받기").click().run()
    at.checkbox(key="step_tmp_a_1").check().run()
    at.run()
    assert len(fake.calls) == 1
    assert at.checkbox(key="step_tmp_a_1").value is True


def test_more_recipes_excludes_shown_titles(monkeypatch):
    fake = FakeGenerate(
        RecipeResult([recipe("달걀국", "tmp_a")], "m", 1),
        RecipeResult([recipe("파전", "tmp_c")], "m", 1),
    )
    monkeypatch.setattr(core.recipe_gen, "generate_recipes", fake)
    at = open_recipes()
    button(at, "레시피 추천받기").click().run()
    button(at, "다른 레시피 보기").click().run()
    assert fake.calls[1]["exclude"] == ["달걀국"]
    assert [m.value for m in at.markdown if m.value.startswith("####")] == ["#### 파전"]


def test_preferences_are_passed(monkeypatch):
    fake = FakeGenerate(RecipeResult([recipe("달걀국", "tmp_a")], "m", 1))
    monkeypatch.setattr(core.recipe_gen, "generate_recipes", fake)
    at = open_recipes()
    at.number_input(key="pref_servings").set_value(4)
    at.segmented_control(key="pref_time").set_value("30분")
    at.multiselect(key="pref_allergies").set_value(["새우"])
    at.run()
    button(at, "레시피 추천받기").click().run()
    prefs = fake.calls[0]["prefs"]
    assert (prefs.servings, prefs.max_time_minutes, prefs.allergies) == (4, 30, ["새우"])


def test_changed_preferences_prompt_regeneration(monkeypatch):
    monkeypatch.setattr(core.recipe_gen, "generate_recipes", FakeGenerate(RecipeResult([recipe("달걀국", "tmp_a")], "m", 1)))
    at = open_recipes()
    button(at, "레시피 추천받기").click().run()
    at.number_input(key="pref_servings").set_value(3).run()
    assert any("조건이 바뀌었어요" in i.value for i in at.info)


def test_empty_result_shows_hint(monkeypatch):
    monkeypatch.setattr(core.recipe_gen, "generate_recipes", FakeGenerate(RecipeResult([], "m", 1, {"missing": 3})))
    at = open_recipes()
    button(at, "레시피 추천받기").click().run()
    assert any("조건에 맞는 레시피를 찾지 못했어요" in w.value for w in at.warning)


def test_model_error_is_shown(monkeypatch):
    monkeypatch.setattr(core.recipe_gen, "generate_recipes", FakeGenerate(AppError("MODEL_BUSY")))
    at = open_recipes()
    button(at, "레시피 추천받기").click().run()
    assert any(MESSAGES["MODEL_BUSY"] in e.value for e in at.error)
    assert not button(at, "레시피 추천받기").disabled
