# PRD 3단계: 사용자 프로필과 레시피 저장

| 항목 | 내용 |
|---|---|
| 제품 | 냉장고 사진 기반 레시피 추천 웹 애플리케이션 |
| 단계 | 3 / 3 (로그인, 사용자 프로필, 레시피 저장) |
| 사용 모델 | 새로 추가하는 모델 없음 (2단계 생성 요청에 프로필 정보를 반영) |
| 개발·배포 | Streamlit 앱, Streamlit Community Cloud에 무료 배포 |
| 로그인 | ① 아이디·비밀번호(앱이 직접 관리) ② Google 로그인(Streamlit 내장 `st.login`) — 두 방식을 함께 제공 |
| 저장소(DB) | Supabase 무료 요금제의 Postgres (Supabase는 DB로만 사용) |
| 이전 단계 | [PRD_step1.md](PRD_step1.md), [PRD_step2.md](PRD_step2.md) |
| 작성일 | 2026-10-18 작성, 2026-10-19 개정 (DB를 Neon에서 Supabase로, 로그인에 아이디·비밀번호 추가) |

## 1. 배경과 목적

2단계까지 만든 레시피는 세션이 끝나면 사라집니다. 알레르기나 선호 조건도 매번 다시 입력해야 합니다. 3단계에서는 로그인과 프로필을 더해 다음 두 가지를 해결합니다.
1. 마음에 드는 레시피를 저장하고, 나중에 다시 보고, 메모와 평가를 남길 수 있다.
2. 프로필에 적어 둔 알레르기, 식이 조건, 기본 인분이 레시피 생성 조건에 자동으로 채워진다.

## 2. 기술 결정과 이유

| 결정 | 이유 |
|---|---|
| **DB는 Supabase Postgres** | 사용자가 정한 결정. Community Cloud는 실행 중에 만든 파일을 재시작하거나 재배포할 때 지우므로 SQLite 파일은 쓸 수 없고, 외부 DB가 필요하다. Supabase 무료 요금제는 DB 500MB와 무료 프로젝트 2개를 준다(2026-10 확인). |
| **Supabase는 DB로만 쓰고, Supabase Auth는 쓰지 않음** | Supabase Auth의 비밀번호 로그인은 이메일(또는 전화번호)이 필요해서 "아이디" 로그인과 맞지 않는다. Supabase Auth의 Google 로그인은 리디렉션과 토큰 처리를 Streamlit 안에서 직접 구현해야 해서, Streamlit 내장 `st.login`보다 복잡하다. |
| **아이디·비밀번호는 앱이 직접 관리** | 사용자 테이블에 아이디와 비밀번호 해시(argon2)를 저장한다. 비밀번호 평문은 저장하지도 로그에 남기지도 않는다. |
| **Google 로그인은 `st.login`(OIDC)** | Streamlit이 Google 로그인과 신원 쿠키를 직접 처리해 준다. Google OAuth 클라이언트는 무료로 만들 수 있다. |
| **연결은 Supavisor 풀러(세션 모드, 5432 포트)** | 무료 요금제의 직접 연결 주소는 IPv6 전용이라 IPv4 환경에서 연결되지 않을 수 있다. 풀러는 IPv4를 지원한다. Streamlit 서버는 계속 떠 있는 프로세스이므로 세션 모드를 쓴다. |
| **테이블은 `public`이 아닌 `app` 스키마에 둠** | Supabase는 `public` 스키마의 테이블을 REST API로 노출한다. 앱은 REST API를 쓰지 않으므로 노출되지 않는 스키마에 두고, 혹시 모를 노출에 대비해 모든 테이블에 RLS(행 수준 보안)를 켜고 정책은 만들지 않는다(API로는 아무것도 읽을 수 없음). 앱은 DB 접속 계정으로 직접 연결하므로 RLS의 영향을 받지 않는다. |

**Supabase 무료 요금제의 제약** (2026-10 확인)
- **1주일 동안 쓰지 않으면 프로젝트가 일시 정지된다.** 정지되면 저장·불러오기가 실패하고, Supabase 대시보드에서 다시 켜야 한다(데이터는 남아 있음). 대응은 11장 참고.
- 자동 백업이 없다. 중요한 데이터가 생기면 `pg_dump`로 직접 백업한다.
- DB 500MB, 데이터 전송 5GB/월.

