# PRD 3단계: 사용자 프로필과 레시피 저장

| 항목 | 내용 |
|---|---|
| 제품 | 냉장고 사진 기반 레시피 추천 웹 애플리케이션 |
| 단계 | 3 / 3 (사용자 프로필, 레시피 저장) |
| 사용 모델 | 새로 추가하는 모델 없음 (2단계 생성 요청에 프로필 정보를 반영) |
| 개발·배포 | Streamlit 앱, Streamlit Community Cloud에 무료 배포 |
| 로그인 | Streamlit 내장 로그인(`st.login`, OpenID Connect), Google 계정 |
| 저장소(DB) | Neon Postgres 무료 요금제 |
| 이전 단계 | [PRD_step1.md](PRD_step1.md), [PRD_step2.md](PRD_step2.md) |
| 작성일 | 2026-10-18 (같은 날 FastAPI·SQLite 기준에서 Streamlit·Neon 기준으로 개정) |

## 1. 배경과 목적

2단계까지 만든 레시피는 세션이 끝나면 사라집니다. 알레르기나 선호 조건도 매번 다시 입력해야 합니다. 3단계에서는 로그인과 프로필을 더해 다음 두 가지를 해결합니다.
1. 마음에 드는 레시피를 저장하고, 나중에 다시 보고, 메모와 평가를 남길 수 있다.
2. 프로필에 적어 둔 알레르기, 식이 조건, 기본 인분이 레시피 생성 조건에 자동으로 채워진다.

## 2. 기술 결정과 이유

| 결정 | 이유 |
|---|---|
| **로그인은 `st.login`(Google OIDC)** | Streamlit이 OIDC 로그인과 신원 쿠키를 직접 처리해 준다. 비밀번호를 받지 않으므로 비밀번호 해시, 로그인 실패 잠금, 비밀번호 변경과 재설정, CSRF 처리를 만들 필요가 없다. Google OAuth 클라이언트는 무료로 만들 수 있다. |
| **DB는 Neon Postgres** | Community Cloud는 실행 중에 만든 파일을 재시작하거나 재배포할 때 지운다. 그래서 SQLite 파일은 쓸 수 없다. Neon 무료 요금제는 기간 제한이 없고(체험판이 아님), 프로젝트당 1GB 저장 공간과 월 100 CU-시간을 준다. 5분 동안 쓰지 않으면 잠들었다가 요청이 오면 자동으로 깨어난다. |
| **DB 연결은 `st.connection("neon", type="sql")`** | Streamlit 내장 SQL 연결(SQLAlchemy 기반)이라, 연결 정보를 `st.secrets`에 두고 연결 풀을 알아서 관리한다. |

## 3. 목표와 비목표

**목표**
- Google 계정으로 로그인, 로그아웃할 수 있다.
- 프로필(닉네임, 알레르기, 식이 조건, 싫어하는 재료, 요리 실력, 기본 인분, 선호 요리 종류)을 관리할 수 있다.
- 2단계 레시피를 저장하고, 목록 보기, 상세 보기, 메모, 별점, 즐겨찾기, 삭제를 할 수 있다.
- 로그인하지 않아도 1·2단계 기능은 그대로 쓸 수 있다. 저장할 때만 로그인을 요구한다.
- 비용 없이 운영한다(Community Cloud + Neon 무료 + Google OAuth).

**비목표 (3단계에서 하지 않음)**
- 이메일과 비밀번호 가입, Google 외 다른 로그인 제공자(구조상 나중에 추가는 가능)
- 레시피 공유와 공개 피드, 댓글
- 여러 기기 동시 편집 충돌 처리

## 4. 사용자 시나리오

**첫 로그인과 프로필 설정**
1. 사용자가 사이드바의 "Google로 로그인"을 누른다. Google 로그인 화면을 거쳐 앱으로 돌아온다.
2. 처음 로그인한 사용자면 프로필 페이지로 안내된다. 닉네임은 Google 이름으로 미리 채워진다. 알레르기("새우, 땅콩"), 싫어하는 재료("고수"), 기본 인분(2), 요리 실력("초보")을 입력하고 저장한다.

**프로필이 반영된 추천**
3. 냉장고 사진을 올리고 재료를 확정한 뒤 레시피 페이지로 가면, 알레르기, 싫어하는 재료, 인분이 프로필 값으로 미리 채워져 있다. 이번 요청에서만 바꿀 수도 있다.

