# 냉장고 레시피 추천 (학습용)

냉장고 사진에서 식재료를 인식하고, 그 재료로 만들 수 있는 레시피를 추천하는 웹 애플리케이션을 만드는 프로젝트입니다. [OpenRouter](https://openrouter.ai)의 무료 모델을 사용합니다.

| 용도 | 모델 |
|---|---|
| 이미지 인식 (식재료) | `google/gemma-4-26b-a4b-it:free` |
| 텍스트 생성 (레시피) | `nvidia/nemotron-3-super-120b-a12b:free` |

## 기술 스택

| 구분 | 사용 기술 (모두 무료) |
|---|---|
| 앱 | [Streamlit](https://streamlit.io) |
| 배포 | [Streamlit Community Cloud](https://share.streamlit.io) |
| 로그인 (3단계) | Streamlit 내장 로그인 `st.login` + Google 계정 |
| DB (3단계) | [Neon](https://neon.com) Postgres 무료 요금제 |

## 진행 상황

| 단계 | 문서 | 상태 |
|---|---|---|
| 1. 냉장고 사진 식재료 인식 | [docs/PRD_step1.md](docs/PRD_step1.md) | 구현 완료 (배포 전) |
| 2. 레시피 생성 | [docs/PRD_step2.md](docs/PRD_step2.md) | 구현 완료 (배포 전) |
| 3. 사용자 프로필과 레시피 저장 | [docs/PRD_step3.md](docs/PRD_step3.md) | 기획 완료 |

## 폴더 구조

```
streamlit_app.py      앱 진입점 (페이지 등록)
app_pages/            화면 (fridge.py: 1단계 식재료 인식, recipes.py: 2단계 레시피 추천)
core/                 화면과 분리된 로직 (OpenRouter 클라이언트, 이미지 인식, 레시피 생성, 재료 사전, 요청 제한)
tests/                pytest 테스트 (실제 모델은 부르지 않음)
docs/                 기획 문서 (PRD)
scripts/              OpenRouter API 동작 확인 스크립트
.streamlit/           Streamlit 설정, secrets.toml 예시
```

## 로컬에서 실행

1. [OpenRouter](https://openrouter.ai/keys)에서 API 키를 발급받습니다.
2. `.env.example`을 `.env`로 복사하고 `OPENROUTER_API_KEY`에 키를 넣습니다. `.streamlit/secrets.toml.example`을 `.streamlit/secrets.toml`로 복사해서 써도 됩니다. 둘 다 git에 올라가지 않습니다.
3. 가상환경을 만들고 패키지를 설치합니다.
   ```bash
   python -m venv .venv
   ```
   ```bash
   .venv/Scripts/python -m pip install -r requirements-dev.txt
   ```
   macOS·Linux에서는 `.venv/Scripts/` 대신 `.venv/bin/`을 씁니다.
4. 앱을 실행하고 http://localhost:8501 을 엽니다.
   ```bash
   .venv/Scripts/streamlit run streamlit_app.py
   ```

## 테스트

```bash
.venv/Scripts/python -m pytest
```

테스트는 모델 호출을 가짜로 바꿔서 실행하므로 무료 사용량을 쓰지 않습니다.

실제 API로 1·2단계를 점검하려면 아래를 실행합니다(Windows, 무료 한도 약 2~7회 사용). 정답을 아는 테스트 사진으로 인식률을 재고, 레시피가 알레르기·한식·30분·추가 구매 조건을 지키는지 항목별로 보고합니다.

```bash
.venv/Scripts/python scripts/live_check.py
```

## Streamlit Community Cloud 배포

1. https://share.streamlit.io 에 GitHub 계정으로 로그인하고 "Create app"을 누릅니다.
2. 저장소 `logistex/recipe4fridge-demo`, 브랜치 `main`, 진입점 `streamlit_app.py`를 고릅니다.
3. "Advanced settings"에서 Python 버전을 로컬과 맞추고, Secrets에 `OPENROUTER_API_KEY = "..."`를 넣습니다.

## 무료 사용량 주의

OpenRouter 무료 모델은 계정 전체에 분당 20회, 하루 50회 제한이 있습니다(크레딧 구매 이력이 10 미만일 때). 기본 모델(Gemma)은 여러 사용자가 한도를 함께 써서 HTTP 429가 자주 납니다. 그러면 앱이 10초 뒤 한 번 더 시도하고, 그래도 안 되면 예비 무료 비전 모델로 자동으로 넘어갑니다. 예비 모델은 하나당 30초까지만 기다리고 다음 모델로 넘어갑니다(`FALLBACK_VISION_MODELS`로 변경 가능, 목록과 선정 이유는 [PRD 1단계 7장](docs/PRD_step1.md)).

예비 모델은 재료명을 깨뜨리거나 분류를 틀리기도 해서, 이름에 한글이 아닌 문자가 섞이면 "⚠ 이름 확인"으로 표시하고, 흔한 재료는 사전으로 분류를 바로잡습니다.

앱은 공개 배포를 고려해 세션당 분당 3회, 앱 전체 하루 40회로 인식 요청을 제한합니다(`DAILY_REQUEST_LIMIT`로 변경 가능).

올린 사진은 모델에 보내기 전에 긴 변 1024px, 300KB 이하 JPEG로 자동 변환되며, 위치 정보 등 EXIF는 지워집니다.
