# 냉장고 레시피 추천 (학습용)

냉장고 사진에서 식재료를 인식하고, 그 재료로 만들 수 있는 레시피를 추천하는 웹 애플리케이션을 만드는 프로젝트입니다. [OpenRouter](https://openrouter.ai)의 무료 모델을 사용합니다.

| 용도 | 모델 |
|---|---|
| 이미지 인식 (식재료) | `google/gemma-4-26b-a4b-it:free` |
| 텍스트 생성 (레시피) | `nvidia/nemotron-3-super-120b-a12b:free` |

## 진행 상황

현재는 기획 문서와 API 동작 테스트 스크립트까지 완료했습니다. 웹 애플리케이션은 아직 구현하지 않았습니다.

| 단계 | 문서 | 상태 |
|---|---|---|
| 1. 냉장고 사진 식재료 인식 | [docs/PRD_step1.md](docs/PRD_step1.md) | 기획 완료 |
| 2. 레시피 생성 | [docs/PRD_step2.md](docs/PRD_step2.md) | 기획 완료 |
| 3. 사용자 프로필과 레시피 저장 | [docs/PRD_step3.md](docs/PRD_step3.md) | 기획 완료 |

## 폴더 구조

```
docs/       기획 문서 (PRD)
scripts/    OpenRouter API 동작 테스트 스크립트
.env.example  환경 변수 예시
```

## API 테스트 실행

1. [OpenRouter](https://openrouter.ai/keys)에서 API 키를 발급받습니다.
2. `.env.example`을 `.env`로 복사하고 `OPENROUTER_API_KEY`에 키를 넣습니다. `.env`는 git에 올라가지 않습니다.
3. Pillow를 설치합니다(테스트 이미지 생성용). 나머지는 Python 표준 라이브러리만 씁니다.
   ```bash
   pip install pillow
   ```
4. 프로젝트 루트에서 실행합니다.
   ```bash
   python scripts/test_openrouter.py          # 텍스트·이미지 둘 다
   python scripts/test_openrouter.py text     # 텍스트만
   python scripts/test_openrouter.py image    # 이미지만
   ```

무료 모델은 요청이 몰리면 HTTP 429(요청 한도 초과)를 돌려줍니다. 스크립트가 자동으로 재시도하지만, 그래도 실패하면 잠시 뒤 다시 실행하세요.