**레시피 저장과 다시 보기**
4. 추천받은 레시피 카드에서 "저장"을 누르면 "내 레시피"에 저장된다.
5. "내 레시피" 페이지에서 저장한 레시피를 최신순, 별점순, 조리 시간순으로 정렬하거나 즐겨찾기만 걸러 보고, 제목이나 재료로 검색한다.
6. 레시피를 만들어 본 뒤 별점과 메모("간장을 조금 줄이면 더 맛있음")를 남긴다.

**비로그인 사용자의 저장**
7. 로그인하지 않은 사용자가 "저장"을 누르면 "저장하려면 로그인하세요"라는 안내와 로그인 버튼이 나온다.

## 5. 기능 요구사항

### 5.1 로그인과 계정

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-1 | 사이드바에 로그인 상태를 보여 준다. 로그아웃 상태면 "Google로 로그인"(`st.login("google")`), 로그인 상태면 닉네임과 "로그아웃"(`st.logout()`)을 보여 준다. | 필수 |
| F3-2 | 사용자 식별은 `st.user`의 OIDC 고유 ID(`sub`)로 한다. 이메일은 바뀔 수 있으므로 식별자로 쓰지 않고 표시용으로만 저장한다. | 필수 |
| F3-3 | 처음 로그인하면 `users`와 `profiles` 행을 만든다. 닉네임 기본값은 `st.user.name`이다. | 필수 |
| F3-4 | 계정을 삭제하면 그 사용자의 프로필과 저장 레시피를 모두 지우고 로그아웃한다. 삭제 전에 "복구할 수 없습니다"라고 안내하고, 확인 문구("삭제")를 직접 입력하게 한다. Google 계정 자체에는 영향이 없다고 함께 안내한다. | 필수 |
| F3-5 | 로그인하지 않으면 "내 레시피"와 "프로필" 페이지를 메뉴에 보이지 않게 한다(`st.navigation`에 넣는 페이지를 로그인 상태에 따라 바꿈). | 필수 |

### 5.2 프로필

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-6 | 프로필 항목: 닉네임(2–20자), 알레르기(최대 20개), 식이 조건(채식, 비건, 글루텐 제외 등 다중 선택), 싫어하는 재료(최대 20개), 요리 실력(초보/보통/능숙), 기본 인분(1–6), 선호 요리 종류(다중 선택). | 필수 |
| F3-7 | 2단계 조건 화면을 열면 프로필 값을 기본값으로 채운다. 이번 요청에서 바꾼 값은 프로필에 저장하지 않는다. | 필수 |
| F3-8 | 프로필의 알레르기는 2단계 서버 필터(F2-7)에도 자동으로 적용된다. 사용자가 조건 화면에서 지워도 프로필 알레르기를 합쳐서 적용한다. | 필수 |
| F3-9 | 싫어하는 재료는 프롬프트에 "가능하면 쓰지 않기"로 전달한다. 알레르기와 달리 결과에서 강제로 걸러 내지는 않는다. | 필수 |
| F3-10 | 요리 실력이 "초보"이면 프롬프트에 "단계를 더 잘게 나누고 용어를 풀어서 설명"을 덧붙인다. | 권장 |

### 5.3 레시피 저장

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-11 | 2단계 레시피 객체 전체를 그 시점 그대로(스냅숏) 저장한다. 생성에 쓴 재료 목록과 조건도 함께 저장한다. | 필수 |
| F3-12 | 같은 사용자가 같은 레시피(제목과 재료 목록이 같음)를 다시 저장하면 새로 만들지 않고 "이미 저장됨"으로 안내한다. | 필수 |
| F3-13 | "내 레시피" 목록: 한 번에 20개씩, 최신순(기본), 별점순, 조리 시간순 정렬. 즐겨찾기만 보기 필터. 제목과 재료명 검색. | 필수 |
| F3-14 | 저장한 레시피에 별점(1–5, `st.feedback("stars")`), 메모(최대 1000자), 즐겨찾기를 달 수 있다. | 필수 |
| F3-15 | 저장한 레시피의 제목과 조리 순서를 사용자가 직접 고칠 수 있다. 원본 스냅숏은 따로 보관해서 "원래대로" 되돌릴 수 있다. | 권장 |
| F3-16 | 저장한 레시피를 지울 수 있다. 사용자당 최대 500개까지 저장할 수 있다(Neon 무료 저장 공간 보호). | 필수 |

## 6. 시스템 구성

```
브라우저 ──(웹소켓)── Streamlit 앱 (Community Cloud)
                        │  st.login ──▶ Google OIDC
                        │  st.connection("neon") ──▶ Neon Postgres (무료)
                        └─ core/openrouter.py ──▶ OpenRouter
```