## 3. 목표와 비목표

**목표**
- 아이디·비밀번호로 가입하고 로그인할 수 있다. Google 계정으로도 로그인할 수 있다.
- 프로필(닉네임, 알레르기, 식이 조건, 싫어하는 재료, 요리 실력, 기본 인분, 선호 요리 종류)을 관리할 수 있다.
- 2단계 레시피를 저장하고, 목록 보기, 상세 보기, 메모, 별점, 즐겨찾기, 삭제를 할 수 있다.
- 로그인하지 않아도 1·2단계 기능은 그대로 쓸 수 있다. 저장할 때만 로그인을 요구한다.
- 비용 없이 운영한다(Community Cloud + Supabase 무료 + Google OAuth).

**비목표 (3단계에서 하지 않음)**
- 비밀번호 찾기·재설정 메일 (아이디 계정은 이메일을 받지 않으므로 메일을 보낼 수 없다)
- 아이디 계정과 Google 계정 연결·합치기 (같은 사람이라도 별개 계정으로 본다)
- Google 외 다른 소셜 로그인, 레시피 공유와 공개 피드, 댓글

## 4. 사용자 시나리오

**아이디로 가입**
1. 사이드바의 "로그인"을 누르면 로그인 화면이 나온다. 탭은 "로그인 / 회원가입 / Google".
2. "회원가입" 탭에서 아이디, 비밀번호, 비밀번호 확인, 닉네임을 입력한다. 가입하면 바로 로그인되고 프로필 화면으로 안내된다.

**Google로 로그인**
3. "Google로 로그인"을 누르면 Google 로그인 화면을 거쳐 앱으로 돌아온다. 처음이면 계정이 만들어지고, 닉네임은 Google 이름으로 채워진다.

**프로필이 반영된 추천**
4. 프로필에 알레르기("새우, 땅콩"), 싫어하는 재료("고수"), 기본 인분(2)을 저장해 두면, 레시피 페이지의 조건이 이 값으로 미리 채워진다.

**레시피 저장과 다시 보기**
5. 레시피 카드의 "저장"을 누르면 "내 레시피"에 저장된다.
6. "내 레시피"에서 정렬, 즐겨찾기 필터, 검색을 하고, 별점과 메모를 남긴다.

**비로그인 사용자의 저장**
7. 로그인하지 않은 사용자가 "저장"을 누르면 "저장하려면 로그인하세요"라는 안내와 로그인 단추가 나온다.

## 5. 기능 요구사항

### 5.1 아이디·비밀번호 계정

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-1 | 아이디는 4–20자, 영문 소문자·숫자·밑줄(`_`)만 쓴다. 대소문자를 구분하지 않고 중복될 수 없다. | 필수 |
| F3-2 | 비밀번호는 8–64자, 영문과 숫자를 모두 포함한다. 아이디와 같은 비밀번호는 거부한다. | 필수 |
| F3-3 | 비밀번호는 argon2(`argon2-cffi`)로 해시해서 저장한다. 평문은 어디에도 저장하거나 기록하지 않는다. | 필수 |
| F3-4 | 로그인 실패 메시지는 "아이디 또는 비밀번호가 올바르지 않아요"로 통일해서, 어느 쪽이 틀렸는지(아이디가 존재하는지) 알려 주지 않는다. | 필수 |
| F3-5 | 같은 아이디로 15분 안에 5회 실패하면 15분 동안 그 아이디의 로그인을 막는다. 시도 기록은 DB에 남긴다(세션 상태는 새로고침하면 초기화되므로). | 필수 |
| F3-6 | 로그인하면 무작위 세션 토큰(32바이트)을 만들어, 해시는 DB `sessions` 테이블에, 원본은 브라우저 쿠키에 저장한다(14일 유지). 새로고침해도 `st.context.cookies`로 쿠키를 읽어 로그인을 유지한다. 쿠키는 `st.html(unsafe_allow_javascript=True)`로 설정한다. | 필수 |
| F3-7 | 로그아웃하면 DB의 세션을 지우고 쿠키도 지운다. | 필수 |
| F3-8 | 로그인한 상태에서 현재 비밀번호를 확인한 뒤 비밀번호를 바꿀 수 있다. 바꾸면 다른 기기의 세션은 모두 끊는다. | 필수 |

