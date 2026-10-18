import json

import httpx
import pytest

from core.errors import AppError
from core.openrouter import OpenRouterClient

OK_BODY = {"model": "m", "choices": [{"message": {"content": "{}"}}]}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def make_client(responses, clock=None):
    """responses: 차례로 돌려줄 httpx.Response 또는 예외."""
    calls = []
    queue = list(responses)

    def handler(request: httpx.Request):
        calls.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    clock = clock or FakeClock()
    client = OpenRouterClient("test-key", transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock)
    return client, calls, clock


def requested_models(calls):
    return [json.loads(c.content)["model"] for c in calls]


# --- chat: 같은 모델 재시도 ------------------------------------------------------

def test_log_records_success_and_retry():
    log = []
    client, _, _ = make_client([httpx.Response(429, json={}), httpx.Response(200, json=OK_BODY)])
    client.chat({"model": "m"}, deadline_seconds=90, log=log)
    assert [a["outcome"] for a in log] == [429, 200]


def test_success_sends_auth_header():
    client, calls, _ = make_client([httpx.Response(200, json=OK_BODY)])
    assert client.chat({"model": "m"}, deadline_seconds=90) == OK_BODY
    assert calls[0].headers["Authorization"] == "Bearer test-key"


def test_retries_429_once_then_succeeds():
    retries = []
    client, calls, clock = make_client([httpx.Response(429, json={}), httpx.Response(200, json=OK_BODY)])
    client.chat({"model": "m"}, deadline_seconds=90, on_retry=lambda a, w: retries.append((a, w)))
    assert len(calls) == 2
    assert retries == [(1, 10)]
    assert clock.now == 10


def test_persistent_429_gives_model_busy_after_one_retry():
    client, calls, _ = make_client([httpx.Response(429, json={})] * 2)
    with pytest.raises(AppError) as exc:
        client.chat({"model": "m"}, deadline_seconds=90)
    assert exc.value.code == "MODEL_BUSY"
    assert len(calls) == 2


def test_skips_retry_when_deadline_would_pass():
    client, calls, clock = make_client([httpx.Response(429, json={})])
    with pytest.raises(AppError) as exc:
        client.chat({"model": "m"}, deadline_seconds=5)
    assert exc.value.code == "MODEL_BUSY"
    assert len(calls) == 1 and clock.now == 0


def test_error_object_in_200_body_is_treated_as_status():
    client, calls, _ = make_client(
        [httpx.Response(200, json={"error": {"code": 429, "message": "rate limited"}}), httpx.Response(200, json=OK_BODY)]
    )
    assert client.chat({"model": "m"}, deadline_seconds=90) == OK_BODY
    assert len(calls) == 2


def test_timeout_gives_model_timeout():
    client, _, _ = make_client([httpx.ReadTimeout("slow")])
    with pytest.raises(AppError) as exc:
        client.chat({"model": "m"}, deadline_seconds=90)
    assert exc.value.code == "MODEL_TIMEOUT"


@pytest.mark.parametrize(
    "status,code", [(401, "CONFIG_ERROR"), (403, "UPSTREAM_ERROR"), (500, "UPSTREAM_ERROR"), (400, "UPSTREAM_ERROR")]
)
def test_non_retryable_errors_fail_immediately(status, code):
    client, calls, _ = make_client([httpx.Response(status, json={"error": {"message": "secret detail"}})])
    with pytest.raises(AppError) as exc:
        client.chat({"model": "m"}, deadline_seconds=90)
    assert exc.value.code == code
    assert "secret detail" not in exc.value.message  # 원문을 사용자에게 노출하지 않음
    assert len(calls) == 1


def test_connection_error_gives_upstream_error():
    client, _, _ = make_client([httpx.ConnectError("down")])
    with pytest.raises(AppError) as exc:
        client.chat({"model": "m"}, deadline_seconds=90)
    assert exc.value.code == "UPSTREAM_ERROR"


# --- chat_with_fallback: 예비 모델 전환 -------------------------------------------

def build(model):
    return {"model": model}


def test_falls_back_after_one_retry_on_429():
    switched = []
    client, calls, _ = make_client(
        [httpx.Response(429, json={}), httpx.Response(429, json={}), httpx.Response(200, json=OK_BODY)]
    )
    model, body = client.chat_with_fallback(
        build, ["primary", "fb1", "fb2"], deadline_seconds=120, on_fallback=switched.append
    )
    assert (model, body) == ("fb1", OK_BODY)
    assert requested_models(calls) == ["primary", "primary", "fb1"]
    assert switched == ["fb1"]


def test_fallback_requests_use_shorter_timeout():
    client, calls, _ = make_client([httpx.Response(429, json={})] * 2 + [httpx.Response(200, json=OK_BODY)])
    client.chat_with_fallback(
        build, ["primary", "fb1"], deadline_seconds=120, attempt_timeout=60, fallback_attempt_timeout=30
    )
    read_timeouts = [c.extensions["timeout"]["read"] for c in calls]
    assert read_timeouts == [60, 60, 30]


