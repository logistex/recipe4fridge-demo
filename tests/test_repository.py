import pytest

import core.repository as repo
from core import auth
from core.errors import AppError


def recipe(title="달걀국", ingredients=("달걀", "대파"), minutes=15):
    return {
        "id": "tmp_x", "title": title, "summary": "요약", "cuisine": "korean", "servings": 2,
        "time_minutes": minutes, "difficulty": "easy",
        "ingredients": [{"name": n, "amount": "1개", "have": True, "is_pantry": False} for n in ingredients],
        "missing_ingredients": [], "usage_ratio": 1.0,
        "steps": [{"order": 1, "text": "끓인다.", "timer_seconds": 60}, {"order": 2, "text": "담는다.", "timer_seconds": None}],
        "tips": "",
    }


@pytest.fixture
def users(engine):
    a = auth.sign_up(engine, "user_aaa", "abcd1234", "abcd1234", "에이")
    b = auth.sign_up(engine, "user_bbb", "abcd1234", "abcd1234", "비이")
    return a, b


# --- 프로필 ------------------------------------------------------------------------------

def test_update_profile_cleans_values(engine, users):
    a, _ = users
    saved = repo.update_profile(engine, a, {
        "nickname": " 요리왕 ", "allergies": ["새우", "새우", " 땅콩 ", ""], "diet": ["채식"], "disliked": ["고수"],
        "skill_level": "beginner", "default_servings": 3, "cuisines": ["korean", "martian"],
    })
    assert saved["allergies"] == ["새우", "땅콩"] and saved["cuisines"] == ["korean"]
    prof = repo.get_profile(engine, a)
    assert (prof["nickname"], prof["skill_level"], prof["default_servings"], prof["disliked"]) == ("요리왕", "beginner", 3, ["고수"])


@pytest.mark.parametrize("bad", [{"nickname": "김"}, {"skill_level": "chef"}, {"default_servings": 9}])
def test_update_profile_rejects_invalid(engine, users, bad):
    data = {"nickname": "요리왕", "skill_level": "normal", "default_servings": 2} | bad
    with pytest.raises(AppError):
        repo.update_profile(engine, users[0], data)


# --- 저장 --------------------------------------------------------------------------------

def test_save_and_duplicate_detection(engine, users):
    a, b = users
    rid = repo.save_recipe(engine, a, recipe(), {"ingredients": []}, "m")
    saved = repo.get_recipe(engine, a, rid)
    assert "id" not in saved["recipe"] and saved["original"] == saved["recipe"]
    with pytest.raises(AppError) as exc:  # 재료 순서·표기가 달라도 같은 레시피
        repo.save_recipe(engine, a, recipe(ingredients=("대파", "계란")), {}, "m")
    assert exc.value.code == "ALREADY_SAVED"
    assert repo.save_recipe(engine, b, recipe(), {}, "m")  # 다른 사용자는 저장할 수 있음
    assert repo.dedupe_key(recipe()) in repo.saved_keys(engine, a)


def test_save_limit(engine, users, monkeypatch):
    monkeypatch.setattr(repo, "MAX_SAVED", 2)
    repo.save_recipe(engine, users[0], recipe("가"), {}, "m")
    repo.save_recipe(engine, users[0], recipe("나"), {}, "m")
    with pytest.raises(AppError) as exc:
        repo.save_recipe(engine, users[0], recipe("다"), {}, "m")
    assert exc.value.code == "SAVE_LIMIT"


def test_save_rejects_invalid_or_huge_recipe(engine, users):
    with pytest.raises(AppError):
        repo.save_recipe(engine, users[0], {"title": "빈 레시피"}, {}, "m")
    huge = recipe() | {"tips": "가" * 70000}
    with pytest.raises(AppError):
        repo.save_recipe(engine, users[0], huge, {}, "m")


def test_list_sort_search_favorite_and_paging(engine, users):
    a, b = users
    r1 = repo.save_recipe(engine, a, recipe("김치전", ("김치", "밀가루"), 25), {}, "m")
    r2 = repo.save_recipe(engine, a, recipe("달걀국", ("달걀",), 10), {}, "m")
    r3 = repo.save_recipe(engine, a, recipe("두부조림", ("두부",), 20), {}, "m")
    repo.save_recipe(engine, b, recipe("남의 레시피", ("김치",)), {}, "m")
    repo.update_recipe(engine, a, r1, rating=5, is_favorite=True)
    repo.update_recipe(engine, a, r3, rating=3)

    titles = lambda **kw: [r["title"] for r in repo.list_recipes(engine, a, **kw)[0]]  # noqa: E731
    assert titles() == ["두부조림", "달걀국", "김치전"]
    assert titles(sort="rating") == ["김치전", "두부조림", "달걀국"]
    assert titles(sort="time") == ["달걀국", "두부조림", "김치전"]
    assert titles(favorite_only=True) == ["김치전"]
    assert titles(query="김치") == ["김치전"]  # 다른 사용자의 레시피는 안 나옴
    assert titles(query="두부") == ["두부조림"]  # 재료명 검색
    assert titles(query="%") == []  # LIKE 특수 문자는 글자 그대로 찾음
    rows, total = repo.list_recipes(engine, a, limit=2)
    assert len(rows) == 2 and total == 3


def test_other_users_recipes_are_untouchable(engine, users):
    a, b = users
    rid = repo.save_recipe(engine, a, recipe(), {}, "m")
    assert repo.get_recipe(engine, b, rid) is None
    with pytest.raises(AppError):
        repo.update_recipe(engine, b, rid, memo="남의 메모")
    with pytest.raises(AppError):
        repo.update_recipe(engine, b, rid, title="바꿈")
    with pytest.raises(AppError):
        repo.restore_recipe(engine, b, rid)
    assert repo.delete_recipe(engine, b, rid) is False
    assert repo.get_recipe(engine, a, rid)["memo"] is None


def test_edit_and_restore(engine, users):
    a, _ = users
    rid = repo.save_recipe(engine, a, recipe(), {}, "m")
    repo.update_recipe(engine, a, rid, title="내 달걀국", steps=["물을 끓인다.", "", "달걀을 푼다.", "간한다."])
    edited = repo.get_recipe(engine, a, rid)
    assert edited["title"] == "내 달걀국"
    assert [s["text"] for s in edited["recipe"]["steps"]] == ["물을 끓인다.", "달걀을 푼다.", "간한다."]
    assert edited["recipe"]["steps"][0]["timer_seconds"] == 60
    repo.restore_recipe(engine, a, rid)
    restored = repo.get_recipe(engine, a, rid)
    assert restored["title"] == "달걀국" and len(restored["recipe"]["steps"]) == 2


def test_memo_and_rating_bounds(engine, users):
    a, _ = users
    rid = repo.save_recipe(engine, a, recipe(), {}, "m")
    with pytest.raises(AppError):
        repo.update_recipe(engine, a, rid, memo="가" * 1001)
    repo.update_recipe(engine, a, rid, memo="  간장 조금  ", rating=9)
    row = repo.get_recipe(engine, a, rid)
    assert row["memo"] == "간장 조금" and row["rating"] is None


def test_delete_recipe(engine, users):
    rid = repo.save_recipe(engine, users[0], recipe(), {}, "m")
    assert repo.delete_recipe(engine, users[0], rid) is True
    assert repo.get_recipe(engine, users[0], rid) is None
