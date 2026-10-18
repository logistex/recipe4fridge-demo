# PRD 3단계: 사용자 프로필과 레시피 저장

| 항목 | 내용 |
|---|---|
| 제품 | 냉장고 사진 기반 레시피 추천 웹 애플리케이션 |
| 단계 | 3 / 3 (사용자 프로필, 레시피 저장) |
| 사용 모델 | 새로 추가하는 모델 없음 (2단계 생성 요청에 프로필 정보를 반영) |
| 이전 단계 | [PRD_step1.md](PRD_step1.md), [PRD_step2.md](PRD_step2.md) |
| 작성일 | 2026-10-18 |

## 1. 배경과 목적

2단계까지 만든 레시피는 화면을 닫으면 사라집니다. 알레르기나 선호 조건도 매번 다시 입력해야 합니다. 3단계에서는 사용자 계정과 프로필을 만들어 다음 두 가지를 해결합니다.
1. 마음에 드는 레시피를 저장하고, 나중에 다시 보고, 메모와 평가를 남길 수 있다.
2. 프로필에 적어 둔 알레르기, 식이 조건, 기본 인분이 레시피 생성 조건에 자동으로 채워진다.

## 2. 목표와 비목표

**목표**
- 이메일과 비밀번호로 가입, 로그인, 로그아웃할 수 있다.
- 프로필(닉네임, 알레르기, 식이 조건, 싫어하는 재료, 요리 실력, 기본 인분)을 관리할 수 있다.
- 2단계 레시피를 저장하고, 목록 보기, 상세 보기, 메모, 별점, 즐겨찾기, 삭제를 할 수 있다.
- 로그인하지 않아도 1·2단계 기능은 그대로 쓸 수 있다. 저장할 때만 로그인을 요구한다.

**비목표 (3단계에서 하지 않음)**
- 소셜 로그인(OAuth), 레시피 공유와 공개 피드, 댓글
- 여러 기기 동시 편집 충돌 처리, 실시간 동기화
- 비밀번호 재설정 이메일 발송 (메일 서버가 필요하므로 향후 과제)

## 3. 사용자 시나리오

**프로필 설정**
1. 사용자가 상단의 "로그인"을 눌러 회원가입한다(이메일, 비밀번호, 닉네임).
2. 가입 직후 프로필 설정 화면이 나온다. 알레르기("새우, 땅콩"), 싫어하는 재료("고수"), 기본 인분(2), 요리 실력("초보")을 입력하고 저장한다.

**프로필이 반영된 추천**
3. 냉장고 사진을 올리고 재료를 확정한 뒤 레시피 조건 화면으로 가면, 알레르기, 싫어하는 재료, 인분이 프로필 값으로 미리 채워져 있다. 이번 요청에서만 바꿀 수도 있다.

**레시피 저장과 다시 보기**
4. 추천받은 레시피 카드에서 "저장"을 누르면 "내 레시피"에 저장된다.
5. "내 레시피" 화면에서 저장한 레시피를 최신순, 별점순, 즐겨찾기만 보기로 정렬하거나 필터링하고, 제목이나 재료로 검색한다.
6. 레시피를 만들어 본 뒤 별점과 메모("간장을 조금 줄이면 더 맛있음")를 남긴다.

**비로그인 사용자의 저장**
7. 로그인하지 않은 사용자가 "저장"을 누르면 로그인 창이 뜬다. 로그인하면 그 레시피가 자동으로 저장된다.

## 4. 기능 요구사항

### 4.1 계정

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-1 | 이메일, 비밀번호(8자 이상, 영문과 숫자 포함), 닉네임(2–20자)으로 가입한다. 이메일은 중복될 수 없다. | 필수 |
| F3-2 | 로그인하면 HttpOnly, Secure, SameSite=Lax 쿠키로 세션을 유지한다. 세션 유효기간은 14일이다. | 필수 |
| F3-3 | 로그아웃하면 서버의 세션을 무효화한다. | 필수 |
| F3-4 | 같은 이메일로 로그인에 5회 연속 실패하면 15분 동안 로그인을 막는다. | 필수 |
| F3-5 | 비밀번호는 로그인한 상태에서 현재 비밀번호를 확인한 뒤에만 바꿀 수 있다. | 필수 |
| F3-6 | 계정을 삭제하면 프로필과 저장한 레시피를 모두 함께 지운다(복구 불가 안내 후 비밀번호 재확인). | 필수 |

