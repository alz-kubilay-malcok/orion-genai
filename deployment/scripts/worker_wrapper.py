#!/usr/bin/env python3
"""Backend worker için stdlib-only HTTP liveness/readiness probe.

Mevcut ``WorkerRunner`` / ``OutboxDispatcher`` koduna dokunmadan,
orchestration (docker compose, küba liveness) tarafı için ``/live`` ve
``/ready`` endpoint'leri sunar.

Çalışma modeli
--------------
Supervisor olarak tek süreç, çocuk olarak worker komutu:

    ┌─ worker_wrapper.py (PID 1) ────────────────────────────┐
    │                                                        │
    │  - HTTP probe   : $WORKER_HEALTH_PORT (default 8057)    │
    │  - supervisör   : subprocess PopenWORKER_CHILD_CMD[..]) │
    │                                                        │
    │  SIGTERM/SIGINT → child.terminate() → wait → exit      │
    └────────────────────────────────────────────────────────┘

Endpoint anlamları:

- ``/live``  → supervisör ayakta mı VE child.poll() None mi?
- ``/ready`` → ``/live`` + ``uptime ≥ WORKER_MIN_UPTIME_SECONDS``
              VE opsiyonel olarak ``worker_heartbeats`` tablosundaki
              en son yazılan ``last_seen_at`` yaşı
              ``WORKER_STALE_AFTER_SECONDS``'tan küçük mü?

DB-bağımlı heartbeat check
--------------------------
Varsayılan **kapalı**. Açmak için ``WORKER_HEARTBEAT_CHECK=true``.
Açıldığında her istek yeni bir async session açar; probe sıklığı
``compose healthcheck interval=10s`` gibi makul aralıkta ise PG ek
yükü düşüktür. Çok yüksek frequency'de probe yapılacaksa bu check'i
kapatıp ``min_uptime`` + ``child_alive`` mantığına güvenmek daha sağlıklı.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

_LOG = logging.getLogger("worker_probe")

# ---- Konfigürasyon ---------------------------------------------------------

CHILD_CMD: list[str] = shlex.split(
    os.environ.get("WORKER_CHILD_CMD", "python main.py worker")
)
HEALTH_PORT: int = int(os.environ.get("WORKER_HEALTH_PORT", "8057"))
HEALTH_HOST: str = os.environ.get("WORKER_HEALTH_HOST", "0.0.0.0")
MIN_UPTIME_SECONDS: int = int(os.environ.get("WORKER_MIN_UPTIME_SECONDS", "15"))
STALE_AFTER_SECONDS: int = int(os.environ.get("WORKER_STALE_AFTER_SECONDS", "180"))
DB_HEARTBEAT_CHECK: bool = (
    os.environ.get("WORKER_HEARTBEAT_CHECK", "false").lower() == "true"
)
DB_HEARTBEAT_WORKER_ID: Optional[str] = os.environ.get("WORKER_ID")

_START_MONO: float = time.time()

_child: Optional[subprocess.Popen[Any]] = None
_child_started_at: float = 0.0
_last_child_exit_code: Optional[int] = None


# ---- Heartbeat okuma (best-effort, opsiyonel) ------------------------------


def _latest_heartbeat_age() -> Optional[float]:
    """``worker_heartbeats.last_seen_at`` yaşı (saniye).

    ``None`` dönerse DB sorgusu çalışmadı ya da hiç kayıt yok.
    Probe response payload'ında ``db_check_ran=False`` olarak işaretlenir,
    çağıran yorumlasın.
    """
    try:
        import asyncio

        from sqlalchemy import text

        from backend.src.data.db import adb_init

        async def _read_age() -> Optional[float]:
            built = await adb_init()
            try:
                async with built.session_factory() as session:
                    if DB_HEARTBEAT_WORKER_ID:
                        row = (
                            await session.execute(
                                text(
                                    "SELECT last_seen_at FROM worker_heartbeats "
                                    "WHERE worker_id = :wid"
                                ),
                                {"wid": DB_HEARTBEAT_WORKER_ID},
                            )
                        ).first()
                    else:
                        row = (
                            await session.execute(
                                text(
                                    "SELECT MAX(last_seen_at) AS max_seen "
                                    "FROM worker_heartbeats"
                                )
                            )
                        ).first()
                    if row is None or row[0] is None:
                        return None
                    seen: datetime = row[0]
                    if seen.tzinfo is None:
                        seen = seen.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    return max((now - seen).total_seconds(), 0.0)
            finally:
                await built.aclose()

        return asyncio.run(_read_age())
    except Exception as exc:  # noqa: BLE001 — probe log+continue
        _LOG.warning("heartbeat DB okuma başarısız: %s", exc)
        return None


# ---- HTTP handler ----------------------------------------------------------


def _snapshot() -> dict[str, Any]:
    alive = _child is not None and _child.poll() is None
    uptime = max(time.time() - _START_MONO, 0.0)
    payload: dict[str, Any] = {
        "status": "alive" if alive else "down",
        "worker_pid": _child.pid if _child else None,
        "uptime_seconds": round(uptime, 2),
        "last_child_exit_code": _last_child_exit_code,
    }
    if not alive:
        payload["ready"] = False
        return payload
    payload["uptime_passes_min_threshold"] = uptime >= MIN_UPTIME_SECONDS
    age = _latest_heartbeat_age() if DB_HEARTBEAT_CHECK else None
    payload["db_check_ran"] = age is not None
    if age is not None:
        payload["heartbeat_age_seconds"] = round(age, 2)
        payload["heartbeat_fresh"] = age <= STALE_AFTER_SECONDS
    else:
        payload["heartbeat_fresh"] = True
    payload["ready"] = (
        payload["uptime_passes_min_threshold"] and payload["heartbeat_fresh"]
    )
    return payload


class _Handler(BaseHTTPRequestHandler):
    server_version = "worker-probe/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        _LOG.debug(fmt, *args)

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — http.server contract
        snap = _snapshot()
        path = self.path.split("?", 1)[0]
        if path in ("/live", "/health/live"):
            code = 200 if snap["status"] == "alive" else 503
            self._send_json(code, snap)
            return
        if path in ("/ready", "/health/ready"):
            code = 200 if snap.get("ready") else 503
            self._send_json(code, snap)
            return
        self._send_json(404, {"error": "not_found", "path": path})


# ---- Child supervision -----------------------------------------------------


def _spawn_child() -> None:
    """Worker komutunu başlatır. Zaten çalışıyorsa idempotent no-op."""
    global _child, _child_started_at
    if _child is not None and _child.poll() is None:
        _LOG.warning("child zaten çalışıyor, ikinci kez başlatılmadı")
        return
    _LOG.info("child başlatılıyor: %s", " ".join(CHILD_CMD))
    _child = subprocess.Popen(
        CHILD_CMD,
        cwd=os.getcwd(),
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
    )
    _child_started_at = time.time()


def _terminate_child_gracefully() -> int:
    """SIGTERM/15 gönderir; 20s içinde kapanmazsa SIGKILL."""
    global _last_child_exit_code
    if _child is None:
        return 0
    try:
        if _child.poll() is None:
            _child.terminate()
            try:
                _last_child_exit_code = _child.wait(timeout=20)
                _LOG.info("child temiz kapandı: rc=%s", _last_child_exit_code)
            except subprocess.TimeoutExpired:
                _LOG.warning("child terminate'a yanıt vermedi; kill")
                _child.kill()
                _last_child_exit_code = _child.wait().returncode
        else:
            _last_child_exit_code = _child.returncode
    except ProcessLookupError:
        _last_child_exit_code = None
    return _last_child_exit_code if _last_child_exit_code is not None else 0


def _handle_signal(_signum: int, _frame: Optional[Any]) -> None:
    """SIGINT/SIGTERM → temiz kapat. Bu thread'ten asla dönülmez."""
    _LOG.info("shutdown istendi (signal=%s)", _signum)
    rc = _terminate_child_gracefully()
    sys.exit(rc)


# ---- Entry -----------------------------------------------------------------


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    # ``min_uptime`` sayesinde container restart-loop'larında probe
    # ``ready=true`` döndürmek için min süreyi bekler; orchestrator
    # role tanımlamadan önce sıçrama olmaz.
    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except ValueError:
        _LOG.debug("signal handler kurulamadı (muhtemelen test)")

    httpd = ThreadingHTTPServer((HEALTH_HOST, HEALTH_PORT), _Handler)
    _LOG.info("health probe dinliyor: http=%s:%d cmd=%s", HEALTH_HOST, HEALTH_PORT, " ".join(CHILD_CMD))

    threading.Thread(target=_spawn_child, name="worker-supervisor", daemon=True).start()

    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        return _terminate_child_gracefully()


if __name__ == "__main__":
    raise SystemExit(main())