### 5.2 Google 로그인

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-9 | "Google로 로그인"은 `st.login("google")`, 로그아웃은 `st.logout()`을 쓴다. | 필수 |
| F3-10 | Google 사용자는 `st.user`의 OIDC 고유 ID(`sub`)로 식별한다. 이메일은 표시용으로만 저장한다. | 필수 |
| F3-11 | 처음 로그인하면 `users`와 `profiles` 행을 만든다. 같은 이메일의 아이디 계정이 있어도 자동으로 합치지 않는다(다른 사람이 이메일을 사칭할 위험). | 필수 |

### 5.3 공통 계정 기능

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-12 | 현재 사용자는 다음 순서로 정한다: Google 로그인 상태(`st.user.is_logged_in`) → 아이디 세션 쿠키 → 비로그인. 화면 코드는 `core.auth.current_user()`만 쓴다. | 필수 |
| F3-13 | 사이드바에 로그인 상태를 보여 준다. 비로그인이면 "로그인", 로그인이면 닉네임, 로그인 방식(아이디/Google), "로그아웃". | 필수 |
| F3-14 | 로그인하지 않으면 "내 레시피"와 "프로필" 페이지를 메뉴에 보이지 않게 한다. | 필수 |
| F3-15 | 계정을 삭제하면 그 사용자의 프로필, 저장 레시피, 세션을 모두 지우고 로그아웃한다. 아이디 계정은 비밀번호를, Google 계정은 확인 문구("삭제")를 입력해야 한다. | 필수 |

### 5.4 프로필

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-16 | 프로필 항목: 닉네임(2–20자), 알레르기(최대 20개), 식이 조건, 싫어하는 재료(최대 20개), 요리 실력(초보/보통/능숙), 기본 인분(1–6), 선호 요리 종류. | 필수 |
| F3-17 | 2단계 조건 화면을 열면 프로필 값을 기본값으로 채운다. 이번 요청에서 바꾼 값은 프로필에 저장하지 않는다. | 필수 |
| F3-18 | 프로필의 알레르기는 2단계 서버 필터에도 항상 적용한다. 조건 화면에서 지워도 프로필 알레르기를 합쳐서 적용한다. | 필수 |
| F3-19 | 싫어하는 재료는 프롬프트에 "가능하면 쓰지 않기"로 전달한다(강제로 걸러 내지는 않음). 요리 실력이 "초보"이면 "단계를 더 잘게 나누고 용어를 풀어서 설명"을 덧붙인다. | 권장 |

### 5.5 레시피 저장

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-20 | 2단계 레시피 객체 전체를 그 시점 그대로(스냅숏) 저장한다. 생성에 쓴 재료 목록과 조건(`state["recipe_input"]`)도 함께 저장한다. | 필수 |
| F3-21 | 같은 사용자가 같은 레시피(제목과 재료 목록이 같음)를 다시 저장하면 "이미 저장됨"으로 안내한다. | 필수 |
| F3-22 | "내 레시피" 목록: 한 번에 20개씩, 최신순(기본)·별점순·조리 시간순, 즐겨찾기만 보기, 제목과 재료명 검색. | 필수 |
| F3-23 | 저장한 레시피에 별점(1–5, `st.feedback("stars")`), 메모(최대 1000자), 즐겨찾기를 달 수 있다. | 필수 |
| F3-24 | 저장한 레시피의 제목과 조리 순서를 고칠 수 있고, "원래대로"로 저장할 때의 내용으로 되돌릴 수 있다. | 권장 |
| F3-25 | 사용자당 최대 500개까지 저장할 수 있다(무료 DB 500MB 보호). | 필수 |
| F3-26 | DB에 연결하지 못하면(프로젝트 일시 정지 등) 실패를 숨기지 않고 "❌ 저장소에 연결하지 못했어요"와 원인을 보여 준다(1·2단계의 실패 표시 방식과 같음). 1·2단계는 계속 쓸 수 있다. | 필수 |

## 6. 시스템 구성

```
브라우저 ──(웹소켓)── Streamlit 앱 (Community Cloud)
     │  쿠키: 아이디 세션 토큰            │  st.login ──▶ Google OIDC
                                           │  st.connection("supabase") ──▶ Supabase Postgres
                                           │       (Supavisor 풀러, 세션 모드 5432, app 스키마)
                                           └─ core/openrouter.py ──▶ OpenRouter
```

