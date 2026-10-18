# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

냉장고 사진에서 식재료를 인식하고 레시피를 추천하는 Streamlit 앱입니다. OpenRouter의 무료 모델을 쓰고, Streamlit Community Cloud에 무료로 배포합니다. **모든 구성이 무료여야 한다**는 조건이 있습니다.

- 기획은 `docs/PRD_step1.md`(식재료 인식, 구현 완료), `PRD_step2.md`(레시피 생성, 구현 완료), `PRD_step3.md`(프로필과 저장: `st.login` Google OIDC + Neon Postgres)입니다. 구현은 이 순서를 따르며, 각 PRD에 데이터 형식, 화면 구성, 수용 기준이 있습니다.
- OpenRouter 무료 모델은 계정 전체에 하루 50회 한도가 있습니다. 실제 API 호출은 꼭 필요할 때만 하고, 테스트는 가짜 클라이언트로 합니다.

## 명령어

Windows 기준이며 프로젝트 루트에서 실행합니다. 의존성은 `.venv`에 있습니다.

```bash
.venv/Scripts/streamlit run streamlit_app.py            # 앱 실행 (http://localhost:8501)
.venv/Scripts/python -m pytest                          # 전체 테스트
.venv/Scripts/python -m pytest tests/test_vision.py::test_extract_json_handles_fences_and_prose   # 테스트 하나
python scripts/test_openrouter.py [text|image]          # 실제 API 동작 확인 (무료 한도 사용)
```

- Git Bash에서 한글 출력이 깨지면 `PYTHONIOENCODING=utf-8`을 붙입니다.
- `requirements.txt`는 Community Cloud가 설치하는 런타임 의존성, `requirements-dev.txt`는 여기에 pytest를 더한 것입니다. 버전은 고정합니다.

## 구조

- `streamlit_app.py`가 `st.navigation`으로 `app_pages/`의 페이지를 등록합니다. 새 단계의 페이지는 여기에 `st.Page`로 추가합니다.
- `core/`는 화면과 분리된 로직입니다. `core/runtime.py`만 Streamlit에 의존하며(`st.cache_resource`로 클라이언트와 하루 사용량 카운터를 세션 간에 공유), 나머지는 Streamlit 없이 테스트할 수 있습니다.
  - `openrouter.py`: `chat()`은 429/502/503에 10초 뒤 한 번 더 시도합니다. `chat_with_fallback()`은 기본 모델이 그래도 실패하면 예비 모델을 기다림 없이 한 번씩 시도하고 `(응답한 모델, 응답)`을 돌려줍니다(401은 넘어가지 않음). 전체 기한(`deadline_seconds`)을 넘기면 멈춥니다. OpenRouter는 HTTP 200 본문에 `error` 객체를 담아 보내기도 하므로 그 코드를 상태로 다룹니다. 모든 실패는 `core.errors.AppError(code)`로 바뀌며, 화면은 `e.message`(한국어)만 보여 줍니다.
  - `vision.py`: `prepare_image()`가 사진을 자동 변환합니다(EXIF 회전 반영 후 제거, 긴 변 1024px에서 시작해 300KB 이하가 될 때까지 품질→크기 순으로 낮춤, 최소 640px). 그다음 기본·예비 모델 호출 → JSON 추출(코드 블록·설명 문장 허용) → 정규화. 해석에 실패하면 방금 응답한 모델에 1회 다시 요청합니다. `response_format`은 지원하는 모델에만 보냅니다.
  - OpenRouter는 처리 중에 연결 유지용 공백을 보내서 httpx 읽기 제한 시간이 계속 다시 시작됩니다. 그래서 `_post()`는 응답을 스트림으로 받으며 경과 시간을 직접 재고, 요청당 제한(기본 모델 60초, 예비 모델 30초)을 넘기면 끊습니다. httpx `timeout`만으로 시간을 제한하려 하지 마세요.
  - `ingredient_names.py`: 재료명에 한글이 아닌 문자가 섞이면 `name_suspect`(화면에 "⚠ 이름 확인")로 표시하고, 흔한 재료 약 200개의 분류 사전으로 모델 분류를 덮어씁니다(2글자 이상은 끝말 일치, 긴 말 우선).
  - 예비 모델 목록은 `config.DEFAULT_FALLBACK_VISION_MODELS`(선정 이유는 주석과 PRD 1단계 7장)이고, `runtime.vision_model_plan()`이 OpenRouter 모델 목록(6시간 캐시)으로 지금 무료로 이미지를 받는 모델만 남깁니다. OpenRouter API에는 모델별 인기 수치가 없으므로, 목록을 바꿀 때는 실제로 한 번씩 호출해 확인합니다.
  - `fridge_flow.py`: 같은 사진(SHA-256)은 다시 인식하지 않고, 세션당 분당 제한과 앱 전체 하루 제한을 확인한 뒤에만 모델을 부릅니다.
