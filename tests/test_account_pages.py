"""Streamlit AppTest로 3단계 화면(로그인, 프로필, 저장, 내 레시피)을 확인한다. DB는 메모리 SQLite."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import core.config
import core.recipe_gen
import core.session
from core import auth, repository
from core.recipe_gen import RecipeResult
from core.runtime import _engine, get_daily_limiter

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")
INGREDIENTS = [{"name": "달걀", "quantity": 6, "unit": "개", "category": "유제품·달걀"}]


def recipe(title="달걀국", rid="tmp_a"):
    return {
        "id": rid, "title": title, "summary": "요약", "cuisine": "korean", "servings": 2, "time_minutes": 15,
        "difficulty": "easy", "ingredients": [{"name": "달걀", "amount": "2개", "have": True, "is_pantry": False}],
        "missing_ingredients": [], "usage_ratio": 1.0,
        "steps": [{"order": 1, "text": "끓인다.", "timer_seconds": None}], "tips": "",
    }


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(core.config, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(core.session, "cookie_token", lambda: None)
    get_daily_limiter.clear()


@pytest.fixture
def db():
    return _engine("sqlite://")  # 앱이 쓰는 것과 같은 메모리 DB


def logged_in_as(monkeypatch, db, username="cook_kim", nickname="김요리"):
    """쿠키에 세션 토큰이 있는 상태(새로고침 후)를 흉내 낸다."""
    user_id = auth.sign_up(db, username, "abcd1234", "abcd1234", nickname)
    token = auth.create_session(db, user_id)
    monkeypatch.setattr(core.session, "cookie_token", lambda: token)
    return user_id, token


def text_input(at, label, nth=0):
    return [t for t in at.text_input if t.label == label][nth]


def button(at, label):
    return next(b for b in at.button if b.label == label)


def sidebar_text(at):
    return " ".join(m.value for m in at.sidebar.markdown) + " ".join(c.value for c in at.sidebar.caption)


def open_page(page=None, **state):
    at = AppTest.from_file(APP, default_timeout=20)
    for k, v in state.items():
        at.session_state[k] = v
    if page:
        at.switch_page(page)
    return at.run()


# --- 가입·로그인·로그아웃 ---------------------------------------------------------------------

def test_sign_up_logs_in_sets_cookie_and_opens_profile(db):
    at = open_page("app_pages/login.py")
    assert at.title[0].value == "로그인"
    text_input(at, "아이디", 1).input("new_cook")
    text_input(at, "비밀번호", 1).input("abcd1234")
    text_input(at, "비밀번호 확인").input("abcd1234")
    text_input(at, "닉네임").input("새요리사")
    button(at, "가입하기").click().run()

    assert not at.exception
    assert at.title[0].value == "프로필"
    assert "새요리사" in sidebar_text(at) and "아이디로 로그인" in sidebar_text(at)
    token = at.session_state["auth_token"]
    assert auth.user_id_from_session(db, token) is not None
    cookie_scripts = [h.proto.body for h in at.get("html")]
    assert any("r4f_session=" + token in body and "max-age=1209600" in body for body in cookie_scripts)


def test_sign_up_error_is_shown(db):
    at = open_page("app_pages/login.py")
    text_input(at, "아이디", 1).input("ab")
    button(at, "가입하기").click().run()
    assert any("아이디는 4~20자" in e.value for e in at.error)


def test_login_failure_message_is_generic(db):
    auth.sign_up(db, "cook_kim", "abcd1234", "abcd1234", "김요리")
    at = open_page("app_pages/login.py")
    text_input(at, "아이디").input("cook_kim")
    text_input(at, "비밀번호").input("wrong1234")
    button(at, "로그인").click().run()
    assert any(e.value == "아이디 또는 비밀번호가 올바르지 않아요." for e in at.error)


def test_login_then_logout(db):
    auth.sign_up(db, "cook_kim", "abcd1234", "abcd1234", "김요리")
    at = open_page("app_pages/login.py")
    text_input(at, "아이디").input("cook_kim")
    text_input(at, "비밀번호").input("abcd1234")
    button(at, "로그인").click().run()
    token = at.session_state["auth_token"]
    assert at.title[0].value == "냉장고 재료 찾기" and "김요리" in sidebar_text(at)

    at.sidebar.button[0].click().run()  # 로그아웃
    assert "auth_token" not in at.session_state and at.session_state["user"] is None
    assert auth.user_id_from_session(db, token) is None  # DB 세션도 지움
    assert any("r4f_session=; path=/; max-age=0" in h.proto.body for h in at.get("html"))  # 쿠키도 지움


def test_cookie_session_keeps_login_after_reload(monkeypatch, db):
    logged_in_as(monkeypatch, db)
    at = open_page()
    assert "김요리" in sidebar_text(at)
    at.switch_page("app_pages/my_recipes.py").run()  # 로그인해야 등록되는 페이지가 열림
    assert at.title[0].value == "내 레시피"


def test_expired_or_unknown_cookie_is_ignored(monkeypatch, db):
    monkeypatch.setattr(core.session, "cookie_token", lambda: "forged-token")
    at = open_page()
    assert at.session_state["user"] is None
    with pytest.raises(Exception):
        at.switch_page("app_pages/my_recipes.py").run()  # 로그아웃 상태에서는 등록되지 않은 페이지


def test_google_identity_creates_google_account(monkeypatch, db):
    monkeypatch.setattr(core.session, "google_identity", lambda: {"sub": "g-1", "email": "g@example.com", "name": "구글러"})
    at = open_page()
    assert "구글러" in sidebar_text(at) and "Google로 로그인" in sidebar_text(at)
    assert at.session_state["user"].method == "google"


def test_google_tab_explains_when_not_configured(db):
    at = open_page("app_pages/login.py")
    assert any("Google 로그인이 아직 설정되지 않았어요" in i.value for i in at.info)


def test_database_failure_is_shown_and_steps_1_2_still_work(monkeypatch):
    monkeypatch.setattr(core.config, "database_url", lambda: "postgresql+psycopg://nobody@127.0.0.1:1/none?connect_timeout=2")
    _engine.clear()
    at = open_page()
    assert not at.exception
    assert at.title[0].value == "냉장고 재료 찾기"
    assert any("저장소 연결 실패" in e.value for e in at.sidebar.error)


# --- 저장과 내 레시피 ---------------------------------------------------------------------------

def result_state():
    return {
        "confirmed_ingredients": INGREDIENTS,
        "recipe_result": RecipeResult([recipe()], "m", 1).to_dict(),
        "recipe_input": {"ingredients": INGREDIENTS, "preferences": {}, "exclude_titles": []},
    }


def test_save_requires_login(db):
    at = open_page("app_pages/recipes.py", **result_state())
    button(at, "저장 (로그인 필요)").click().run()
    assert at.title[0].value == "로그인"
    assert any("레시피를 저장하려면 로그인" in i.value for i in at.info)


def test_save_then_my_recipes(monkeypatch, db):
    user_id, _ = logged_in_as(monkeypatch, db)
    at = open_page("app_pages/recipes.py", **result_state())
    button(at, "저장").click().run()
    assert any("내 레시피에 저장했어요" in s.value for s in at.success)
    assert button(at, "저장됨 ✓").disabled
    rows, total = repository.list_recipes(db, user_id)
    assert total == 1 and rows[0]["recipe"]["title"] == "달걀국"
    saved = repository.get_recipe(db, user_id, rows[0]["id"])
    assert saved["source_input"]["ingredients"] == INGREDIENTS

    at.switch_page("app_pages/my_recipes.py").run()
    assert [m.value for m in at.markdown if m.value.startswith("####")] == ["#### 달걀국"]


def test_my_recipes_memo_and_delete(monkeypatch, db):
    user_id, _ = logged_in_as(monkeypatch, db)
    rid = repository.save_recipe(db, user_id, recipe(), {}, "m")
    at = open_page("app_pages/my_recipes.py")
    at.text_area(key=f"memo_{rid}").input("간장 조금 덜").run()
    button(at, "메모 저장").click().run()
    assert repository.get_recipe(db, user_id, rid)["memo"] == "간장 조금 덜"
    assert button(at, "삭제").disabled  # 확인 전에는 지울 수 없음
    at.checkbox(key=f"del_confirm_{rid}").check().run()
    button(at, "삭제").click().run()
    assert repository.get_recipe(db, user_id, rid) is None
    assert any("아직 저장한 레시피가 없어요" in i.value for i in at.info)


def test_empty_my_recipes(monkeypatch, db):
    logged_in_as(monkeypatch, db)
    at = open_page("app_pages/my_recipes.py")
    assert any("아직 저장한 레시피가 없어요" in i.value for i in at.info)


# --- 프로필 ----------------------------------------------------------------------------------

def test_profile_is_applied_to_recipe_generation(monkeypatch, db):
    user_id, _ = logged_in_as(monkeypatch, db)
    repository.update_profile(db, user_id, {
        "nickname": "김요리", "allergies": ["새우"], "diet": ["채식"], "disliked": ["고수"],
        "skill_level": "beginner", "default_servings": 3, "cuisines": ["korean"],
    })
    calls = []

    def fake_generate(ingredients, prefs, exclude, **kwargs):
        calls.append(prefs)
        return RecipeResult([recipe()], "m", 1)

    monkeypatch.setattr(core.recipe_gen, "generate_recipes", fake_generate)
    at = open_page("app_pages/recipes.py", confirmed_ingredients=INGREDIENTS)
    assert any("새우" in c.value and "항상 함께 적용" in c.value for c in at.caption)
    at.multiselect(key="pref_allergies").set_value(["땅콩"]).run()
    button(at, "레시피 추천받기").click().run()
    prefs = calls[0]
    assert prefs.servings == 3 and prefs.cuisine == "korean" and prefs.diet == ["채식"]
    assert prefs.allergies == ["땅콩", "새우"]  # 조건 화면 + 프로필 알레르기
    assert prefs.disliked == ["고수"] and prefs.skill_level == "beginner"


def test_profile_page_saves(monkeypatch, db):
    user_id, _ = logged_in_as(monkeypatch, db)
    at = open_page("app_pages/profile.py")
    text_input(at, "닉네임").input("요리왕")
    at.multiselect[0].set_value(["새우"])
    button(at, "프로필 저장").click().run()
    assert any("프로필을 저장했어요" in s.value for s in at.success)
    assert repository.get_profile(db, user_id)["allergies"] == ["새우"]
    assert "요리왕" in sidebar_text(at)


def test_delete_account_from_profile(monkeypatch, db):
    user_id, _ = logged_in_as(monkeypatch, db)
    at = open_page("app_pages/profile.py")
    [t for t in at.text_input if t.label == "비밀번호"][0].input("abcd1234")
    button(at, "계정 삭제").click().run()
    assert auth.load_user(db, user_id) is None
    assert at.session_state["user"] is None and at.title[0].value == "냉장고 재료 찾기"