**추가되는 파일**
```
app_pages/
  my_recipes.py          # 내 레시피 목록과 상세
  profile.py             # 프로필, 계정 삭제
core/
  auth.py                # 현재 사용자 확인, 첫 로그인 처리
  db.py                  # 테이블 생성(마이그레이션), 쿼리 함수
  repository.py          # 프로필과 저장 레시피 CRUD (항상 user_id 조건 포함)
```

**추가 의존성**: `streamlit[auth]`(Authlib 포함), `SQLAlchemy`, `psycopg[binary]`

**`.streamlit/secrets.toml`에 추가하는 값** (로컬과 Community Cloud 양쪽)
```toml
[auth]
redirect_uri = "https://<앱이름>.streamlit.app/oauth2callback"   # 로컬은 http://localhost:8501/oauth2callback
cookie_secret = "<무작위 긴 문자열>"

[auth.google]
client_id = "<Google OAuth 클라이언트 ID>"
client_secret = "<Google OAuth 클라이언트 보안 비밀>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[connections.neon]
url = "postgresql+psycopg://<사용자>:<비밀번호>@<호스트>/<DB>?sslmode=require"
```
- 로컬용과 배포용은 `redirect_uri`가 다르다. Google Cloud 콘솔의 OAuth 클라이언트에도 두 주소를 모두 등록한다.
- `cookie_secret`과 DB 비밀번호는 `.env.example`처럼 자리표시자만 담은 `.streamlit/secrets.toml.example`로 문서화한다.

## 7. 데이터 모델 (Postgres)

```sql
CREATE TABLE users (
  id          BIGSERIAL PRIMARY KEY,
  oidc_sub    TEXT NOT NULL,
  provider    TEXT NOT NULL DEFAULT 'google',
  email       TEXT,                       -- 표시용
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, oidc_sub)
);

CREATE TABLE profiles (
  user_id           BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  nickname          TEXT NOT NULL CHECK (char_length(nickname) BETWEEN 2 AND 20),
  allergies         JSONB NOT NULL DEFAULT '[]',
  diet              JSONB NOT NULL DEFAULT '[]',
  disliked          JSONB NOT NULL DEFAULT '[]',
  skill_level       TEXT NOT NULL DEFAULT 'normal' CHECK (skill_level IN ('beginner','normal','expert')),
  default_servings  INT  NOT NULL DEFAULT 2 CHECK (default_servings BETWEEN 1 AND 6),
  cuisines          JSONB NOT NULL DEFAULT '[]',
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE saved_recipes (
  id               BIGSERIAL PRIMARY KEY,
  user_id          BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title            TEXT NOT NULL,          -- 검색과 정렬용 (사용자가 고칠 수 있음)
  recipe           JSONB NOT NULL,         -- 현재 레시피 (사용자가 고친 내용 반영)
  original         JSONB NOT NULL,         -- 저장할 때의 원본 스냅숏
  source_input     JSONB NOT NULL,         -- 생성에 쓴 재료 목록과 조건
  ingredient_names TEXT NOT NULL,          -- 재료명 검색용 (공백으로 이은 문자열)
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
CREATE INDEX idx_saved_user_created ON saved_recipes (user_id, created_at DESC);
```
- 테이블 생성은 앱이 시작될 때 `CREATE TABLE IF NOT EXISTS`로 한 번 실행한다(`st.cache_resource`로 한 번만).
- 검색은 `title ILIKE` 또는 `ingredient_names ILIKE`로 시작한다. 레시피가 많아지면 `pg_trgm` 인덱스를 검토한다.

## 8. 로직 함수 (`core/repository.py`)

모든 함수는 첫 인자로 현재 사용자의 `user_id`를 받는다. 그리고 모든 쿼리에 `WHERE user_id = :user_id`를 붙인다. 화면 코드는 `user_id`를 직접 만들지 않고, `core.auth.current_user_id()`가 `st.user`에서 찾은 값만 쓴다.

| 함수 | 설명 |
|---|---|
| `get_or_create_user(provider, sub, email, name)` | 첫 로그인 처리. `user_id`를 돌려준다. |
| `get_profile(user_id)` / `update_profile(user_id, data)` | 프로필 읽기와 쓰기 |
| `save_recipe(user_id, recipe, source_input, model)` | 저장. 중복이면 `AlreadySaved(id)`, 개수 초과면 `LimitReached` 예외 |
| `list_recipes(user_id, sort, favorite_only, query, offset, limit=20)` | 목록(요약 필드만) |
| `get_recipe(user_id, recipe_id)` | 상세. 다른 사용자의 레시피면 `None` |
| `update_recipe(user_id, recipe_id, **fields)` | 별점, 메모, 즐겨찾기, 제목·조리 순서 수정 |
| `restore_recipe(user_id, recipe_id)` | 원본 스냅숏으로 되돌리기 |
| `delete_recipe(user_id, recipe_id)` | 삭제 |
| `delete_account(user_id)` | `users` 행 삭제(나머지는 `ON DELETE CASCADE`로 함께 삭제) |