- Streamlit은 위젯을 조작할 때마다 스크립트 전체를 다시 실행합니다. 그래서 모델 호출은 버튼의 `on_click`으로 `pending` 플래그를 세운 실행에서만 일어나고, 끝나면 `st.rerun()`합니다. 결과는 `st.session_state`에 둡니다. 2단계 이후의 모델 호출도 같은 방식을 따릅니다.
- 인식 결과는 `fridge_flow.init_rows()`로 `st.session_state["ing_rows"]`에 행으로 옮겨, 행마다 `name_{id}`, `qty_{id}`, `unit_{id}`, `del_{id}` 위젯을 한 줄에 그립니다(`id`는 `<사진 해시 8자>-<순번>`). 한 줄 배치는 `st.container(horizontal=True, wrap=False)`와 고정 너비로 합니다. `st.columns`는 휴대폰에서 줄이 넘치고, 수량 칸이 130px보다 좁으면 −/+ 단추가 사라집니다.
- 2단계 입력은 `st.session_state["confirmed_ingredients"]`(`name`, `quantity`, `unit`, `category` 목록)입니다.
- 2단계(`app_pages/recipes.py`, `core/recipe_gen.py`, `core/recipe_flow.py`, `core/pantry.py`):
  - 텍스트 모델(Nemotron)은 `reasoning: {"enabled": false}`로 부릅니다. 추론을 켜면 90초를 넘기고, 끄면 21~35초입니다. 출력은 `json_schema`로 강제하지만 서버에서 다시 검증합니다.
  - 모델이 준 보유 여부·알레르기 준수는 믿지 않습니다. `pantry.py`가 대표 이름(손질법 제거 + 동의어)으로 보유 여부를 다시 계산하고, `recipe_gen.reject_reason()`이 알레르기(파생 식품 포함)·채식·추가 구매 수·시간·요리 종류·중복으로 걸러 냅니다. 모자라면 모자란 수만큼 한 번 더 요청합니다.
  - 생성 결과는 `state["recipe_result"]`, 3단계 저장용 입력은 `state["recipe_input"]`에 둡니다. 조건 위젯은 `pref_*` key로 세션에 남습니다.
- 페이지 이동은 `st.switch_page("app_pages/...")`입니다. 그래서 화면 테스트는 페이지 파일이 아니라 `streamlit_app.py`를 `AppTest`로 띄우고, 2단계는 `at.switch_page(...)`로 엽니다.
- `tests/test_fridge_page.py`는 `AppTest`로 화면을 돌리며, `core.vision.recognize_ingredients`와 `core.runtime.vision_model_plan`(네트워크 호출)을 monkeypatch합니다. 페이지가 매 실행마다 `from core... import ...`를 다시 하기 때문에 이 방식이 통합니다.
- `core/` 파일을 고친 뒤 실행 중인 Streamlit 서버는 예전 모듈을 그대로 들고 있을 수 있습니다(ImportError 등). 서버를 다시 시작합니다.

## API 키 처리

- 키는 `core/config.get_setting()`이 `st.secrets` → 환경 변수 → 프로젝트 루트 `.env` 순서로 찾습니다. 로컬에서는 `.env`, Community Cloud에서는 앱 Secrets를 씁니다.
- `.env`의 값을 읽어서 출력하지 않습니다. 확인이 필요할 때는 길이나 접두사(`sk-or-v1-`)만 봅니다. 새 비밀 값을 추가하면 `.env.example`과 `.streamlit/secrets.toml.example`에 자리표시자를 넣습니다.
- `.gitignore`가 `.env`, `.env.*`, `.streamlit/secrets.toml`을 제외합니다. `.git/hooks/pre-commit` 훅은 `.env` 파일이나 `sk-or-v1-` 형식의 키가 스테이징되면 커밋을 막습니다. 이 훅은 git이 추적하지 않으므로, 저장소를 새로 clone하면 다시 설치해야 합니다.
