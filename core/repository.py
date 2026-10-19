"""프로필과 저장 레시피 CRUD (PRD 3단계 5.4~5.5, 8장).

모든 함수는 첫 인자로 user_id를 받고, 모든 쿼리에 user_id 조건을 붙인다(다른 사용자의 데이터에 닿지 않게).
"""

import copy
import hashlib
import json

from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from core.auth import nickname_problem
from core.db import profiles, saved_recipes, utcnow
from core.errors import AppError
from core.pantry import canonical
from core.recipe_gen import CUISINES, clean_user_text

MAX_SAVED = 500
MAX_RECIPE_BYTES = 64 * 1024
SKILL_LEVELS = {"beginner": "초보", "normal": "보통", "expert": "능숙"}
SORTS = {"recent": "최신순", "rating": "별점순", "time": "조리 시간순"}


# --- 프로필 ---------------------------------------------------------------------------

def get_profile(engine: Engine, user_id: int) -> dict:
    with engine.connect() as conn:
        row = conn.execute(select(profiles).where(profiles.c.user_id == user_id)).mappings().first()
    return dict(row) if row else {}


def _clean_tags(values, limit: int = 20) -> list[str]:
    out = []
    for v in values or []:
        v = clean_user_text(v, 20)
        if v and v not in out:
            out.append(v)
    return out[:limit]


def update_profile(engine: Engine, user_id: int, data: dict) -> dict:
    problem = nickname_problem(data.get("nickname", ""))
    skill = data.get("skill_level", "normal")
    servings = data.get("default_servings", 2)
    if not problem and skill not in SKILL_LEVELS:
        problem = "요리 실력 값이 올바르지 않아요."
    if not problem and not (isinstance(servings, int) and 1 <= servings <= 6):
        problem = "기본 인분은 1~6 사이로 골라 주세요."
    if problem:
        raise AppError("INVALID_INPUT", problem)
    values = {
        "nickname": clean_user_text(data["nickname"], 20),
        "allergies": _clean_tags(data.get("allergies")),
        "diet": _clean_tags(data.get("diet")),
        "disliked": _clean_tags(data.get("disliked")),
        "skill_level": skill,
        "default_servings": servings,
        "cuisines": [c for c in data.get("cuisines") or [] if c in CUISINES],
    }
    with engine.begin() as conn:
        conn.execute(update(profiles).where(profiles.c.user_id == user_id).values(**values, updated_at=utcnow()))
    return values


# --- 저장 레시피 -------------------------------------------------------------------------

def dedupe_key(recipe: dict) -> str:
    names = sorted(canonical(i["name"]) for i in recipe.get("ingredients", []))
    return hashlib.sha256(json.dumps([canonical(recipe.get("title", "")), names], ensure_ascii=False).encode()).hexdigest()


def _validate_recipe(recipe: dict) -> dict:
    if not isinstance(recipe, dict) or not recipe.get("title") or not recipe.get("ingredients") or not recipe.get("steps"):
        raise AppError("INVALID_INPUT", "저장할 레시피 형식이 올바르지 않아요.")
    recipe = {k: v for k, v in recipe.items() if k != "id"}  # 임시 id는 저장하지 않는다
    if len(json.dumps(recipe, ensure_ascii=False).encode()) > MAX_RECIPE_BYTES:
        raise AppError("INVALID_INPUT", "레시피가 너무 커서 저장할 수 없어요.")
    return recipe


def save_recipe(engine: Engine, user_id: int, recipe: dict, source_input: dict, model: str) -> int:
    recipe = _validate_recipe(recipe)
    key = dedupe_key(recipe)
    with engine.begin() as conn:
        existing = conn.execute(
            select(saved_recipes.c.id).where(and_(saved_recipes.c.user_id == user_id, saved_recipes.c.dedupe_key == key))
        ).scalar_one_or_none()
        if existing is not None:
            raise AppError("ALREADY_SAVED")
        count = conn.execute(
            select(func.count()).select_from(saved_recipes).where(saved_recipes.c.user_id == user_id)
        ).scalar_one()
        if count >= MAX_SAVED:
            raise AppError("SAVE_LIMIT")
        try:
            return conn.execute(insert(saved_recipes).values(
                user_id=user_id, title=recipe["title"], recipe=recipe, original=copy.deepcopy(recipe),
                source_input=source_input or {}, ingredient_names=" ".join(i["name"] for i in recipe["ingredients"]),
                dedupe_key=key, time_minutes=recipe.get("time_minutes"), model=model or "",
            )).inserted_primary_key[0]
        except IntegrityError:  # 동시에 두 번 누른 경우
            raise AppError("ALREADY_SAVED") from None