### 4.2 프로필

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-7 | 프로필 항목: 닉네임, 알레르기(태그 최대 20개), 식이 조건(채식, 비건, 글루텐 제외 등 다중 선택), 싫어하는 재료(태그 최대 20개), 요리 실력(초보/보통/능숙), 기본 인분(1–6), 선호 요리 종류(다중 선택). | 필수 |
| F3-8 | 2단계 조건 화면을 열면 프로필 값을 기본값으로 채운다. 이번 요청에서 바꾼 값은 프로필에 저장하지 않는다. | 필수 |
| F3-9 | 프로필의 알레르기는 2단계 서버 필터(F2-7)에도 자동으로 적용된다. 사용자가 조건 화면에서 지워도 서버는 프로필 알레르기를 합쳐서 적용한다. | 필수 |
| F3-10 | 싫어하는 재료는 프롬프트에 "가능하면 쓰지 않기"로 전달한다. 알레르기와 달리 서버에서 강제로 걸러 내지는 않는다. | 필수 |
| F3-11 | 요리 실력이 "초보"이면 프롬프트에 "단계를 더 잘게 나누고 용어를 풀어서 설명"을 덧붙인다. | 권장 |

### 4.3 레시피 저장

| ID | 요구사항 | 우선순위 |
|---|---|---|
| F3-12 | 2단계 레시피 객체 전체를 그 시점 그대로(스냅숏) 저장한다. 생성에 쓴 재료 목록과 조건도 함께 저장한다. | 필수 |
| F3-13 | 같은 사용자가 같은 레시피(제목과 재료 목록이 같음)를 다시 저장하면 새로 만들지 않고 "이미 저장됨"으로 안내한다. | 필수 |
| F3-14 | "내 레시피" 목록: 페이지당 20개, 최신순(기본), 별점순, 조리 시간순 정렬. 즐겨찾기만 보기 필터. 제목과 재료명 검색. | 필수 |
| F3-15 | 저장한 레시피에 별점(1–5), 메모(최대 1000자), 즐겨찾기를 달 수 있다. | 필수 |
| F3-16 | 저장한 레시피의 제목과 조리 순서를 사용자가 직접 고칠 수 있다. 원본 스냅숏은 따로 보관해서 "원래대로" 되돌릴 수 있다. | 권장 |
| F3-17 | 저장한 레시피를 지울 수 있다. 사용자당 최대 500개까지 저장할 수 있다. | 필수 |
| F3-18 | 비로그인 상태에서 저장을 누르면, 로그인 후 그 레시피를 자동으로 저장한다(브라우저에 대기 중인 레시피를 임시 보관). | 권장 |

## 5. 시스템 구성

1·2단계와 같은 FastAPI 서버에 인증, 프로필, 저장 기능을 더한다.
```
app/
  db.py                    # SQLite 연결, 마이그레이션
  models.py                # SQLAlchemy 모델 (또는 sqlite3 + SQL 파일)
  security.py              # 비밀번호 해시(argon2), 세션, CSRF
  routers/auth.py
  routers/profile.py
  routers/saved_recipes.py
  services/recipe_gen.py   # 2단계 코드. 프로필을 조건과 병합하는 부분 추가
data/
  app.db                   # SQLite 파일 (.gitignore에 추가)
```
- **DB**: SQLite(파이썬 내장, 3.50.4 확인)를 쓴다. 학습용 단일 서버 구성에 충분하고, 나중에 PostgreSQL로 옮기기 쉽도록 SQLAlchemy를 쓴다.
- **비밀번호**: `argon2-cffi`로 해시한다. 평문 비밀번호는 저장하지도 로그에 남기지도 않는다.
- **세션**: DB의 `sessions` 테이블에 무작위 토큰(32바이트)의 해시를 저장하고, 쿠키에는 원본 토큰을 담는다.
- **CSRF**: 상태를 바꾸는 요청(POST, PATCH, PUT, DELETE)에는 `X-CSRF-Token` 헤더를 요구한다(double-submit 방식).
- `.gitignore`에 `data/`를 추가한다. 세션 서명 키 같은 새 비밀 값은 `.env`에 넣고, `.env.example`에 자리표시자를 더한다.

## 6. 데이터 모델

