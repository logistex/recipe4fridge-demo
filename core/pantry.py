"""레시피 재료 판정: 기본 양념, 동의어, 보유 여부, 알레르기 파생어, 채식 조건.

모델이 표시한 "보유 여부"나 알레르기 준수는 믿지 않고 여기서 다시 판정한다(PRD F2-5, F2-7).
"""

import re

from core.ingredient_names import category_for

DEFAULT_PANTRY = ("소금", "후추", "설탕", "식용유", "물", "간장", "참기름", "다진 마늘")

# 같은 재료의 다른 이름 → 대표 이름
_SYNONYM_GROUPS = [
    ("달걀", "계란"),
    ("대파", "파"),
    ("소고기", "쇠고기"),
    ("닭고기", "닭"),
    ("다진마늘", "마늘"),
    ("고춧가루", "고추가루"),
    ("후추", "후춧가루"),
    ("간장", "진간장", "양조간장"),
    ("식용유", "카놀라유", "포도씨유", "콩기름"),
    ("요거트", "요구르트"),
    ("케첩", "케찹"),
    ("밥", "쌀밥", "공기밥"),
    ("양상추", "상추"),  # 냉장고 사진에서는 둘을 잘 구분하지 못한다
]
SYNONYMS = {name: group[0] for group in _SYNONYM_GROUPS for name in group}

# 레시피 재료명 앞에 붙는 손질법. 떼어 내야 "다진 대파"가 보유한 "대파"와 맞는다.
_PREP_WORDS = (
    "다진", "채썬", "채 썬", "송송 썬", "얇게 썬", "잘게 썬", "깍둑 썬", "어슷 썬", "썬", "삶은", "익힌", "볶은",
    "데친", "손질한", "불린", "으깬", "간", "구운", "냉동", "신선한", "생",
)
_PREP_RE = re.compile(r"^(?:(?:" + "|".join(sorted(map(re.escape, _PREP_WORDS), key=len, reverse=True)) + r")\s+)+")

# 알레르기 → 그 재료가 들어 있는 식품 이름 (포함 여부로 대조한다)
ALLERGY_TERMS = {
    "달걀": ("달걀", "계란", "메추리알", "마요네즈", "에그"),
    "우유": ("우유", "치즈", "버터", "생크림", "요거트", "요구르트", "크림", "연유", "분유"),
    "밀": ("밀가루", "빵", "국수", "파스타", "스파게티", "부침가루", "튀김가루", "라면", "우동", "소면", "만두", "간장"),
    "대두": ("콩", "두부", "된장", "두유", "유부", "청국장", "간장", "고추장", "쌈장"),
    "땅콩": ("땅콩", "피넛"),
    "견과류": ("호두", "아몬드", "잣", "땅콩", "캐슈", "피스타치오", "마카다미아"),
    "새우": ("새우", "크릴", "칵테일새우"),
    "게": ("게", "꽃게", "대게", "맛살", "게맛살"),
    "갑각류": ("새우", "게", "가재", "랍스터", "크릴"),
    "조개": ("조개", "바지락", "홍합", "굴", "전복", "가리비", "모시조개"),
    "생선": ("생선", "고등어", "연어", "참치", "멸치", "대구", "명태", "동태", "황태", "갈치", "꽁치", "삼치", "액젓"),
    "오징어": ("오징어", "한치"),
    "돼지고기": ("돼지고기", "삼겹살", "목살", "베이컨", "햄", "소시지", "스팸", "돈육"),
    "소고기": ("소고기", "쇠고기", "차돌", "불고기", "우삼겹"),
    "닭고기": ("닭", "치킨"),
    "복숭아": ("복숭아",),
    "토마토": ("토마토", "케첩"),
}
_ALLERGY_ALIASES = {"계란": "달걀", "쇠고기": "소고기", "닭": "닭고기", "밀가루": "밀", "콩": "대두", "갑각류": "갑각류"}

VEGETARIAN_EXCLUDED_CATEGORIES = {"육류", "해산물"}
VEGAN_EXCLUDED_CATEGORIES = VEGETARIAN_EXCLUDED_CATEGORIES | {"유제품·달걀"}
VEGAN_EXCLUDED_WORDS = ("꿀", "젓", "액젓", "버터", "치즈", "우유", "마요네즈", "멸치", "가쓰오")
VEGETARIAN_EXCLUDED_WORDS = ("젓", "액젓", "멸치", "가쓰오", "굴소스", "베이컨", "햄")


def canonical(name: str) -> str:
    """비교용 이름: 괄호 내용·손질법 제거, 공백 제거, 동의어를 대표 이름으로."""
    name = re.sub(r"\(.*?\)|\[.*?\]", " ", name or "").strip()
    name = _PREP_RE.sub("", name)
    key = re.sub(r"\s+", "", name)
    return SYNONYMS.get(key, key)


def owns(recipe_name: str, owned: set[str]) -> bool:
    """레시피 재료를 가지고 있는가.

    대표 이름이 같거나, 보유한 재료 이름이 레시피 재료 이름으로 끝나면(보유한 쪽이 더 구체적) 가진 것으로 본다.
    예: 레시피 "김치" ← 보유 "배추김치". 한 글자 이름은 다른 말에 섞이기 쉬워서(파 ⊂ 양파) 정확히 같을 때만.
    """
    key = canonical(recipe_name)
    if not key:
        return False
    if key in owned:
        return True
    return len(key) >= 2 and any(o.endswith(key) for o in owned)


def is_pantry(recipe_name: str, pantry: set[str]) -> bool:
    return canonical(recipe_name) in pantry


def pantry_set(items=DEFAULT_PANTRY) -> set[str]:
    return {canonical(i) for i in items}


def allergy_terms(allergies) -> set[str]:
    """알레르기 목록을 실제로 대조할 단어들로 넓힌다. 사전에 없는 알레르기는 그 이름 자체로 대조한다."""
    terms = set()
    for allergy in allergies:
        key = canonical(allergy)
        if not key:
            continue
        key = _ALLERGY_ALIASES.get(key, key)
        terms.add(key)
        for t in ALLERGY_TERMS.get(key, ()):  # 대표 이름과 원래 이름을 모두 넣어야 "계란물"도 걸러진다
            terms.update((canonical(t), re.sub(r"\s+", "", t)))
        terms.update(name for name, rep in SYNONYMS.items() if rep == key)
    return {t for t in terms if t}


def find_allergens(texts, terms: set[str]) -> set[str]:
    """레시피 글(재료명, 제목, 조리 순서)에 들어 있는 알레르기 단어. 한 글자 단어(게, 굴, 콩)는 재료명과 정확히 같을 때만."""
    found = set()
    for text in texts:
        flat = re.sub(r"\s+", "", text or "")
        key = canonical(text or "")
        for term in terms:
            if (len(term) >= 2 and term in flat) or term == key:
                found.add(term)
    return found


def violates_diet(ingredient_names, diet) -> str | None:
    """채식·비건 조건을 어기는 재료가 있으면 그 재료명을 돌려준다."""
    diet = set(diet)
    if "비건" in diet:
        categories, words = VEGAN_EXCLUDED_CATEGORIES, VEGAN_EXCLUDED_WORDS
    elif "채식" in diet:
        categories, words = VEGETARIAN_EXCLUDED_CATEGORIES, VEGETARIAN_EXCLUDED_WORDS
    else:
        return None
    for name in ingredient_names:
        key = canonical(name)
        if category_for(key) in categories or any(w in key for w in words):
            return name
    return None
