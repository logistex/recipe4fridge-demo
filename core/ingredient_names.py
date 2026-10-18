"""재료명 검사와 흔한 재료의 분류 사전.

모델이 재료명을 깨뜨리거나("달strand") 분류를 틀리는("달걀 → 기타") 경우를 바로잡는다.
"""

import unicodedata

# 흔한 재료 → 분류. 모델이 준 분류보다 이 사전을 믿는다.
# 2글자 이상 이름은 끝부분이 같으면 맞는 것으로 본다("배추김치" → 김치, "저지방 우유" → 우유).
# 1글자 이름(배, 무, 파 …)은 다른 말에 섞이기 쉬워서 정확히 같을 때만 쓴다.
_CATEGORY_WORDS = {
    "채소": """양파 대파 쪽파 파 마늘 생강 당근 감자 고구마 무 배추 양배추 상추 양상추 깻잎 시금치 브로콜리
        오이 호박 가지 토마토 파프리카 피망 고추 버섯 콩나물 숙주 부추 미나리 셀러리 아스파라거스
        옥수수 연근 우엉 비트 케일 청경채 단호박 샐러드""",
    "과일": """사과 배 귤 오렌지 레몬 라임 바나나 딸기 포도 블루베리 키위 수박 참외 멜론 복숭아 자두 망고
        파인애플 아보카도 체리 감 석류 자몽 한라봉""",
    "육류": """고기 소고기 쇠고기 돼지고기 닭고기 닭 닭다리 닭가슴살 닭봉 삼겹살 목살 갈비 다짐육 베이컨
        오리고기 양고기 차돌박이 불고기 스테이크""",
    "해산물": """생선 고등어 연어 참치 새우 오징어 문어 조개 바지락 홍합 굴 게 꽃게 멸치 황태 명태 동태 대구
        갈치 전복 미역 다시마 낙지 주꾸미 꽁치 삼치""",
    "유제품·달걀": """달걀 계란 메추리알 우유 치즈 버터 요거트 요구르트 생크림 크림치즈 모짜렐라""",
    "곡물·면": """쌀 밥 현미 찹쌀 밀가루 부침가루 튀김가루 빵 식빵 떡 국수 라면 소면 우동 파스타 스파게티
        당면 오트밀 시리얼 또띠아""",
    "양념·소스": """간장 된장 고추장 쌈장 케첩 마요네즈 머스터드 굴소스 식초 설탕 소금 후추 참기름 들기름 식용유
        올리브유 고춧가루 맛술 물엿 올리고당 꿀 잼 드레싱 소스 액젓 새우젓 와사비""",
    "반찬·가공식품": """김치 깍두기 단무지 두부 어묵 햄 소시지 스팸 참치캔 만두 피클 장아찌 젓갈 김 유부 맛살""",
    "음료": """주스 콜라 사이다 탄산수 맥주 와인 소주 막걸리 물 생수 커피 차 두유 이온음료""",
}

CATEGORY_BY_NAME: dict[str, str] = {
    word: category for category, words in _CATEGORY_WORDS.items() for word in words.split()
}
_SUFFIX_WORDS = sorted((w for w in CATEGORY_BY_NAME if len(w) >= 2), key=len, reverse=True)

ALLOWED_NAME_SYMBOLS = set(" ·()-,")


def category_for(name: str) -> str | None:
    """사전에 있는 재료면 분류를, 없으면 None을 돌려준다."""
    key = name.replace(" ", "")
    if key in CATEGORY_BY_NAME:
        return CATEGORY_BY_NAME[key]
    for word in _SUFFIX_WORDS:  # 긴 말부터 확인해야 "참치캔"이 "참치"보다 먼저 맞는다
        if key.endswith(word):
            return CATEGORY_BY_NAME[word]
    return None


def is_suspicious_name(name: str) -> bool:
    """한글 재료명에 영문·한자 등 다른 문자가 섞였으면 모델이 이름을 깨뜨렸을 가능성이 높다."""
    for ch in name:
        if ch.isdigit() or ch in ALLOWED_NAME_SYMBOLS:
            continue
        if not unicodedata.name(ch, "").startswith("HANGUL"):
            return True
    return False