```sql
CREATE TABLE users (
  id            INTEGER PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE profiles (
  user_id           INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  nickname          TEXT NOT NULL,
  allergies         TEXT NOT NULL DEFAULT '[]',   -- JSON 배열
  diet              TEXT NOT NULL DEFAULT '[]',   -- JSON 배열
  disliked          TEXT NOT NULL DEFAULT '[]',   -- JSON 배열
  skill_level       TEXT NOT NULL DEFAULT 'normal' CHECK (skill_level IN ('beginner','normal','expert')),
  default_servings  INTEGER NOT NULL DEFAULT 2 CHECK (default_servings BETWEEN 1 AND 6),
  cuisines          TEXT NOT NULL DEFAULT '[]',   -- JSON 배열
  updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sessions (
  token_hash  TEXT PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at  TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE saved_recipes (
  id             INTEGER PRIMARY KEY,
  user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title          TEXT NOT NULL,          -- 검색과 정렬용 (사용자가 고칠 수 있음)
  recipe         TEXT NOT NULL,          -- 현재 레시피 JSON (사용자가 고친 내용 반영)
  original       TEXT NOT NULL,          -- 저장할 때의 원본 스냅숏 JSON
  source_input   TEXT NOT NULL,          -- 생성에 쓴 재료 목록과 조건 JSON
  dedupe_key     TEXT NOT NULL,          -- 제목 + 정렬한 재료명의 해시
  time_minutes   INTEGER,
  rating         INTEGER CHECK (rating BETWEEN 1 AND 5),
  memo           TEXT CHECK (length(memo) <= 1000),
  is_favorite    INTEGER NOT NULL DEFAULT 0,
  model          TEXT NOT NULL,          -- 생성한 모델 ID
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (user_id, dedupe_key)
);
CREATE INDEX idx_saved_user_created ON saved_recipes(user_id, created_at DESC);
```
- 외래 키가 동작하도록 연결할 때마다 `PRAGMA foreign_keys = ON`을 실행한다.
- 재료명 검색은 `recipe` JSON의 재료명을 모은 별도 열이나 FTS5 가상 테이블로 구현한다. 처음에는 `LIKE` 검색으로 시작해도 된다.

## 7. API 명세

모든 응답의 오류 형식은 1·2단계와 같은 `{ "error": { "code", "message" } }`이다. 로그인이 필요한 API에 세션 없이 요청하면 `401 UNAUTHORIZED`, 다른 사용자의 데이터에 접근하면 `404 NOT_FOUND`를 돌려준다(존재 여부를 숨기려고 403 대신 404를 씀).

### 인증
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/auth/signup` | `{ email, password, nickname }` → 가입 후 바로 로그인. 이메일 중복이면 `409 EMAIL_TAKEN` |
| POST | `/api/auth/login` | `{ email, password }` → 세션 쿠키 발급. 실패하면 `401 INVALID_CREDENTIALS`, 잠기면 `429 LOGIN_LOCKED` |
| POST | `/api/auth/logout` | 세션 무효화 |
| GET | `/api/auth/me` | 로그인 상태와 `{ id, email, nickname }` |
| PUT | `/api/auth/password` | `{ current_password, new_password }` |
| DELETE | `/api/auth/account` | `{ password }` → 계정과 모든 데이터 삭제 |

### 프로필
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/profile` | 내 프로필 |
| PUT | `/api/profile` | 프로필 전체 수정(4.2의 항목) |

