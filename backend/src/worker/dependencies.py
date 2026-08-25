"""Worker DI dataclass.

`OutboxDispatcher` ve handler'lar bu nesneyi dolaşır. Legacy
`Backend`'deki `genai_orion_panel_worker.main:WorkerDependencies` ile
bire bir aynı sorumluluk; burada Copy yerine ince shape tutmak için
yalın dataclass yeterli.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class WorkerDependencies:
    """Worker'ın per-process bağımlılıkları.

    Tip-bildirimleri: gerçek port protocol'ları ileride
    `genai_orion_panel_core.application.ports.*` üzerinden zorla bağlanır;
    şu an forward-ref kullanıyoruz, böylece adapter wiring'i
    factory içinde yapılır ve `WorkerDependencies` runtime'da import'a
    bağımlı kalmaz.
    """

    session_factory: Any

    # Provision payload'ındaki LiteLLM/MCP çağrıları için kullanılır —
    # factory tarafından `genai_orion_panel_core.application.ports.litellm`
    # concrete'leriyle doldurulur. Adapter paketi yeni backend'e henüz
    # import edilmemiş; factory None bırakırsa handler sırasında
    # explicit `RuntimeError` raise eder ki "yapacak bir şey yok"
    # yerine fail-fast olsun.
    secret_cipher: Any | None = None
    litellm: Any | None = None
    mcp_provision: Any | None = None
    mcp_catalog_port: Any | None = None  # RequestRepository replacement n/a; cross-adapter

    # Approver mail için: capability token üreten bir helper. None ise
    # worker approver mail routing'ini devre dışı bırakır.
    approval_token_issuer: Callable[..., Any] | None = None

    # Runner callback: worker_heartbeats satırını yazma yardımcısı.
    # Operations: ``heartbeat_callback(worker_id, started_at, last_seen_at)``.
    # None ise runner heartbeat yazma'yı atlar.
    heartbeat_callback: Callable[..., Any] | None = None

    # DLQ notification hook (dead-letter'a düşen job'lar için operatör alert).
    # Signature: ``notify_dead_letter(job_id, job_type, error_code, error_message)``.
    dead_letter_notifier: Callable[..., Any] | None = None


__all__ = ["WorkerDependencies"]
