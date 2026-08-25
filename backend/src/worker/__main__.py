"""Worker entry — `python -m backend.src.worker`.

Akış:
1. `.env`'den DB + worker konfigürasyonu oku.
2. `adb_init(...)` → engine + session factory + DDL apply.
3. `WorkerRunner(session_factory, config).run_forever()` çağrısı.
4. SIGINT/SIGTERM'de temiz kapanış; engine dispose.

Console-script karşılığı için `pyproject.toml` sonrasında
`genai-orion-panel-worker = "backend.src.worker.__main__:main"` satırı
eklenecek; bu turda `__main__` içinden manual pre-flight yapıyoruz.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from ..data.db import db_init
from ..observability.logging_config import configure_json_logging
from .config import WorkerConfig
from .dependencies_factory import build_worker_dependencies
from .runner import WorkerRunner

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    # JSON line format; korelasyon kimliği ayrıca context'e set edilebilir.
    configure_json_logging(level=logging.INFO)


def main() -> int:
    """Process entry point — return code exit status int olarak."""
    _configure_logging()
    config = WorkerConfig.from_env()

    built = asyncio.run(db_init.adb_init())
    try:
        deps = build_worker_dependencies(
            session_factory=built.session_factory, config=config,
        )
        runner = WorkerRunner(built.session_factory, config, deps=deps)
        runner.run_forever()
    finally:
        asyncio.run(built.aclose())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
