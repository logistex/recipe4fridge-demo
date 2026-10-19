"""화면의 선택지 (2단계 조건, 3단계 프로필이 함께 씀)."""

TIME_OPTIONS = {"15분": 15, "30분": 30, "60분": 60, "제한 없음": None}
DIFFICULTY_OPTIONS = {"쉬움": "easy", "보통": "normal", "상관없음": None}
CUISINE_OPTIONS = {"한식": "korean", "양식": "western", "중식": "chinese", "일식": "japanese", "상관없음": None}
MISSING_OPTIONS = {"허용 안 함": 0, "2개까지": 2, "상관없음": None}
DIET_OPTIONS = ["채식", "비건", "글루텐 제외"]
ALLERGY_OPTIONS = [
    "달걀", "우유", "밀", "대두", "땅콩", "견과류", "새우", "게", "조개", "생선", "오징어",
    "돼지고기", "소고기", "닭고기", "복숭아", "토마토",
]
SKILL_OPTIONS = {"초보": "beginner", "보통": "normal", "능숙": "expert"}