def keepalive_response(clock, seconds_per_chunk, chunks, final=OK_BODY):
    """OpenRouter처럼 처리 중에 공백을 조금씩 보내다가 마지막에 본문을 보내는 응답."""

    def body():
        for _ in range(chunks):
            clock.now += seconds_per_chunk
            yield b" "
        yield json.dumps(final).encode()

    return httpx.Response(200, content=body())


def test_keepalive_whitespace_is_ignored_when_fast_enough():
    clock = FakeClock()
    client, _, _ = make_client([keepalive_response(clock, 5, 3)], clock=clock)
    assert client.chat({"model": "m"}, deadline_seconds=120, attempt_timeout=30) == OK_BODY


def test_slow_keepalive_stream_is_cut_at_attempt_timeout():
    # 공백이 10초마다 와서 httpx 읽기 제한에는 걸리지 않지만, 전체로는 30초를 넘는다
    clock = FakeClock()
    client, _, _ = make_client([keepalive_response(clock, 10, 10)], clock=clock)
    with pytest.raises(AppError) as exc:
        client.chat({"model": "m"}, deadline_seconds=120, attempt_timeout=30)
    assert exc.value.code == "MODEL_TIMEOUT"
    assert clock.now <= 40


def test_slow_fallback_is_skipped_for_the_next_one():
    clock = FakeClock()
    responses = [httpx.Response(429, json={})] * 2 + [keepalive_response(clock, 10, 10), httpx.Response(200, json=OK_BODY)]
    client, calls, _ = make_client(responses, clock=clock)
    model, _ = client.chat_with_fallback(
        build, ["primary", "slow", "fast"], deadline_seconds=120, attempt_timeout=60, fallback_attempt_timeout=30
    )
    assert model == "fast"


def test_each_fallback_is_tried_once_and_any_error_moves_on():
    client, calls, clock = make_client(
        [
            httpx.Response(429, json={}),
            httpx.Response(429, json={}),
            httpx.Response(429, json={}),  # fb1: 재시도 없이 다음으로
            httpx.Response(403, json={}),  # fb2: 403도 다음으로
            httpx.Response(200, json=OK_BODY),
        ]
    )
    model, _ = client.chat_with_fallback(build, ["primary", "fb1", "fb2", "fb3"], deadline_seconds=120)
    assert model == "fb3"
    assert requested_models(calls) == ["primary", "primary", "fb1", "fb2", "fb3"]
    assert clock.now == 10  # 기다린 것은 기본 모델 재시도 한 번뿐


def test_all_models_failing_is_reported_as_such_with_each_attempt():
    log = []
    client, calls, _ = make_client(
        [httpx.Response(429, json={}), httpx.Response(429, json={}), httpx.Response(502, json={}), httpx.ReadTimeout("x")]
    )
    with pytest.raises(AppError) as exc:
        client.chat_with_fallback(build, ["primary", "fb1", "fb2"], deadline_seconds=120, log=log)
    assert exc.value.code == "ALL_MODELS_FAILED"  # 마지막 시도(시간 초과)만 보고 원인을 단정하지 않음
    assert [(a["model"], a["outcome"]) for a in log] == [
        ("primary", 429), ("primary", 429), ("fb1", 502), ("fb2", "timeout"),
    ]
    assert all("seconds" in a and "limit" in a for a in log)


def test_primary_success_does_not_touch_fallbacks():
    client, calls, _ = make_client([httpx.Response(200, json=OK_BODY)])
    assert client.chat_with_fallback(build, ["primary", "fb1"], deadline_seconds=120)[0] == "primary"
    assert len(calls) == 1


def test_invalid_api_key_does_not_fall_back():
    client, calls, _ = make_client([httpx.Response(401, json={})])
    with pytest.raises(AppError) as exc:
        client.chat_with_fallback(build, ["primary", "fb1"], deadline_seconds=120)
    assert exc.value.code == "CONFIG_ERROR"
    assert len(calls) == 1


def test_no_fallbacks_raises_primary_error():
    client, _, _ = make_client([httpx.Response(429, json={})] * 2)
    with pytest.raises(AppError) as exc:
        client.chat_with_fallback(build, ["primary"], deadline_seconds=120)
    assert exc.value.code == "MODEL_BUSY"


def test_free_vision_models_filters_free_image_models():
    body = {
        "data": [
            {"id": "a/vision:free", "architecture": {"input_modalities": ["text", "image"]}, "supported_parameters": ["response_format"]},
            {"id": "b/text:free", "architecture": {"input_modalities": ["text"]}},
            {"id": "c/vision-paid", "architecture": {"input_modalities": ["image"]}},
        ]
    }
    client, _, _ = make_client([httpx.Response(200, json=body)])
    assert client.free_vision_models() == {"a/vision:free": {"response_format"}}
