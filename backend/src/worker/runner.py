"""Worker runner — `OutboxDispatcher` için sonsuz polling loop + heartbeat.

Davranış:
- `tick()` her `poll_interval_seconds`'te bir çağrılır.
- Boş tick'lerde DB'ye yük binmemesi için `lock - poll` simple pattern.
- SIGINT/SIGTERM stop event'ini set eder; son tick'ten sonra temiz çıkış.
- `worker_heartbeats` tablosu `started_at`/`last_seen_at` ile beslenir —
  `/health/live` ve dashboard'a tek kaynak.

Çoklu instance: Her worker farklı `worker_id` ile çalışır; outbox
`claim_next_due` UPDATE WHERE-clauses'i sayesinde yarışı DB'ye bırakır.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import threading
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import WorkerConfig
from .dependencies import WorkerDependencies
from .dispatcher import OutboxDispatcher

logger = logging.getLogger(__name__)


class WorkerRunner:
    """Worker process'inin ana orchestrator'ı.

    Engine session_factory'sini dışarıdan alır (db_init ile kurulur);
    bu sayede test fixture'ı aynı shape'i sağlayabilir.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        config: WorkerConfig,
        *,
        dispatcher: OutboxDispatcher | None = None,
        deps: WorkerDependencies | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._config = config
        # `deps` injection: handler tablosunu dispatcher kurarken bağla.
        # Heartbeat callback'i de deps'ten kopyala; yoksa dispatcher'dan
        # gelseydi burada copy'lemeye gerek yok — `_safe_tick` deps'i
        # kullanır.
        self._heartbeat_callback = deps.heartbeat_callback if deps is not None else None

        if dispatcher is not None:
            self._dispatcher = dispatcher
        elif deps is not None:
            self._dispatcher = OutboxDispatcher(session_factory, config, deps=deps)
        else:
            self._dispatcher = OutboxDispatcher(session_factory, config)
        self._stop = threading.Event()
        self._started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self._last_dispatch = 0
        self._processed_total = 0

    @property
    def dispatcher(self) -> OutboxDispatcher:
        return self._dispatcher

    @property
    def is_running(self) -> bool:
        return not self._stop.is_set()

    def request_stop(self) -> None:
        """Cooperative stop — loop'tan çık.

        Her tick arasında kontrol edilir; in-flight dispatch bloke olmaz.
        """
        if not self._stop.is_set():
            logger.info("worker stop isteniyor", extra={"worker_id": self._dispatcher.worker_id})
        self._stop.set()
        self._dispatcher.request_stop()

    def install_signal_handlers(self) -> None:
        """SIGINT/SIGTERM → `request_stop`.

        Windows'ta SIGTERM yok; orada kullanıcının Ctrl+C ile SIGINT
        atması beklenir.
        """
        loop_factory = signal.getsignal(signal.SIGINT)
        already_installed = getattr(self, "_signals_installed", False)
        if already_installed:
            return
        self._signals_installed = True  # type: ignore[attr-defined]
        try:
            signal.signal(signal.SIGINT, lambda *_: self.request_stop())
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, lambda *_: self.request_stop())
        except ValueError:
            # Ana thread dışında çağrılırsa (test fixture) skip.
            pass

    def run_forever(self) -> None:
        """Blocking orchestration — Ctrl+C veya `request_stop`'a kadar poll."""
        self.install_signal_handlers()
        logger.info(
            "worker başladı",
            extra={
                "worker_id": self._dispatcher.worker_id,
                "poll_interval_seconds": self._config.poll_interval_seconds,
                "hold_minutes": self._config.hold_minutes,
                "max_attempts": self._config.max_attempts,
            },
        )
        try:
            while self.is_running:
                self._safe_tick()
                self._sleep_or_stop()
        finally:
            logger.info(
                "worker durdu",
                extra={
                    "worker_id": self._dispatcher.worker_id,
                    "processed_total": self._processed_total,
                },
            )

    def _safe_tick(self) -> None:
        try:
            self._last_dispatch = self._dispatcher.tick()
            self._processed_total += self._last_dispatch
        except Exception as exc:  # noqa: BLE001 — fail-safe
            logger.error(
                "worker tick patladı",
                extra={
                    "worker_id": self._dispatcher.worker_id,
                    "error": repr(exc),
                },
                exc_info=True,
            )
        # Heartbeat her tick'te yazılır; DB write başarısız olursa tick'i
        # düşürmeyiz (`_safe_tick` zaten fail-safe), sadece log uyarırız.
        # `_safe_tick` sync scope'ta; dispatcher's `asyncio.run` çağrısı
        # burada tamamlanmış, yeni event loop açmamız güvenli.
        if self._heartbeat_callback is not None:
            self._heartbeat_callback(
                worker_id=self._dispatcher.worker_id,
                started_at=self._started_at,
                last_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )

    def _sleep_or_stop(self) -> None:
        """`poll_interval_seconds` kadar uyur; stop anında erken döner.

        `Event.wait` cancelable; iş parçacığı üzerinde çalışır, asyncio
        ile çakışmaz.
        """
        self._stop.wait(timeout=self._config.poll_interval_seconds)


__all__ = ["WorkerRunner"]
