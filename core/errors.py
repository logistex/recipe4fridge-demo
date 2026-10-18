"""화면에 보여 줄 수 있는 앱 오류."""

MESSAGES = {
    "INVALID_IMAGE": "이미지 파일을 열 수 없어요. JPEG, PNG, WEBP 사진을 올려 주세요.",
    "IMAGE_TOO_LARGE": "10MB 이하 사진만 올릴 수 있어요.",
    "PARSE_FAILED": "인식 결과를 읽지 못했어요. 다시 시도해 주세요.",
    "MODEL_BUSY": "무료 모델에 요청이 몰려 있어요. 1분쯤 뒤에 다시 시도해 주세요.",
    "RATE_LIMITED": "요청이 너무 잦아요. 1분쯤 뒤에 다시 시도해 주세요.",
    "DAILY_LIMIT": "오늘 준비된 무료 사용량을 모두 썼어요. 내일 다시 이용해 주세요.",
    "MODEL_TIMEOUT": "응답이 너무 늦어요. 잠시 뒤 다시 시도해 주세요.",
    "UPSTREAM_ERROR": "인식 서비스에 문제가 생겼어요. 잠시 뒤 다시 시도해 주세요.",
    "CONFIG_ERROR": "API 키가 설정되지 않았거나 올바르지 않습니다.",
}


class AppError(Exception):
    """사용자에게 보여 줄 한국어 문구와 오류 코드를 함께 담는다."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or MESSAGES.get(code, "알 수 없는 오류가 생겼어요.")
        super().__init__(self.message)
