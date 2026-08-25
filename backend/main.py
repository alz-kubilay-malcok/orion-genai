"""Backend tek-entrypoint orchestrator (.env otomatik yükleme).

Kullanım::

    python main.py migrate            # DDL/flyway + safety create_all
    python main.py api                # FastAPI (uvicorn, ana thread bloklu)
    python main.py worker             # Outbox worker (WorkerRunner.run_forever)
    python main.py debug-routes       # Mount edilmiş rotaları JSON dump et
    python main.py defaults           # Tüm sub-command'ı default sırayla koş
                                      # (önce `migrate`, sonra `worker`)
    python main.py --help

Her sub-command:

* ``migrate``  → ``DBConfig.from_env()`` + ``db_init.adb_init()`` +
                 ``base.metadata.create_all`` (varsayılan açık; sadece
                 schema drift tespitinde yeni kolon ekler).
* ``api``      → :mod:`backend.src.api.main` `create_app()` üzerinden
                 ``uvicorn.run(...)``.
* ``worker``   → :mod:`backend.src.worker.__main__`.``main()`.
* ``debug-routes`` → :func:`backend.src.api.main.create_app` ile rotaları
                     enumerate edip her satıra ``<path>  [<methods>]``
                     basar; DB/DI gerektirmez.

``defaults`` modu (CLI argümansız veya ``defaults`` sub-command):
   migrate + worker (api SLI'dir, ayrı terminalde çalıştırılır).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

# Backend'i PYTHONPATH'e eklemeden kullanıcının doğrudan `python main.py`
# çağırmasını desteklemek için üst dizini (proje root) sys.path'e ekle.
# Böylece `from backend.src...` importları çalışır.
_BACKEND_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_ROOT.parent
for _path in (str(_PROJECT_ROOT), str(_BACKEND_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# .env'i mümkünse yükle (pydantic-settings değil, basit manual parser;
# container/deployment ortamlarında zaten env_file kullanılıyor — bu dosya
# sadece developer convenience).
_ENV_PATH = _BACKEND_ROOT / ".env"
if _ENV_PATH.is_file():
    try:
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError as exc:
        print(f"backend/main.py: .env okunamadı: {exc}", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="GenAiOrionPanel backend orchestrator",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    sub.add_parser(
        "migrate",
        help="DDL/flyway + safety create_all (DB bağlantısı gerekir)",
    )
    sub.add_parser(
        "api",
        help="FastAPI (uvicorn) – DB gerekir, ana thread bloklanır",
    )
    sub.add_parser(
        "worker",
        help="Outbox worker (WorkerRunner.run_forever) – DB gerekir",
    )
    sub.add_parser(
        "debug-routes",
        help="Mount edilmiş rotaları sanal ortamda dump et (DB bağımsız)",
    )
    sub.add_parser(
        "defaults",
        help="Default mod: migrate + worker (compose için uygun)",
    )
    return parser


def _configure_logging() -> None:
    """Log konfig; idempotent, mevcut handler'lara dokunmaz."""
    from backend.src.observability.logging_config import configure_json_logging
    try:
        configure_json_logging(level=logging.INFO)
    except Exception as exc:  # noqa: BLE001 — log setup fail etmemeli
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).warning(
            "configure_json_logging başarısız (%s); basicConfig fallback",
            exc,
        )


def cmd_migrate(args: argparse.Namespace) -> int:
    _configure_logging()
    # Lazy import; uygulama başka modlara bağlanmasın.
    from backend.src.data.db import adb_init, DBConfig

    async def _run() -> list[str]:
        cfg = DBConfig.from_env()
        built = await adb_init(cfg)
        try:
            # ``applied`` — flyway hangi migration'ları yeni uyguladı
            # + safety create_all drift tespiti yapılır (asyncio.to_thread).
            from backend.src.data.db.base import Base
            from backend.src.data.db import models  # noqa: F401 — register
            from sqlalchemy.ext.asyncio import engine as _async_engine

            if built.applied:
                print(f"[migrate] flyway uyguladı: {built.applied}")
            else:
                print("[migrate] flyway: yeni migration yok")
            # Drift safety: eksik tablo varsa create_all ile tamamla.
            async with built.engine.begin() as conn:  # type: ignore[attr-defined]
                await conn.run_sync(Base.metadata.create_all)
            print("[migrate] Base.metadata.create_all tamam")
            return built.applied or []
        finally:
            await built.aclose()  # type: ignore[attr-defined]

    try:
        applied = asyncio.run(_run())
        print(f"[migrate] OK, applied={len(applied)}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[migrate] FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def cmd_api(args: argparse.Namespace) -> int:
    _configure_logging()
    try:
        import uvicorn  # type: ignore
    except ImportError:
        print("[api] Hata: uvicorn yüklü değil (pip install uvicorn[standard])",
              file=sys.stderr)
        return 3
    from backend.src.api.main import create_app

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    log_level = os.getenv("API_LOG_LEVEL", "info").lower()

    app = create_app()
    print(f"[api] uvicorn başlıyor: http://{host}:{port} (log_level={log_level})")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("API_TRUSTED_HOSTS", "*"),
    )
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    _configure_logging()
    from backend.src.worker.__main__ import main as worker_main

    print("[worker] WorkerRunner.run_forever() — Ctrl+C ile dur")
    return int(worker_main() or 0)


def cmd_debug_routes(args: argparse.Namespace) -> int:
    """Mount edilmiş rotaları JSON dump — DB ve DI gerekmez."""
    try:
        from backend.src.api.main import create_app
    except Exception as exc:  # noqa: BLE001
        print(f"[debug-routes] import failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 4

    app = create_app()
    routes: list[dict[str, object]] = []

    # FastAPI ``openapi()`` schema'sı tüm mount edilmiş rotaları flat
    # ``{path: {method: op}}`` dict'i olarak döner; ``_IncludedRouter``
    # internal starlette sınıfı olduğu için onun üzerinden enumerate
    # etmek unreliable (path/methods attribute yok). ``openapi()`` ise
    # FastAPI'nin resmi rotaları hesaplanırken kullandığı internal
    # flat list'ten gelir.
    for path, ops in (app.openapi() or {}).get("paths", {}).items():
        if path.startswith(("/openapi", "/docs", "/redoc")):
            continue
        methods = sorted(ops.keys())
        routes.append({"path": path, "methods": methods})

    routes.sort(key=lambda x: (str(x["path"]), str(x["methods"])))
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, object]] = []
    for entry in routes:
        key = (str(entry["path"]), ",".join(entry["methods"]))  # type: ignore[arg-type]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    print(json.dumps(deduped, indent=2, ensure_ascii=False))
    return 0


def cmd_defaults(args: argparse.Namespace) -> int:
    """``migrate`` + ``worker`` aynı process'te, komut sıralı.

    ``api`` modunu çalıştırmaz — default mod çoğunlukla container'da
    worker'ı ayrı container'da tutmak için kullanılır. ``api`` ise
    ayrı ``compose`` service olarak sürekli çalışır.
    """
    rc = cmd_migrate(args)
    if rc != 0:
        return rc
    return cmd_worker(args)


_COMMANDS = {
    "migrate": cmd_migrate,
    "api": cmd_api,
    "worker": cmd_worker,
    "debug-routes": cmd_debug_routes,
    "defaults": cmd_defaults,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command or "defaults"
    handler = _COMMANDS.get(command)
    if handler is None:
        parser.error(f"Bilinmeyen alt-komut: {command!r}")
    return int(handler(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
