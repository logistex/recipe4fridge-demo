"""3단계 저장소: 테이블 정의와 연결 (docs/PRD_step3.md 7장).

배포에서는 Supabase Postgres(app 스키마 + RLS), 로컬 개발과 테스트에서는 SQLite를 같은 정의로 쓴다.
SQLite에는 스키마가 없으므로 schema_translate_map으로 app 스키마를 지운다.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

SCHEMA = "app"
ID = BigInteger().with_variant(Integer, "sqlite")  # SQLite는 INTEGER PRIMARY KEY여야 자동 증가한다
JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


metadata = MetaData(schema=SCHEMA)

users = Table(
    "users", metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("username", Text, unique=True),  # 아이디 계정만 (소문자로 저장)
    Column("password_hash", Text),  # 아이디 계정만 (argon2)
    Column("google_sub", Text, unique=True),  # Google 계정만
    Column("email", Text),  # Google 계정의 표시용 이메일
    Column("created_at", DateTime(timezone=True), nullable=False, default=utcnow),
    CheckConstraint(
        "(username IS NOT NULL AND password_hash IS NOT NULL) OR google_sub IS NOT NULL", name="users_identity"
    ),
)

sessions = Table(
    "sessions", metadata,
    Column("token_hash", Text, primary_key=True),  # 쿠키 토큰의 SHA-256
    Column("user_id", ID, ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utcnow),
)

login_attempts = Table(
    "login_attempts", metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("username", Text, nullable=False),
    Column("attempted_at", DateTime(timezone=True), nullable=False, default=utcnow),
    Index("ix_login_attempts_username_time", "username", "attempted_at"),
)

profiles = Table(
    "profiles", metadata,
    Column("user_id", ID, ForeignKey("app.users.id", ondelete="CASCADE"), primary_key=True),
    Column("nickname", Text, nullable=False),
    Column("allergies", JSONType, nullable=False, default=list),
    Column("diet", JSONType, nullable=False, default=list),
    Column("disliked", JSONType, nullable=False, default=list),
    Column("skill_level", Text, nullable=False, default="normal"),
    Column("default_servings", Integer, nullable=False, default=2),
    Column("cuisines", JSONType, nullable=False, default=list),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow),
    CheckConstraint("length(nickname) BETWEEN 2 AND 20", name="profiles_nickname"),
    CheckConstraint("skill_level IN ('beginner','normal','expert')", name="profiles_skill"),
    CheckConstraint("default_servings BETWEEN 1 AND 6", name="profiles_servings"),
)

saved_recipes = Table(
    "saved_recipes", metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("user_id", ID, ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False),
    Column("title", Text, nullable=False),
    Column("recipe", JSONType, nullable=False),  # 현재 레시피 (사용자가 고친 내용 반영)
    Column("original", JSONType, nullable=False),  # 저장할 때의 원본 스냅숏
    Column("source_input", JSONType, nullable=False),  # 생성에 쓴 재료 목록과 조건
    Column("ingredient_names", Text, nullable=False),  # 재료명 검색용
    Column("dedupe_key", Text, nullable=False),
    Column("time_minutes", Integer),
    Column("rating", SmallInteger),
    Column("memo", Text),
    Column("is_favorite", Boolean, nullable=False, default=False),
    Column("model", Text, nullable=False),
    Column("schema_version", SmallInteger, nullable=False, default=1),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utcnow),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow),
    UniqueConstraint("user_id", "dedupe_key", name="saved_recipes_dedupe"),
    CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="saved_recipes_rating"),
    CheckConstraint("memo IS NULL OR length(memo) <= 1000", name="saved_recipes_memo"),
    Index("ix_saved_recipes_user_created", "user_id", "created_at"),
)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        options = {"execution_options": {"schema_translate_map": {SCHEMA: None}}}
        if url in ("sqlite://", "sqlite:///:memory:"):  # 테스트용 메모리 DB: 스레드끼리 같은 연결을 쓴다
            options.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
        else:
            options["connect_args"] = {"check_same_thread": False}
        engine = create_engine(url, **options)

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")  # 계정 삭제 시 CASCADE가 동작하도록

        return engine
    # Supabase Supavisor 풀러(세션 모드). 잠들었다 깨어난 연결을 걸러 내려고 pre_ping을 켠다.
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2, pool_recycle=1800)


def init_db(engine: Engine) -> None:
    """테이블을 만든다(이미 있으면 그대로). Postgres에서는 app 스키마와 RLS도 설정한다."""
    postgres = engine.dialect.name == "postgresql"
    with engine.begin() as conn:
        if postgres:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        metadata.create_all(conn)
        if postgres:
            # Supabase REST API로 노출되더라도 아무것도 읽히지 않게 RLS를 켜고 정책은 만들지 않는다
            for table in metadata.sorted_tables:
                conn.execute(text(f"ALTER TABLE {SCHEMA}.{table.name} ENABLE ROW LEVEL SECURITY"))


def is_local(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite"