**2단계 변경**: `generate_recipes()`를 부르기 전에, 로그인한 상태면 프로필을 읽어 조건과 합친다.
- 알레르기: 프로필 값과 요청 값의 합집합으로 강제 적용한다.
- 싫어하는 재료: 프롬프트에 "가능하면 피하기"로 넣는다.
- 인분과 요리 종류: 요청 값이 있으면 요청 값을, 없으면 프로필 값을 쓴다.
- 요리 실력: 프롬프트 지시에 반영한다.

## 9. 화면 요구사항

| 페이지 / 요소 | 구성 |
|---|---|
| 사이드바 | 로그인 상태, 로그인·로그아웃 버튼. 로그인 상태면 "내 레시피", "프로필" 메뉴가 보인다. |
| 레시피 카드(2단계) | "저장" 버튼. 이미 저장한 레시피는 "저장됨 ✓"으로 표시한다. 로그아웃 상태에서 누르면 로그인 안내를 보여 준다. |
| 내 레시피 | 검색창(`st.text_input`), 정렬(`st.segmented_control`), 즐겨찾기만 보기(`st.toggle`), 카드 목록, "더 보기" 버튼. 레시피가 없으면 "냉장고 사진으로 첫 레시피를 찾아보세요" 버튼을 보여 준다. |
| 저장한 레시피 상세 | 2단계 상세 내용에 별점(`st.feedback("stars")`), 메모(`st.text_area`), 즐겨찾기, 편집, 원래대로, 삭제 버튼을 더한다. "생성할 때 쓴 재료"는 `st.expander`로 접어 둔다. |
| 프로필 | `st.form` 하나로 묶는다. 알레르기와 싫어하는 재료는 `st.multiselect(accept_new_options=True)`. 알레르기 칸 옆에 "추천 레시피에서 항상 제외됩니다"라고 안내한다. |
| 계정 삭제 | 프로필 페이지 맨 아래의 `st.expander("계정 삭제")` 안에 둔다. 빨간 버튼과 확인 문구 입력. |

- 사용자가 입력한 메모와 닉네임, 모델이 만든 글은 마크다운이나 HTML로 해석되지 않게 보여 준다(`st.text`나 이스케이프 처리). Streamlit은 기본적으로 HTML을 막지만, 마크다운 링크와 이미지 문법은 해석하기 때문이다.

## 10. 비기능 요구사항

| 구분 | 요구사항 |
|---|---|
| 보안 | 신원은 `st.user`(Streamlit이 서명한 쿠키)로만 판단한다. 모든 DB 쿼리에 `user_id` 조건을 붙이고, 매개변수 바인딩만 쓴다(문자열로 SQL을 이어 붙이지 않음). |
| 비밀 값 | Google 클라이언트 보안 비밀, `cookie_secret`, DB URL은 `st.secrets`에만 둔다. `.streamlit/secrets.toml`은 커밋하지 않는다. |
| 개인정보 | 알레르기와 식이 조건은 건강 관련 정보로 취급한다. 로그에 남기지 않고, 계정을 삭제하면 즉시 지운다. 수집 항목(이메일, 이름, 프로필, 저장 레시피)을 프로필 페이지에 안내한다. 앱과 DB 위치(Community Cloud는 미국, Neon은 프로젝트를 만들 때 고른 지역)를 안내한다. |
| 입력 검증 | 저장하는 `recipe` JSON은 2단계 레시피 스키마로 다시 검증한다. JSON 하나의 크기는 64KB로 제한한다. |
| 성능 | 목록 조회는 500건 기준 1초 이내. Neon이 잠들어 있다가 깨어나면 첫 쿼리가 몇 초 늦을 수 있으므로, 연결 풀에 `pool_pre_ping=True`를 켜고 첫 조회에 스피너를 보여 준다. |
| 무료 한도 | Neon 무료: 프로젝트당 1GB, 월 100 CU-시간. 사용자당 500개 제한과 64KB 제한으로 저장 공간을 보호한다. CU-시간을 다 쓰면 다음 달까지 DB가 멈추므로(데이터는 지워지지 않음), 이때는 "저장 기능을 잠시 쓸 수 없어요"라고 안내하고 1·2단계는 계속 쓸 수 있게 한다. |

