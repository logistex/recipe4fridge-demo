import pytest

from core.ingredient_names import CATEGORY_BY_NAME, category_for, is_suspicious_name
from core.vision import CATEGORIES, normalize_ingredients


@pytest.mark.parametrize(
    "name,category",
    [
        ("달걀", "유제품·달걀"),
        ("우유", "유제품·달걀"),
        ("저지방 우유", "유제품·달걀"),
        ("배추김치", "반찬·가공식품"),
        ("고추장", "양념·소스"),
        ("청양고추", "채소"),
        ("참치캔", "반찬·가공식품"),  # "참치"(해산물)보다 긴 말이 먼저 맞음
        ("참치", "해산물"),
        ("토마토소스", "양념·소스"),
        ("방울토마토", "채소"),
        ("오렌지주스", "음료"),
        ("배", "과일"),
    ],
)
def test_category_dictionary(name, category):
    assert category_for(name) == category


@pytest.mark.parametrize("name", ["배즙", "생닭", "무언가", "알 수 없는 반찬"])
def test_one_letter_words_match_only_exactly_and_unknown_is_none(name):
    assert category_for(name) is None


def test_dictionary_uses_only_known_categories():
    assert set(CATEGORY_BY_NAME.values()) <= set(CATEGORIES)


@pytest.mark.parametrize("name", ["달strand", "egg", "牛乳", "치즈x", "моloko"])
def test_mixed_scripts_are_suspicious(name):
    assert is_suspicious_name(name)


@pytest.mark.parametrize("name", ["달걀", "저지방 우유", "닭고기(다리)", "1등급 한우", "모짜렐라·체다 치즈"])
def test_normal_korean_names_are_fine(name):
    assert not is_suspicious_name(name)


def test_normalize_fixes_category_and_flags_garbled_name():
    items = [
        {"name": "달strand", "quantity": 2, "unit": "개", "category": "기타", "confidence": "high"},
        {"name": "우유", "quantity": 1, "unit": "개", "category": "기타", "confidence": "high"},
        {"name": "수상한 소스병", "quantity": 1, "unit": "병", "category": "기타", "confidence": "medium"},
        {"name": "브리오슈", "quantity": 1, "unit": "개", "category": "곡물·면", "confidence": "high"},
    ]
    result = {i.name: i for i in normalize_ingredients(items)}
    assert result["달strand"].name_suspect and result["달strand"].confidence == "low"
    assert result["우유"].category == "유제품·달걀" and not result["우유"].name_suspect
    assert result["수상한 소스병"].category == "기타"  # 끝말이 "소스병"이라 사전에 없음 → 모델 값 유지
    assert result["브리오슈"].category == "곡물·면"  # 사전에 없으면 모델 분류를 그대로 씀