**추가되는 파일**
```
app_pages/
  login.py               # 로그인 / 회원가입 / Google 탭
  my_recipes.py          # 내 레시피 목록과 상세
  profile.py             # 프로필, 비밀번호 변경, 계정 삭제
core/
  auth.py                # current_user(), 가입·로그인·로그아웃, 세션 쿠키, 로그인 실패 제한
  passwords.py           # argon2 해시·검증, 아이디·비밀번호 규칙 검사
  db.py                  # 연결, 테이블 생성(마이그레이션)
  repository.py          # 프로필과 저장 레시피 CRUD (항상 user_id 조건 포함)
```

**추가 의존성**: `streamlit[auth]`(Authlib), `SQLAlchemy`, `psycopg[binary]`, `argon2-cffi`

**`.streamlit/secrets.toml`에 추가하는 값** (로컬과 Community Cloud 양쪽)
```toml
[auth]
redirect_uri = "https://<앱이름>.streamlit.app/oauth2callback"   # 로컬은 http://localhost:8501/oauth2callback
cookie_secret = "<무작위 긴 문자열>"

[auth.google]
client_id = "<Google OAuth 클라이언트 ID>"
client_secret = "<Google OAuth 클라이언트 보안 비밀>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[connections.supabase]
# Supabase 대시보드 > Connect > Session pooler 의 연결 문자열 (포트 5432)
url = "postgresql+psycopg://postgres.<프로젝트ref>:<DB 비밀번호>@aws-0-<지역>.pooler.supabase.com:5432/postgres?sslmode=require"
```
- 로컬용과 배포용은 `redirect_uri`가 다르다. Google Cloud 콘솔의 OAuth 클라이언트에 두 주소를 모두 등록한다.
- 위 값들은 `.streamlit/secrets.toml.example`에 자리표시자로만 문서화한다. pre-commit 훅에 Supabase 연결 문자열 형식(`pooler.supabase.com` + 비밀번호)도 검사하도록 추가한다.

## 7. 데이터 모델 (Postgres, `app` 스키마)

```sql
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE app.users (
  id             BIGSERIAL PRIMARY KEY,
  username       TEXT UNIQUE,                 -- 아이디 계정만 (소문자로 저장)
  password_hash  TEXT,                        -- 아이디 계정만 (argon2)
  google_sub     TEXT UNIQUE,                 -- Google 계정만
  email          TEXT,                        -- Google 계정의 표시용 이메일
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((username IS NOT NULL AND password_hash IS NOT NULL) OR google_sub IS NOT NULL)
);

CREATE TABLE app.sessions (               -- 아이디 로그인 세션 (Google은 st.login 쿠키가 담당)
  token_hash  TEXT PRIMARY KEY,           -- 쿠키 토큰의 SHA-256
  user_id     BIGINT NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
  expires_at  TIMESTAMPTZ NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE app.login_attempts (         -- 로그인 실패 제한 (F3-5)
  username     TEXT NOT NULL,
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON app.login_attempts (username, attempted_at);

CREATE TABLE app.profiles (
  user_id           BIGINT PRIMARY KEY REFERENCES app.users(id) ON DELETE CASCADE,
  nickname          TEXT NOT NULL CHECK (char_length(nickname) BETWEEN 2 AND 20),
  allergies         JSONB NOT NULL DEFAULT '[]',
  diet              JSONB NOT NULL DEFAULT '[]',
  disliked          JSONB NOT NULL DEFAULT '[]',
  skill_level       TEXT NOT NULL DEFAULT 'normal' CHECK (skill_level IN ('beginner','normal','expert')),
  default_servings  INT  NOT NULL DEFAULT 2 CHECK (default_servings BETWEEN 1 AND 6),
  cuisines          JSONB NOT NULL DEFAULT '[]',
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE app.saved_recipes (
  id               BIGSERIAL PRIMARY KEY,
  user_id          BIGINT NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
  title            TEXT NOT NULL,
  recipe           JSONB NOT NULL,         -- 현재 레시피 (사용자가 고친 내용 반영)
  original         JSONB NOT NULL,         -- 저장할 때의 원본 스냅숏
  source_input     JSONB NOT NULL,         -- 생성에 쓴 재료 목록과 조건
  ingredient_names TEXT NOT NULL,          -- 재료명 검색용
  dedupe_key       TEXT NOT NULL,          -- 제목 + 정렬한 재료명의 해시
  time_minutes     INT,
  rating           SMALLINT CHECK (rating BETWEEN 1 AND 5),
  memo             TEXT CHECK (char_length(memo) <= 1000),
  is_favorite      BOOLEAN NOT NULL DEFAULT false,
  model            TEXT NOT NULL,
  schema_version   SMALLINT NOT NULL DEFAULT 1,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, dedupe_key)
);
CREATE INDEX ON app.saved_recipes (user_id, created_at DESC);

-- REST API로 노출되더라도 아무것도 읽히지 않게 RLS를 켜고 정책은 만들지 않는다
ALTER TABLE app.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.login_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.saved_recipes ENABLE ROW LEVEL SECURITY;
```
- 테이블 생성은 앱이 시작될 때 `IF NOT EXISTS`로 한 번 실행한다(`st.cache_resource`).
- 만료된 세션과 1일이 지난 로그인 실패 기록은 로그인할 때 함께 지운다.

