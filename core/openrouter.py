"""OpenRouter chat completions 클라이언트 (재시도, 예비 모델 전환, 전체 제한 시간, 오류 변환)."""

import json
import logging
import time
from collections.abc import Callable, Sequence

import httpx

from core import config
from core.errors import AppError

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
RETRYABLE_STATUS = {429, 502, 503}
# 기본 모델이 이 오류로 끝나면 예비 모델로 넘어간다 (API 키 문제 같은 CONFIG_ERROR는 넘어가도 소용없다)
FALLBACK_ON = {"MODEL_BUSY", "UPSTREAM_ERROR", "MODEL_TIMEOUT"}

logger = logging.getLogger(__name__)

RetryCallback = Callable[[int, int], None]
FallbackCallback = Callable[[str], None]


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        retry_delays: tuple[int, ...] = config.RETRY_DELAYS,
        request_timeout: float = config.REQUEST_TIMEOUT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._http = httpx.Client(
            transport=transport,
            timeout=request_timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Title": "recipe4fridge-demo",
            },
        )
        self._retry_delays = retry_delays
        self._request_timeout = request_timeout
        self._sleep = sleep
        self._clock = clock

    def chat(
        self,
        payload: dict,
        *,
        deadline_seconds: float,
        on_retry: RetryCallback | None = None,
        retry_delays: tuple[int, ...] | None = None,
        attempt_timeout: float | None = None,
        log: list | None = None,
    ) -> dict:
        """요청을 보내고 응답 JSON을 돌려준다. 일시적 오류면 retry_delays만큼 기다렸다 다시 보낸다.

        log를 주면 요청마다 {"model", "outcome", "seconds", "limit"}를 덧붙인다(화면에 시도 내역을 보여 주기 위함).
        outcome은 HTTP 상태 코드(200, 429 …)이거나 "timeout", "network"다.
        """
        delays = self._retry_delays if retry_delays is None else retry_delays
        per_attempt = min(self._request_timeout, attempt_timeout or self._request_timeout)
        start = self._clock()
        last_status = None
        for attempt in range(len(delays) + 1):
            remaining = deadline_seconds - (self._clock() - start)
            if remaining <= 0:
                break
            status, data = self._logged_post(payload, min(remaining, per_attempt), log)
            logger.info("OpenRouter model=%s status=%s attempt=%d", payload.get("model"), status, attempt + 1)
            if status == 200:
                return data
            last_status = status

            if status not in RETRYABLE_STATUS or attempt == len(delays):
                break
            wait = delays[attempt]
            if (self._clock() - start) + wait >= deadline_seconds:
                break
            if on_retry:
                on_retry(attempt + 1, wait)
            self._sleep(wait)

        if last_status is None:
            raise AppError("MODEL_TIMEOUT")
        if last_status == 429:
            raise AppError("MODEL_BUSY")
        if last_status == 401:
            raise AppError("CONFIG_ERROR")
        raise AppError("UPSTREAM_ERROR")

    def _logged_post(self, payload: dict, limit: float, log: list | None) -> tuple[int, dict]:
        start = self._clock()
        entry = {"model": payload.get("model"), "limit": round(limit)}
        try:
            status, data = self._post(payload, limit=limit)
            entry["outcome"] = status
            return status, data
        except AppError as e:
            entry["outcome"] = "timeout" if e.code == "MODEL_TIMEOUT" else "network"
            raise
        finally:
            entry["seconds"] = round(self._clock() - start, 1)
            if log is not None:
                log.append(entry)

    def _post(self, payload: dict, *, limit: float) -> tuple[int, dict]:
        """요청 하나를 limit초 안에 끝낸다.

        OpenRouter는 처리하는 동안 연결 유지용 공백을 조금씩 보내므로, httpx의 읽기 제한 시간은
        계속 다시 시작되어 전체 시간을 막지 못한다. 그래서 응답을 조각으로 받으면서 경과 시간을 직접 잰다.
        """
        start = self._clock()
        body = bytearray()
        try:
            with self._http.stream("POST", API_URL, json=payload, timeout=limit) as resp:
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if self._clock() - start > limit:
                        logger.warning("OpenRouter 응답 시간 초과: model=%s %.0f초", payload.get("model"), limit)
                        raise AppError("MODEL_TIMEOUT")
                status_code = resp.status_code
        except httpx.TimeoutException:
            raise AppError("MODEL_TIMEOUT") from None
        except httpx.HTTPError as e:
            logger.warning("OpenRouter 연결 실패: %s", type(e).__name__)
            raise AppError("UPSTREAM_ERROR") from None
        return _status_and_body(status_code, bytes(body))

    def chat_with_fallback(
        self,
        build_payload: Callable[[str], dict],
        models: Sequence[str],
        *,
        deadline_seconds: float,
        attempt_timeout: float | None = None,
        fallback_attempt_timeout: float | None = None,
        on_retry: RetryCallback | None = None,
        on_fallback: FallbackCallback | None = None,
        log: list | None = None,
    ) -> tuple[str, dict]:
        """첫 모델은 재시도 정책대로, 예비 모델은 한 번씩만 시도한다. (응답한 모델, 응답)을 돌려준다.

        예비 모델 요청에는 fallback_attempt_timeout(없으면 attempt_timeout)을 적용한다.
        """
        start = self._clock()
        primary, *fallbacks = models
        try:
            return primary, self.chat(
                build_payload(primary),
                deadline_seconds=deadline_seconds,
                on_retry=on_retry,
                attempt_timeout=attempt_timeout,
                log=log,
            )
        except AppError as e:
            if e.code not in FALLBACK_ON or not fallbacks:
                raise
            last_error = e

        for model in fallbacks:
            remaining = deadline_seconds - (self._clock() - start)
            if remaining <= 0:
                break
            logger.info("예비 모델로 전환: %s", model)
            if on_fallback:
                on_fallback(model)
            try:
                return model, self.chat(
                    build_payload(model),
                    deadline_seconds=remaining,
                    retry_delays=(),
                    attempt_timeout=fallback_attempt_timeout or attempt_timeout,
                    log=log,
                )
            except AppError as e:  # 예비 모델은 어떤 이유로 실패하든 다음 모델로 넘어간다
                last_error = e
        # 마지막 시도만 보고 원인을 정하면 틀리기 쉽다(예: 502인데 "요청이 몰렸다"). 모두 실패했다고 그대로 알린다.
        raise AppError("ALL_MODELS_FAILED")

    def free_vision_models(self) -> dict[str, set[str]]:
        """이미지를 받는 무료 모델과 각 모델이 지원하는 파라미터. 모델 목록은 키 없이 공개된 API다."""
        resp = self._http.get(MODELS_URL, timeout=30)
        resp.raise_for_status()
        models = {}
        for m in resp.json().get("data", []):
            modalities = (m.get("architecture") or {}).get("input_modalities") or []
            if m.get("id", "").endswith(":free") and "image" in modalities:
                models[m["id"]] = set(m.get("supported_parameters") or [])
        return models


def _status_and_body(status: int, body: bytes) -> tuple[int, dict]:
    """OpenRouter는 HTTP 200 본문에 error 객체를 담아 보내기도 하므로, 그 코드를 상태로 쓴다."""
    try:
        data = json.loads(body)  # 앞쪽의 연결 유지용 공백은 json이 알아서 건너뛴다
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    error = data.get("error")
    if status == 200 and isinstance(error, dict):
        code = error.get("code")
        status = code if isinstance(code, int) else 502
    elif status == 200 and not data.get("choices"):
        status = 502
    return status, data
