"""Worker error taxonomy.

Dispatcher `HandlerFn(...).handle(...)`'i dispatch eder; başarı sınıflandırmasını
bu tiplere yaslıyoruz. Yeni error sınıfı yazmak istenirse:

- `TransientError`: geçici (network, 5xx, timeout). Yeniden dene.
- `PermanentError`: mantıksal (validation, 4xx, missing entity). Retry etme.

`max_attempts` aşımında transient error bile dead_letter'a düşer.
"""

from __future__ import annotations


class WorkerError(Exception):
    """Worker'ın kabul ettiği base error.

    Alt sınıflar catastrophic olmayan hata senaryolarını dispatch'e bildirir.
    Tanımsız exception'lar için dispatcher varsayılan olarak PermanentError
    davranır (unknown fail-once-in-a-row korunur).
    """

    code: str = "WORKER_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TransientError(WorkerError):
    """Yeniden denenmeli hata — provider outage, SMTP timeout, network."""

    code = "TRANSIENT_ERROR"


class PermanentError(WorkerError):
    """Retry anlamsız — 4xx yanıt, eksik kayıt, kod-level bug."""

    code = "PERMANENT_ERROR"


class RetryHeld(TransientError):
    """LiteLLM-down gibi durumlar için `hold_minutes` ile beklemeli retry.

    Dispatcher bu error için job'ı `hold_minutes` (default 5) sonrasına
    planlar; `attempts` sayacı tabii ki artar ama backoff sabit ve uzundur.
    """

    code = "LITELLM_HOLD"


__all__ = [
    "PermanentError",
    "RetryHeld",
    "TransientError",
    "WorkerError",
]