## 8. 로직 함수

**`core/auth.py`**
| 함수 | 설명 |
|---|---|
| `current_user() -> User \| None` | Google → 아이디 세션 쿠키 순서로 확인 (F3-12) |
| `sign_up(username, password, nickname)` | 규칙 검사 → 중복 확인 → 해시 저장 → 로그인 |
| `log_in(username, password)` | 실패 제한 확인 → 검증 → 세션 생성 → 쿠키 설정. 실패하면 통일된 문구 |
| `log_out()` | 아이디: 세션 삭제와 쿠키 삭제 / Google: `st.logout()` |
| `change_password(user, current, new)` | 현재 비밀번호 확인 → 해시 교체 → 이 기기 외 세션 삭제 |

**`core/repository.py`**: 모든 함수는 첫 인자로 `user_id`를 받고, 모든 쿼리에 `WHERE user_id = :user_id`를 붙인다. 매개변수 바인딩만 쓴다.
| 함수 | 설명 |
|---|---|
| `get_profile` / `update_profile` | 프로필 읽기·쓰기 |
| `save_recipe(user_id, recipe, source_input, model)` | 중복이면 `AlreadySaved(id)`, 개수 초과면 `LimitReached` |
| `list_recipes(user_id, sort, favorite_only, query, offset, limit=20)` | 목록 |
| `get_recipe` / `update_recipe` / `restore_recipe` / `delete_recipe` | 상세·수정·원래대로·삭제. 다른 사용자의 레시피면 `None` |
| `delete_account(user_id)` | `users` 행 삭제 (나머지는 `ON DELETE CASCADE`) |

**2단계 변경**: 로그인한 상태면 `generate_recipes()`를 부르기 전에 프로필을 읽어 조건과 합친다(F3-17~F3-19).

## 9. 화면 요구사항

| 페이지 / 요소 | 구성 |
|---|---|
| 사이드바 | 로그인 상태(닉네임, 방식), 로그인·로그아웃. 로그인 상태면 "내 레시피", "프로필" 메뉴 |
| 로그인 페이지 | `st.tabs(["로그인", "회원가입", "Google"])`. 로그인·가입은 `st.form`. 비밀번호 칸은 `type="password"`. 가입 칸 아래에 아이디·비밀번호 규칙을 안내한다. "비밀번호를 잊으면 되찾을 수 없어요"라고 가입 화면에 미리 알린다. |
| 레시피 카드(2단계) | "저장" 단추. 저장된 레시피는 "저장됨 ✓". 비로그인이면 로그인 안내 |
| 내 레시피 | 검색, 정렬(`st.segmented_control`), 즐겨찾기만(`st.toggle`), 카드 목록, "더 보기" |
| 저장한 레시피 상세 | 2단계 상세에 별점, 메모, 즐겨찾기, 편집, 원래대로, 삭제 |
| 프로필 | `st.form`. 알레르기·싫어하는 재료는 `st.multiselect(accept_new_options=True)`. 아이디 계정은 비밀번호 변경 칸 |
| 계정 삭제 | 프로필 맨 아래 `st.expander("계정 삭제")`, 빨간 단추, 비밀번호 또는 확인 문구 |
| 실패 표시 | DB 연결 실패, 저장 실패는 1·2단계와 같은 "❌ … 실패" 배너로 보여 준다 |