### 저장한 레시피
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/saved-recipes` | `{ recipe, source_input, model }` → 저장. 이미 있으면 `409 ALREADY_SAVED`와 기존 `id`. 개수 초과면 `409 LIMIT_REACHED` |
| GET | `/api/saved-recipes?sort=recent\|rating\|time&favorite=true&q=달걀&page=1` | 목록(요약 필드만) |
| GET | `/api/saved-recipes/{id}` | 상세(`recipe`, 메모, 별점 등) |
| PATCH | `/api/saved-recipes/{id}` | `rating`, `memo`, `is_favorite`, `recipe`(제목과 조리 순서 수정) 중 일부 |
| POST | `/api/saved-recipes/{id}/restore` | 원본 스냅숏으로 되돌리기 |
| DELETE | `/api/saved-recipes/{id}` | 삭제 |

### 2단계 API 변경
- `POST /api/recipes/generate`: 로그인한 상태면 서버가 프로필을 읽어 `preferences`와 합친다.
  - 알레르기는 프로필 값과 요청 값의 합집합으로 강제 적용한다.
  - 싫어하는 재료는 프롬프트에 "가능하면 피하기"로 넣는다.
  - 인분과 요리 종류는 요청 값이 있으면 요청 값을, 없으면 프로필 값을 쓴다.
  - 요리 실력은 프롬프트 지시에 반영한다.
- 비로그인 상태의 동작은 2단계와 같다.

## 8. 화면 요구사항

- **상단 바**: 비로그인이면 "로그인", 로그인했으면 닉네임 메뉴(내 레시피, 프로필, 로그아웃)를 보여 준다.
- **로그인과 가입 창**: 모달 하나에 탭 두 개. 비밀번호 규칙을 실시간으로 안내한다.
- **프로필 화면**: 태그 입력(알레르기, 싫어하는 재료), 다중 선택 칩(식이 조건, 요리 종류), 숫자 선택(기본 인분). 알레르기 칸 옆에 "추천 레시피에서 항상 제외됩니다"라고 안내한다.
- **레시피 카드와 상세**: 저장 버튼(북마크 아이콘)을 둔다. 저장된 레시피는 채워진 아이콘으로 바뀌고, 다시 누르면 "내 레시피에서 삭제할까요?"라고 확인한다.
- **내 레시피 화면**: 검색창, 정렬 선택, 즐겨찾기 필터, 카드 그리드. 레시피가 없으면 "냉장고 사진으로 첫 레시피를 찾아보세요" 버튼을 보여 준다.
- **저장한 레시피 상세**: 2단계 상세 화면에 별점, 메모, 즐겨찾기, 편집, 원래대로, 삭제를 더한다. "생성할 때 쓴 재료"를 접어서 보여 준다.
- **계정 설정**: 비밀번호 변경, 계정 삭제(위험 동작이므로 빨간색으로 구분하고 비밀번호를 다시 확인).

## 9. 비기능 요구사항

| 구분 | 요구사항 |
|---|---|
| 보안 | argon2 해시, HttpOnly·Secure·SameSite 쿠키, CSRF 토큰, 로그인 실패 제한. 모든 저장 레시피 조회에 `user_id` 조건을 붙인다. |
| 개인정보 | 알레르기와 식이 조건은 건강 관련 정보로 취급한다. 로그에 남기지 않고, 계정을 삭제하면 즉시 지운다. 수집 항목을 가입 화면에 안내한다. |
| 입력 검증 | 모든 요청 본문은 pydantic으로 검증한다. 저장하는 `recipe` JSON은 2단계 응답 스키마로 다시 검증해서 임의 데이터가 들어오지 않게 한다. JSON 하나의 크기는 64KB로 제한한다. |
| 출력 | 레시피, 메모, 닉네임을 화면에 넣을 때는 `textContent`로 넣어서 XSS를 막는다(`innerHTML` 금지). |
| 성능 | 저장 레시피 목록 API는 500건 기준 200ms 이내. |
| 백업 | `data/app.db`는 git에 넣지 않는다. 필요하면 SQLite `.backup` 명령으로 백업한다. |

## 10. 수용 기준

- [ ] 가입하고, 로그아웃한 뒤 다시 로그인하면 같은 프로필과 저장한 레시피가 보인다.
- [ ] 비밀번호를 5회 틀리면 15분 동안 로그인이 막히고 안내 문구가 나온다.
- [ ] 사용자 A의 세션으로 사용자 B의 저장 레시피 ID를 조회, 수정, 삭제하면 모두 404가 나온다.
- [ ] 프로필 알레르기에 "달걀"을 넣으면, 조건 화면에서 알레르기를 지워도 생성된 레시피에 달걀이 나오지 않는다.
- [ ] 같은 레시피를 두 번 저장하면 두 번째에 "이미 저장됨" 안내가 나오고, 목록에는 1개만 있다.
- [ ] 저장한 레시피의 조리 순서를 고친 뒤 "원래대로"를 누르면 저장할 때의 내용으로 돌아간다.
- [ ] 메모에 `<script>alert(1)</script>`를 넣어도 스크립트가 실행되지 않고 글자로만 보인다.
- [ ] 계정을 삭제하면 `users`, `profiles`, `sessions`, `saved_recipes`에서 그 사용자의 행이 모두 사라진다.
- [ ] 비로그인 상태에서 저장을 누르고 로그인하면 그 레시피가 저장되어 있다.
- [ ] `data/app.db`가 `git status`에 나타나지 않는다.

## 11. 위험 요소와 대응

| 위험 | 대응 |
|---|---|
| 직접 만든 인증 기능의 보안 허점 | 검증된 라이브러리(argon2-cffi, FastAPI 보안 유틸)를 쓰고, 10장의 보안 수용 기준을 자동화 테스트로 확인한다. |
| 프로필 알레르기와 요청 조건의 충돌 | 알레르기는 항상 합집합으로 처리하고, 화면에 "프로필 알레르기는 항상 적용됩니다"라고 안내한다. |
| 저장된 스냅숏이 2단계 스키마 변경과 맞지 않게 됨 | 서버가 저장할 때 `recipe` JSON에 `schema_version`(현재 1)을 붙이고, 읽을 때 버전별 변환 함수를 거친다. |
| SQLite 동시 쓰기 제한 | 학습용 단일 서버 규모에서는 문제없다. WAL 모드를 켜 두고, 사용자가 많아지면 PostgreSQL로 옮긴다. |

## 12. 미결정 사항

- 비밀번호 재설정 방법(메일 발송을 붙일지, 관리자가 초기화할지)
- 1단계 인식 기록(재료 목록)을 계정에 남길지 여부. 남긴다면 "최근 냉장고 재료로 다시 추천" 기능을 붙일 수 있다.
- 저장한 레시피 내보내기(PDF, 인쇄용 화면) 제공 여부
