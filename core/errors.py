"""화면에 보여 줄 수 있는 앱 오류."""

MESSAGES = {
    "INVALID_IMAGE": "이미지 파일을 열 수 없어요. JPEG, PNG, WEBP 사진을 올려 주세요.",
    "IMAGE_TOO_LARGE": "10MB 이하 사진만 올릴 수 있어요.",
    "PARSE_FAILED": "AI 모델의 응답을 읽을 수 없었어요(약속한 형식이 아님). 다시 시도해 주세요.",
    "MODEL_BUSY": "무료 AI 모델이 요청 한도 초과(429)로 요청을 거절했어요. 1분쯤 뒤에 다시 시도해 주세요.",
    "RATE_LIMITED": "이 앱은 1분에 3번까지만 AI에 요청해요. 1분쯤 뒤에 다시 시도해 주세요.",
    "DAILY_LIMIT": "이 앱에 정해 둔 하루 무료 사용량을 모두 썼어요. 내일 다시 이용해 주세요.",
    "MODEL_TIMEOUT": "AI 모델이 제한 시간 안에 응답하지 않았어요. 잠시 뒤 다시 시도해 주세요.",
    "UPSTREAM_ERROR": "AI 서비스(OpenRouter)가 오류를 돌려줬어요. 잠시 뒤 다시 시도해 주세요.",
    "ALL_MODELS_FAILED": "기본 모델과 예비 모델이 모두 결과를 주지 못했어요. 잠시 뒤 다시 시도해 주세요.",
    "CONFIG_ERROR": "API 키가 설정되지 않았거나 올바르지 않습니다.",
}


class AppError(Exception):
    """사용자에게 보여 줄 한국어 문구와 오류 코드를 함께 담는다."""

    def __init__(self, code: str, message: str | None = None, attempts: list | None = None):
        self.code = code
        self.message = message or MESSAGES.get(code, "알 수 없는 오류가 생겼어요.")
        self.attempts = attempts or []  # 실패하기까지 보낸 요청들 (OpenRouterClient 로그 형식)
        super().__init__(self.message)
