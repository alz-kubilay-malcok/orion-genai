"""Worker runtime konfigürasyonu — `.env`'den dataclass.

Gereksiz abstraction yok; env okuma + minimal validate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        msg = f"{name} tam sayı olmalı (gelen: {raw!r})"
        raise ValueError(msg) from exc


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    """WorkerRunner'ın ihtiyaç duyduğu tüm env-bazlı ayarlar."""

    poll_interval_seconds: int
    max_attempts: int
    hold_minutes: int
    lease_seconds: int
    mail_max_attempts: int
    mail_backoff_seconds: int
    batch_size: int

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        return cls(
            poll_interval_seconds=max(1, _env_int("WORKER_INTERNAL_SECONDS", 30)),
            max_attempts=max(1, _env_int("LITELLM_RETRY", 10)),
            hold_minutes=max(1, _env_int("LITELLM_HOLD_MINUTES", 5)),
            lease_seconds=max(10, _env_int("WORKER_LEASE_SECONDS", 120)),
            mail_max_attempts=max(1, _env_int("MAIL_RETRY_MAX", 5)),
            mail_backoff_seconds=max(5, _env_int("MAIL_RETRY_BACKOFF_SECONDS", 60)),
            batch_size=max(1, _env_int("WORKER_BATCH_SIZE", 8)),
        )


__all__ = ["WorkerConfig"]
