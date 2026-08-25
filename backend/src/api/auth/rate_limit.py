"""Per (IP, username) basit login rate limiter.

In-memory kova; çoklu Pod'da paylaşımsızdır (kabul edilen trade-off
§4.5 "every failed attempt costs the DC a bind — unthrottled, both a
DoS on AD and account lockout trigger"). Prod'da dış backend'e
(Redis) taşıma listesi depoda.

Lockout: ``window`` içinde ``max_attempts`` aşılırsa
``lockout_seconds`` boyunca deneme yapılamaz.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from backend.src.observability.settings import get_settings


@dataclass(slots=True)
class _Bucket:
    attempts: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class LoginRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], _Bucket] = {}

    def check(self, ip: str, username: str) -> tuple[bool, int]:
        """Returns ``(allowed, retry_after_seconds)``.

        ``retry_after_seconds`` lockout başladıysa kalan süre, yoksa 0.
        Eski attempt window dışına çıktıysa atılır.
        """
        s = get_settings()
        now = time.monotonic()
        key = (ip.lower(), username.lower())
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket()
            self._buckets[key] = bucket

        if bucket.locked_until > now:
            return False, int(bucket.locked_until - now)

        # window dışı attempt'leri at
        cutoff = now - s.login_rate_limit_window_seconds
        bucket.attempts = [t for t in bucket.attempts if t >= cutoff]

        if len(bucket.attempts) >= s.login_rate_limit_max_attempts:
            bucket.locked_until = now + s.login_rate_limit_lockout_seconds
            bucket.attempts.clear()
            return False, s.login_rate_limit_lockout_seconds

        return True, 0

    def record_failure(self, ip: str, username: str) -> None:
        key = (ip.lower(), username.lower())
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket()
            self._buckets[key] = bucket
        bucket.attempts.append(time.monotonic())

    def record_success(self, ip: str, username: str) -> None:
        self._buckets.pop((ip.lower(), username.lower()), None)

    def reset_all(self) -> None:
        """Test fixture'ı için."""
        self._buckets.clear()


# Process-tek instance; AppState'e mount edilir.
_limiter = LoginRateLimiter()


def get_rate_limiter() -> LoginRateLimiter:
    return _limiter


__all__ = ["LoginRateLimiter", "get_rate_limiter"]
