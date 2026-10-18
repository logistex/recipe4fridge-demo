# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

냉장고 사진에서 식재료를 인식하고 레시피를 추천하는 웹 애플리케이션을 만들기 위한 학습용 프로젝트입니다. OpenRouter의 무료 모델을 씁니다. 지금은 기획 문서(PRD)와 API 동작 테스트 스크립트만 있고, 웹 앱은 아직 구현하지 않았습니다.

- `docs/`: 문서. `PRD_step1.md`(식재료 인식), `PRD_step2.md`(레시피 생성), `PRD_step3.md`(프로필과 레시피 저장). 구현은 이 순서를 따르며, 각 PRD에 API 명세, 데이터 형식, 수용 기준이 있습니다. 앱 코드의 폴더 구조(`app/`, `static/`)와 기술 스택(FastAPI, SQLite)도 PRD에 정해져 있습니다.
- `scripts/`: 코드. 지금은 `test_openrouter.py` 하나뿐입니다.

빌드 단계, 린터, 테스트 프레임워크는 없습니다. `scripts/test_openrouter.py`를 직접 실행하는 것이 곧 테스트입니다.

## 명령어

프로젝트 루트에서 실행합니다.

```bash
python scripts/test_openrouter.py          # 텍스트·이미지 테스트 둘 다 실행
python scripts/test_openrouter.py text     # 텍스트 인식만
python scripts/test_openrouter.py image    # 이미지 인식만
```

- 테스트가 하나라도 실패하면 종료 코드가 1입니다. 한 테스트가 실패해도 나머지 테스트는 계속 실행됩니다.
- Windows의 Git Bash에서 실행하면 한글 출력이 깨질 수 있습니다. 이때는 `PYTHONIOENCODING=utf-8`을 붙여서 실행합니다.
- 의존성은 Python 표준 라이브러리와 Pillow(테스트 이미지 생성용)뿐입니다. `requests`, `python-dotenv`, `fastapi`는 설치되어 있지 않습니다. requirements 파일도 없습니다.

## 구조

- HTTP 호출은 `urllib.request`로 `https://openrouter.ai/api/v1/chat/completions`에 보냅니다.
- 모델은 파일 상단의 상수로 정해져 있습니다.
  - `TEXT_MODEL = nvidia/nemotron-3-super-120b-a12b:free`: 텍스트 입력만 받습니다.
  - `VISION_MODEL = google/gemma-4-26b-a4b-it:free`: 이미지 입력을 받습니다. 이미지는 base64 data URL로 `image_url` 콘텐츠 파트에 넣어 보냅니다.
- `chat()`은 HTTP 429, 502, 503 응답이 오면 10초, 20초 간격으로 재시도합니다. Gemma 무료 모델은 여러 사용자가 요청 한도를 함께 쓰는 탓에(upstream shared pool) 429가 자주 납니다. 이미지 테스트가 429로 실패하면 몇십 초 기다린 뒤 다시 실행하면 대개 통과합니다. 이것은 코드 문제가 아닙니다.
- `scripts/test_image.png`는 이미지 테스트를 실행할 때마다 `make_test_image()`가 다시 만들며, git이 추적하지 않습니다. 이미지에는 정답이 정해져 있습니다(빨간 원, 파란 사각형, 초록 삼각형, 글자 "HELLO 2026"). 그림을 바꾸면 `test_image()`에서 출력하는 정답 문구도 함께 고칩니다.

## API 키 처리

- 키는 프로젝트 루트 `.env`의 `OPENROUTER_API_KEY`에 있습니다. `load_api_key()`는 `PROJECT_ROOT / ".env"`를 직접 파싱합니다. dotenv 라이브러리는 쓰지 않습니다.
- `.env`의 값을 읽어서 출력하지 않습니다. 확인이 필요할 때는 길이나 접두사(`sk-or-v1-`)만 봅니다. 새 환경 변수를 추가하면 `.env.example`에도 자리표시자를 넣습니다.
- `.gitignore`가 `.env`와 `.env.*`를 제외합니다(`.env.example`은 예외로 커밋됨). 또 `.git/hooks/pre-commit` 훅이 `.env` 파일이 스테이징되거나 `sk-or-v1-` 형식의 키가 포함되면 커밋을 막습니다. 이 훅은 git이 추적하지 않으므로, 저장소를 새로 clone하면 다시 설치해야 합니다.