- 사용자가 입력한 메모·닉네임과 모델이 만든 글은 마크다운·HTML로 해석되지 않게 이스케이프한다.

## 10. 비기능 요구사항

| 구분 | 요구사항 |
|---|---|
| 보안 | 비밀번호 argon2 해시, 로그인 실패 제한, 통일된 실패 문구. 세션 토큰은 DB에 해시로만 저장. 모든 DB 쿼리에 `user_id` 조건과 매개변수 바인딩. 테이블은 `app` 스키마 + RLS. |
| 쿠키 한계 | 자바스크립트로 설정하는 쿠키는 `HttpOnly`를 쓸 수 없어서, 페이지에 악성 스크립트가 들어오면 토큰을 읽힐 수 있다. 앱은 모든 사용자 입력과 모델 출력을 이스케이프해서 이 위험을 줄인다. `Secure`, `SameSite=Lax`, 14일 만료를 쓴다. |
| 비밀 값 | Google 클라이언트 보안 비밀, `cookie_secret`, Supabase 연결 문자열(DB 비밀번호 포함)은 `st.secrets`에만 둔다. |
| 개인정보 | 알레르기·식이 조건은 건강 관련 정보로 취급한다. 로그에 남기지 않고, 계정 삭제 시 즉시 지운다. 수집 항목(아이디 또는 Google 이메일·이름, 프로필, 저장 레시피)과 저장 위치(Supabase 프로젝트 지역)를 프로필 화면에 안내한다. |
| 성능 | 목록 조회는 500건 기준 1초 이내. 연결 풀에 `pool_pre_ping=True`. |
| 무료 한도 | DB 500MB, 사용자당 500개·JSON 64KB 제한. |

## 11. 배포 추가 작업

