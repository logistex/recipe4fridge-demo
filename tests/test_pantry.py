import pytest

from core.pantry import allergy_terms, canonical, find_allergens, is_pantry, owns, pantry_set, violates_diet


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("계란", "달걀"),
        ("다진 대파", "대파"),
        ("송송 썬 파", "대파"),
        ("마늘", "다진마늘"),
        ("다진 마늘", "다진마늘"),
        ("두부 (단단한 것)", "두부"),
        ("간장", "간장"),
        ("국간장", "국간장"),
    ],
)
def test_canonical(raw, expected):
    assert canonical(raw) == expected


@pytest.mark.parametrize(
    "recipe_name,owned,expected",
    [
        ("계란", {"달걀"}, True),
        ("김치", {"배추김치"}, True),  # 보유한 쪽이 더 구체적
        ("배추김치", {"김치"}, False),  # 반대 방향은 아님
        ("파", {"양파"}, False),  # 한 글자는 정확히 같을 때만
        ("다진 대파", {"대파"}, True),
        ("국간장", {"간장"}, False),
        ("고기", {"소고기"}, True),
        ("밥", {"달걀"}, False),
    ],
)
def test_owns(recipe_name, owned, expected):
    assert owns(recipe_name, {canonical(o) for o in owned}) is expected


def test_pantry():
    pantry = pantry_set()
    assert is_pantry("소금", pantry) and is_pantry("진간장", pantry) and is_pantry("마늘", pantry)
    assert not is_pantry("고추장", pantry)


def test_allergy_terms_expand_derived_foods():
    terms = allergy_terms(["계란", "새우"])
    assert {"달걀", "계란", "마요네즈", "새우"} <= terms


@pytest.mark.parametrize(
    "allergy,texts",
    [
        ("새우", ["김치찌개", "새우젓 약간을 넣는다"]),
        ("달걀", ["계란물을 입힌다"]),
        ("달걀", ["마요네즈 1큰술"]),
        ("우유", ["크림치즈"]),
        ("대두", ["간장 1큰술"]),
        ("게", ["게"]),
    ],
)
def test_find_allergens_catches_derived_foods(allergy, texts):
    assert find_allergens(texts, allergy_terms([allergy]))


@pytest.mark.parametrize(
    "allergy,texts",
    [
        ("게", ["게살 없이 만든 요리", "양배추 게"]),  # 한 글자는 재료명과 정확히 같을 때만 (오탐 방지)
        ("새우", ["김치볶음밥", "달걀 2개"]),
    ],
)
def test_find_allergens_avoids_false_positive(allergy, texts):
    assert not find_allergens(texts, allergy_terms([allergy]))


def test_unknown_allergy_is_matched_by_its_own_name():
    assert find_allergens(["망고 퓌레"], allergy_terms(["망고"]))


def test_violates_diet():
    assert violates_diet(["두부", "삼겹살"], ["채식"]) == "삼겹살"
    assert violates_diet(["두부", "멸치액젓"], ["채식"]) == "멸치액젓"
    assert violates_diet(["두부", "달걀"], ["채식"]) is None  # 채식은 달걀·유제품 허용
    assert violates_diet(["두부", "달걀"], ["비건"]) == "달걀"
    assert violates_diet(["삼겹살"], []) is None