def saved_keys(engine: Engine, user_id: int) -> set[str]:
    """화면에서 '저장됨' 표시를 하려고 쓰는, 이 사용자가 저장한 레시피의 중복 확인 키."""
    with engine.connect() as conn:
        return set(conn.execute(select(saved_recipes.c.dedupe_key).where(saved_recipes.c.user_id == user_id)).scalars())


def list_recipes(
    engine: Engine, user_id: int, *, sort: str = "recent", favorite_only: bool = False, query: str = "",
    offset: int = 0, limit: int = 20,
) -> tuple[list[dict], int]:
    cond = [saved_recipes.c.user_id == user_id]
    if favorite_only:
        cond.append(saved_recipes.c.is_favorite.is_(True))
    query = clean_user_text(query, 30).lower()
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        cond.append(or_(
            func.lower(saved_recipes.c.title).like(pattern, escape="\\"),
            func.lower(saved_recipes.c.ingredient_names).like(pattern, escape="\\"),
        ))
    order = {
        "recent": [saved_recipes.c.created_at.desc(), saved_recipes.c.id.desc()],
        "rating": [saved_recipes.c.rating.desc().nulls_last(), saved_recipes.c.created_at.desc()],
        "time": [saved_recipes.c.time_minutes.asc().nulls_last(), saved_recipes.c.created_at.desc()],
    }.get(sort, [saved_recipes.c.created_at.desc()])
    columns = [saved_recipes.c[c] for c in ("id", "title", "time_minutes", "rating", "is_favorite", "created_at", "recipe")]
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(saved_recipes).where(and_(*cond))).scalar_one()
        rows = conn.execute(select(*columns).where(and_(*cond)).order_by(*order).offset(offset).limit(limit)).mappings()
        return [dict(r) for r in rows], total


def get_recipe(engine: Engine, user_id: int, recipe_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(saved_recipes).where(and_(saved_recipes.c.user_id == user_id, saved_recipes.c.id == recipe_id))
        ).mappings().first()
    return dict(row) if row else None


def update_recipe(engine: Engine, user_id: int, recipe_id: int, **fields) -> None:
    values = {}
    if "rating" in fields:
        rating = fields["rating"]
        values["rating"] = rating if isinstance(rating, int) and 1 <= rating <= 5 else None
    if "memo" in fields:
        memo = (fields["memo"] or "").strip()
        if len(memo) > 1000:
            raise AppError("INVALID_INPUT", "메모는 1000자까지 쓸 수 있어요.")
        values["memo"] = memo or None
    if "is_favorite" in fields:
        values["is_favorite"] = bool(fields["is_favorite"])
    if "title" in fields or "steps" in fields:
        current = get_recipe(engine, user_id, recipe_id)
        if current is None:
            raise AppError("NOT_FOUND")
        recipe = copy.deepcopy(current["recipe"])
        if "title" in fields:
            title = clean_user_text(fields["title"], 40)
            if not title:
                raise AppError("INVALID_INPUT", "제목을 입력해 주세요.")
            recipe["title"] = values["title"] = title
        if "steps" in fields:
            steps = [clean_user_text(s, 300) for s in fields["steps"]]
            steps = [s for s in steps if s]
            if not steps:
                raise AppError("INVALID_INPUT", "조리 순서를 한 줄 이상 남겨 주세요.")
            old = {s["order"]: s.get("timer_seconds") for s in recipe.get("steps", [])}
            recipe["steps"] = [{"order": i, "text": t, "timer_seconds": old.get(i)} for i, t in enumerate(steps, 1)]
        values["recipe"] = recipe
    if not values:
        return
    with engine.begin() as conn:
        result = conn.execute(
            update(saved_recipes)
            .where(and_(saved_recipes.c.user_id == user_id, saved_recipes.c.id == recipe_id))
            .values(**values, updated_at=utcnow())
        )
        if result.rowcount == 0:
            raise AppError("NOT_FOUND")


def restore_recipe(engine: Engine, user_id: int, recipe_id: int) -> None:
    current = get_recipe(engine, user_id, recipe_id)
    if current is None:
        raise AppError("NOT_FOUND")
    original = current["original"]
    with engine.begin() as conn:
        conn.execute(
            update(saved_recipes)
            .where(and_(saved_recipes.c.user_id == user_id, saved_recipes.c.id == recipe_id))
            .values(recipe=original, title=original["title"], updated_at=utcnow())
        )


def delete_recipe(engine: Engine, user_id: int, recipe_id: int) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            delete(saved_recipes).where(and_(saved_recipes.c.user_id == user_id, saved_recipes.c.id == recipe_id))
        )
    return result.rowcount > 0