1. Supabase(https://supabase.com)에서 무료 프로젝트를 만든다. 지역은 사용자와 가까운 곳(예: 서울 `ap-northeast-2`)을 고른다.
2. 대시보드 > Connect > **Session pooler** 연결 문자열을 복사해 `[connections.supabase]`에 넣는다(직접 연결은 IPv6 전용이라 쓰지 않음).
3. Google Cloud 콘솔에서 OAuth 동의 화면과 "웹 애플리케이션" OAuth 클라이언트를 만들고, 리디렉션 URI에 `http://localhost:8501/oauth2callback`과 `https://<앱이름>.streamlit.app/oauth2callback`을 넣는다.
4. Community Cloud 앱 설정의 Secrets에 6장의 값을 추가한다(배포용 `redirect_uri`).
5. `requirements.txt`에 추가 의존성을 넣고 푸시한다.
6. **일시 정지 방지(선택)**: 1주일 무활동 정지를 막으려면, GitHub Actions의 예약 작업(무료)으로 3~4일마다 간단한 쿼리(`SELECT 1`)를 보낸다. 연결 문자열은 GitHub 저장소 Secrets에 둔다. 이 작업을 두지 않으면, 정지된 동안 앱은 F3-26대로 실패를 표시한다.

## 12. 수용 기준

- [ ] 아이디로 가입하고, 로그아웃한 뒤 다시 로그인하면 같은 프로필과 저장 레시피가 보인다.
- [ ] 아이디로 로그인한 뒤 브라우저를 새로고침해도 로그인이 유지된다. 로그아웃하면 새로고침해도 로그아웃 상태다.
- [ ] Google로 로그인하면 별도 계정이 만들어지고, 같은 방식으로 저장·불러오기가 된다.
- [ ] 규칙에 맞지 않는 아이디·비밀번호, 이미 있는 아이디로는 가입할 수 없고, 이유가 안내된다.
- [ ] 틀린 아이디와 틀린 비밀번호의 실패 문구가 같다.
- [ ] 같은 아이디로 5회 틀리면 15분 동안 로그인이 막히고 안내가 나온다(새로고침해도 유지).
- [ ] DB의 `password_hash`는 argon2 형식이고, 평문 비밀번호는 DB와 로그 어디에도 없다.
- [ ] 사용자 A로 사용자 B의 저장 레시피 ID를 조회·수정·삭제하면 모두 실패한다(`repository` 단위 테스트).
- [ ] 프로필 알레르기에 "달걀"을 넣으면, 조건 화면에서 지워도 생성된 레시피에 달걀이 없다.
- [ ] 같은 레시피를 두 번 저장하면 "이미 저장됨"이 나오고 목록에는 1개만 있다.
- [ ] 메모에 `[링크](https://example.com)`나 `<script>alert(1)</script>`를 넣어도 글자 그대로 보인다.
- [ ] 계정을 삭제하면 그 사용자의 모든 행이 사라지고 로그아웃된다.
- [ ] Supabase REST API(anon 키)로 `app` 스키마의 어떤 테이블도 읽을 수 없다.
- [ ] Supabase 프로젝트가 일시 정지된 상태에서 저장을 누르면 "❌ 저장소에 연결하지 못했어요"가 나오고, 1·2단계는 그대로 쓸 수 있다.
- [ ] 앱을 재부팅해도 저장 레시피가 남아 있다.
- [ ] `git status`에 `.streamlit/secrets.toml`이 나타나지 않는다.

## 13. 위험 요소와 대응

| 위험 | 대응 |
|---|---|
| 직접 만든 아이디 로그인의 보안 허점 | 검증된 라이브러리(argon2-cffi)를 쓰고, 12장의 보안 수용 기준을 자동화 테스트로 확인한다. |
| Community Cloud에서 쿠키가 동작하지 않을 가능성 | Community Cloud는 앱을 iframe 안에 보여 줄 수 있어서, 브라우저가 쿠키를 막을 수 있다. 배포 후 F3-6을 가장 먼저 확인한다. 동작하지 않으면 아이디 로그인은 "새로고침하면 다시 로그인"으로 낮추고 화면에 그렇게 안내한다(Google 로그인은 영향 없음). |
| Supabase 1주일 무활동 일시 정지 | 11장의 예약 쿼리, 또는 정지 시 실패 표시(F3-26)와 대시보드에서 다시 켜기. |
| 자동 백업 없음 | 필요할 때 `pg_dump`로 직접 백업한다. |
| `st.login`을 거치며 세션 상태가 초기화되어 로그인 전에 만든 레시피가 사라질 수 있음 | 구현할 때 확인한다. 초기화되면 저장 단추의 로그인 안내에 "로그인하면 지금 레시피는 다시 만들어야 해요"라고 알린다. |
| Google OAuth 앱이 "테스트" 상태면 등록한 사용자만 로그인 가능 | 시연 단계에서는 테스트 사용자로 운영하고, 공개할 때 동의 화면을 게시한다. |
| 무료 서비스 정책 변경 | Community Cloud, Supabase, OpenRouter의 무료 조건은 바뀔 수 있다(2026-10 확인). 연결 정보와 모델 ID는 모두 `st.secrets`로 분리한다. |

## 14. 구현 메모 (2026-10-19)

- **로컬 개발용 DB**: Supabase 설정이 없으면 같은 테이블 정의로 `data/local.db`(SQLite, git 제외)를 쓴다. 사이드바에 "로컬 개발용 DB(SQLite)를 쓰고 있어요"라고 알린다. 자동 테스트는 항상 메모리 SQLite를 쓴다.
- **쿠키 순서**: 로그인 직후 페이지를 옮기면 그 실행의 화면 출력(쿠키 스크립트 포함)이 버려진다. 처음 구현에서는 그래서 쿠키가 설정되지 않았고, 테스트로 발견해 "이동 처리 → 쿠키 스크립트" 순서로 고쳤다. 브라우저에서 가입·새로고침(로그인 유지)·로그아웃·새로고침(로그아웃 유지)을 확인했다.
- **내 레시피 펼침 유지**: 별점·메모를 저장하면 다시 실행되면서 펼쳐 둔 상세가 닫히는 문제가 있어, `st.expander(key=...)`와 토스트 알림으로 고쳤다.
- **아직 확인하지 못한 것**: Supabase 연결과 RLS(12장 "REST API로 읽을 수 없음"), Google 로그인, Community Cloud에서의 쿠키 동작(13장 위험)은 Supabase 프로젝트와 Google OAuth 클라이언트를 만든 뒤 확인한다.

## 15. 미결정 사항

- 아이디 계정에 이메일(선택)을 받아 비밀번호 재설정을 지원할지 여부. 지원하려면 메일 발송 서비스가 필요하다.
- 아이디 계정과 Google 계정을 연결하는 기능을 둘지 여부.
- 무료 사용량 보호를 위해 1·2단계도 로그인한 사용자만 쓰게 할지 여부.