## 11. 배포 추가 작업

1. Neon(https://neon.com)에서 무료 프로젝트를 만들고 연결 문자열을 복사한다.
2. Google Cloud 콘솔에서 OAuth 동의 화면과 "웹 애플리케이션" OAuth 클라이언트를 만든다. 승인된 리디렉션 URI에 `http://localhost:8501/oauth2callback`과 `https://<앱이름>.streamlit.app/oauth2callback`을 넣는다.
3. Community Cloud 앱 설정의 Secrets에 6장의 `[auth]`, `[auth.google]`, `[connections.neon]` 값을 추가한다(배포용 `redirect_uri` 사용).
4. `requirements.txt`에 추가 의존성을 넣고 푸시하면 자동으로 다시 배포된다.

## 12. 수용 기준

- [ ] Google로 로그인하고, 로그아웃한 뒤 다시 로그인하면 같은 프로필과 저장 레시피가 보인다.
- [ ] 로그아웃 상태에서는 "내 레시피"와 "프로필" 메뉴가 보이지 않고, 1·2단계는 그대로 쓸 수 있다.
- [ ] 사용자 A의 `user_id`로 사용자 B의 저장 레시피 ID를 조회, 수정, 삭제하면 모두 실패한다(`repository` 단위 테스트).
- [ ] 프로필 알레르기에 "달걀"을 넣으면, 조건 화면에서 알레르기를 지워도 생성된 레시피에 달걀이 나오지 않는다.
- [ ] 같은 레시피를 두 번 저장하면 두 번째에 "이미 저장됨" 안내가 나오고, 목록에는 1개만 있다.
- [ ] 저장한 레시피의 조리 순서를 고친 뒤 "원래대로"를 누르면 저장할 때의 내용으로 돌아간다.
- [ ] 메모에 `[링크](https://example.com)`나 `<script>alert(1)</script>`를 넣어도 링크나 스크립트로 바뀌지 않고 글자 그대로 보인다.
- [ ] 계정을 삭제하면 `users`, `profiles`, `saved_recipes`에서 그 사용자의 행이 모두 사라지고 로그아웃된다.
- [ ] 앱을 재부팅(Community Cloud의 Reboot)해도 저장 레시피가 남아 있다.
- [ ] `git status`에 `.streamlit/secrets.toml`이 나타나지 않는다.

## 13. 위험 요소와 대응

| 위험 | 대응 |
|---|---|
| `st.login`을 거치면서 세션 상태가 초기화되어, 로그인 전에 만든 레시피가 사라질 수 있음 | 구현할 때 실제 동작을 확인한다. 초기화된다면, 사진을 올리기 전에 로그인하도록 첫 화면에서 권하고, 저장 버튼의 로그인 안내에 "로그인하면 지금 레시피는 다시 만들어야 해요"라고 알린다. |
| Google OAuth 앱이 "테스트" 상태면 등록한 테스트 사용자만 로그인할 수 있음 | 학습·시연 단계에서는 테스트 사용자로 운영하고, 공개하려면 OAuth 동의 화면을 "프로덕션"으로 게시한다(기본 범위인 openid, email, profile만 쓰면 Google 심사가 필요 없을 가능성이 높으나, 게시할 때 확인한다). |
| Neon 무료 한도(CU-시간) 소진 | 5분 무활동 시 자동으로 잠드는 기능 덕에 소규모 사용에서는 한도에 거의 닿지 않는다. 닿으면 10장대로 저장 기능만 멈춘다. |
| 저장된 스냅숏이 2단계 스키마 변경과 맞지 않게 됨 | `schema_version`을 기록하고, 읽을 때 버전별 변환 함수를 거친다. |
| 무료 서비스 정책 변경 | Community Cloud, Neon, OpenRouter의 무료 조건은 바뀔 수 있다(2026-10 확인). 연결 정보와 모델 ID를 모두 `st.secrets`로 분리해 두어, 다른 서비스로 옮기기 쉽게 한다. |

## 14. 미결정 사항

- 무료 사용량 보호를 위해 1·2단계도 로그인한 사용자만 쓰게 할지 여부. 그렇게 하면 사용자별 하루 요청 제한도 DB로 정확하게 셀 수 있다.
- 1단계 인식 기록(재료 목록)을 계정에 남길지 여부. 남긴다면 "최근 냉장고 재료로 다시 추천" 기능을 붙일 수 있다.
- 저장한 레시피 내보내기(인쇄용 화면, 텍스트 파일 다운로드 `st.download_button`) 제공 여부
