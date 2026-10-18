"""무료 모델 한도를 지키기 위한 요청 횟수 제한."""

import threading
import time
from collections.abc import Callable, MutableMapping
from datetime import datetime, timezone


class DailyLimiter:
    """앱 전체(모든 세션)가 함께 쓰는 하루 요청 상한. 앱이 재시작되면 0부터 다시 센다."""

    def __init__(self, limit: int, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.limit = limit
        self._now = now
        self._lock = threading.Lock()
        self._day = None
        self._count = 0

    def _roll(self) -> None:
        today = self._now().date()  # OpenRouter 하루 한도와 맞추려고 UTC 날짜로 센다
        if today != self._day:
            self._day, self._count = today, 0

    def try_acquire(self) -> bool:
        with self._lock:
            self._roll()
            if self._count >= self.limit:
                return False
            self._count += 1
            return True

    def remaining(self) -> int:
        with self._lock:
            self._roll()
            return max(self.limit - self._count, 0)


def check_session_rate(
    state: MutableMapping, per_minute: int, now: Callable[[], float] = time.monotonic
) -> bool:
    """세션별로 최근 60초 동안의 요청 수를 센다. 허용되면 기록하고 True."""
    current = now()
    recent = [t for t in state.get("request_times", []) if current - t < 60]
    if len(recent) >= per_minute:
        state["request_times"] = recent
        return False
    state["request_times"] = recent + [current]
    return True
