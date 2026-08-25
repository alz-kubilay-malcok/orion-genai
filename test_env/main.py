"""Single entrypoint for the test_env harness.

Boot sequence (default: `all`):

1. Load backend ``.env`` into ``os.environ`` so secrets / URLs are visible.
2. Start the mock LiteLLM FastAPI (port 8200) on a background thread.
3. Start the Streamlit ``orion_studio`` panel (port 8501) as a subprocess.
4. Wait for both — Ctrl+C tears them down cleanly.

Subcommands:

* ``all``     — mock + panel (default).
* ``mock``    — only the mock LiteLLM server.
* ``panel``   — only the Streamlit panel.
* ``seed``    — POST one webhooks/orion request per kip türü via ``seed_demo``.
* ``check``   — smoke probes: GET /health/live + GET / on the mock + GET /_stcore/health on the panel.

Examples (run with the system Python that has streamlit + uvicorn, e.g. ``py -3.14``)::

    py -3.14 test_env/main.py              # boot everything
    py -3.14 test_env/main.py mock         # only the API mock
    py -3.14 test_env/main.py panel        # only the UI
    py -3.14 test_env/main.py seed         # POST 3 seeded requests
    py -3.14 test_env/main.py check        # print liveness of running services
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Sequence
from contextlib import suppress
from types import FrameType

from pathlib import Path

# --- paths / ports -----------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_SCRIPTS = os.path.join(_HERE, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

REPO_ROOT = str(Path(_HERE).resolve().parent)
BACKEND_ENV_FILE = os.path.join(REPO_ROOT, "backend", ".env")
PANEL_ENTRY = os.path.join(_HERE, "orion_studio", "app.py")

MOCK_HOST = "127.0.0.1"
MOCK_PORT = 8200
PANEL_HOST = "127.0.0.1"
PANEL_PORT = 8501

# Backend'i BU launcher başlatmaz. Sen kendi terminalinde
#   `cd backend && python main.py [api|worker|all]` ile ayaga kaldiriyorsun.
# Bu sabit sadece `cmd check` ile backend ayakta mi diye kontrol amacli kullaniliyor.
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8001


# Avoid routing localhost through Allianz corp proxy
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
existing = os.environ.get("NO_PROXY", "")
parts = {p.strip() for p in existing.split(",") if p.strip()}
for host in ("localhost", "127.0.0.1"):
    parts.add(host)
os.environ["NO_PROXY"] = ",".join(sorted(parts))

# Module-level cache: which env keys originated from backend/.env (so we can
# distinguish them from shell-exported values).
_LOADED_FROM_FILE: set[str] = set()


def _load_backend_env() -> dict[str, str]:
    """Tiny .env loader (KEY=VALUE, ignores blank lines + ``export``/``set``)."""
    env: dict[str, str] = {}
    if not os.path.isfile(BACKEND_ENV_FILE):
        return env
    with open(BACKEND_ENV_FILE, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export ") or line.startswith("set "):
                line = line.split(None, 1)[1]
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            key = key.strip()
            env[key] = value
            os.environ.setdefault(key, value)
    _LOADED_FROM_FILE.update(env)
    return env


def _print_env_summary() -> None:
    keys = (
        "LITELLM_ACCESS_KEY",
        "GENAI_ORION_PANEL_WEBHOOK_SECRET",
        "ORION_STUDIO_API_BASE",
    )
    print("[env] backend .env loaded from", BACKEND_ENV_FILE)
    for key in keys:
        value = os.environ.get(key)
        if value:
            masked = value if len(value) <= 8 else value[:4] + "…" + value[-2:]
            src = "from .env" if key in _LOADED_FROM_FILE else "from shell/unset"
            print(f"      {key} = {masked}   ({src})")
        else:
            print(f"      {key} = <unset>")


# --- mock server -------------------------------------------------------------


def _run_mock_blocking() -> None:  # pragma: no cover - runs in daemon thread
    import uvicorn

    config = uvicorn.Config(
        "mock_litellm.app:app",
        host=MOCK_HOST,
        port=MOCK_PORT,
        log_level="info",
        access_log=True,
    )
    uvicorn.Server(config).run()


def start_mock() -> threading.Thread:
    t = threading.Thread(
        target=_run_mock_blocking,
        name="mock-litellm",
        daemon=True,
    )
    t.start()
    _wait_for_http(f"http://{MOCK_HOST}:{MOCK_PORT}/health/live", label="mock-litellm")
    return t


# --- streamlit panel ---------------------------------------------------------


def _stream_subprocess_output(
    proc: subprocess.Popen[bytes], *, prefix: str
) -> threading.Thread:
    """Arka plan thread'i: child stdout'unu `[prefix]` ile host stdout'a kopyalar."""

    def _pump() -> None:  # pragma: no cover - tamamen I/O
        if proc.stdout is None:
            return
        for line in iter(proc.stdout.readline, b""):
            try:
                text = line.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            sys.stdout.write(f"[{prefix}] {text}")
            sys.stdout.flush()

    t = threading.Thread(target=_pump, name=f"pump-{prefix}", daemon=True)
    t.start()
    return t


def start_backend_healthcheck() -> None:
    """Backend'e dokunmaz; sadece `cmd check` ile ayakta mi raporlar."""
    try:
        with urllib.request.urlopen(
            f"http://{BACKEND_HOST}:{BACKEND_PORT}/health/live", timeout=1.5
        ) as resp:
            print(f"[check] backend             HTTP {resp.status}")
    except Exception as exc:  # noqa: BLE001
        print(
            f"[check] backend             DOWN    (kendi terminalinde "
            f"`cd backend && python main.py` calistir)  ({exc.__class__.__name__})"
        )


def start_panel() -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    # Make ``orion_studio`` importable when Streamlit launches ``app.py``
    # as a top-level script (cwd is the repo root, not test_env/).
    existing_pp = env.get("PYTHONPATH", "")
    parts = [p for p in existing_pp.split(os.pathsep) if p] if existing_pp else []
    if _HERE not in parts:
        parts.insert(0, _HERE)
    env["PYTHONPATH"] = os.pathsep.join(parts)

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            PANEL_ENTRY,
            "--server.port",
            str(PANEL_PORT),
            "--server.address",
            PANEL_HOST,
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    _wait_for_http(
        f"http://{PANEL_HOST}:{PANEL_PORT}/_stcore/health",
        label="streamlit-panel",
        ok_statuses=(200, 503),  # /_stcore/health returns 503 until app loads; still healthy
    )
    return proc


# --- shared helpers ----------------------------------------------------------


def _wait_for_http(
    url: str,
    *,
    label: str,
    timeout: float = 15.0,
    ok_statuses: tuple[int, ...] = (200,),
) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status in ok_statuses:
                    print(f"[ready] {label} -> {url} (HTTP {resp.status})")
                    return
        except Exception as exc:  # noqa: BLE001 - any failure means "not ready yet"
            last_err = exc
        time.sleep(0.3)
    raise RuntimeError(f"timeout waiting for {label} at {url}: {last_err}")


def _install_sigterm_forward(targets: Sequence[subprocess.Popen[bytes] | threading.Thread]) -> None:
    def _handler(signum: int, _frame: FrameType | None) -> None:
        print(f"\n[exit] received signal {signum}; stopping children")
        for t in targets:
            if isinstance(t, subprocess.Popen):
                with suppress(Exception):
                    t.terminate()
            else:
                # threads are daemons; nothing to do, just exit
                pass
        for t in targets:
            if isinstance(t, subprocess.Popen):
                with suppress(Exception):
                    t.wait(timeout=3)
        sys.exit(0)

    signal.signal(signal.SIGINT, _handler)
    with suppress(ValueError, AttributeError):  # SIGTERM may not exist on Windows
        signal.signal(signal.SIGTERM, _handler)


# --- subcommands -------------------------------------------------------------


def cmd_all(_args: argparse.Namespace) -> int:
    """Mock + Streamlit panel — backend'i sen kendi terminalinda baslatiyorsun."""
    _print_env_summary()

    mock_thread = start_mock()
    panel_proc = start_panel()
    _install_sigterm_forward([mock_thread, panel_proc])

    print()
    print("=" * 60)
    print(f"Mock LiteLLM:    http://{MOCK_HOST}:{MOCK_PORT}")
    print(f"Streamlit panel: http://{PANEL_HOST}:{PANEL_PORT}")
    print("Backend'i sen ayri terminalinda baslatiyorsun:")
    print("    cd backend && python main.py all")
    print("Press Ctrl+C to stop mock + panel.")
    print("=" * 60)
    start_backend_healthcheck()
    try:
        panel_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if panel_proc.poll() is None:
            with suppress(Exception):
                panel_proc.terminate()
                panel_proc.wait(timeout=3)
    return 0


def cmd_mock(_args: argparse.Namespace) -> int:
    _print_env_summary()
    start_mock()
    print("[mock] running — Ctrl+C to stop.")
    signal.pause()
    return 0


def cmd_panel(_args: argparse.Namespace) -> int:
    _print_env_summary()
    proc = start_panel()
    _install_sigterm_forward([proc])
    proc.wait()
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    import seed_demo

    if args.only:
        only = args.only
    else:
        only = list(seed_demo.BUILDERS)
    print(f"[seed] posting {only} to {seed_demo.BACKEND}{seed_demo.WEBHOOK_PATH}")
    rc = seed_demo.main(only)
    return rc


def cmd_check(_args: argparse.Namespace) -> int:
    _print_env_summary()
    probes = (
        (f"http://{MOCK_HOST}:{MOCK_PORT}/health/live", "mock-litellm"),
        (f"http://{MOCK_HOST}:{MOCK_PORT}/key/info", "mock-litellm-admin"),
        (f"http://{MOCK_HOST}:{MOCK_PORT}/__mock/state", "mock-litellm-debug"),
        (f"http://{PANEL_HOST}:{PANEL_PORT}/_stcore/health", "streamlit-panel"),
    )
    for url, label in probes:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                print(f"[check] {label:22s} HTTP {resp.status}  {url}")
        except Exception as exc:  # noqa: BLE001
            print(f"[check] {label:22s} DOWN    {url}  ({exc.__class__.__name__})")
    return 0


# --- arg parser --------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="test_env.main",
        description=(
            "Boot the test_env harness.\n"
            "default = 'all' (mock + backend(api+worker) + panel).\n"
            "Tek terminal, tek Ctrl+C ile üçü de kapanır."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=False)

    sub.add_parser("all", help="mock + backend(all) + panel (default)").set_defaults(
        func=cmd_all
    )

    sub.add_parser("mock", help="boot only the mock LiteLLM server").set_defaults(
        func=cmd_mock
    )
    sub.add_parser("panel", help="boot only the Streamlit panel").set_defaults(
        func=cmd_panel
    )

    seed_p = sub.add_parser("seed", help="POST 3 seeded webhook requests")
    seed_p.add_argument(
        "only",
        nargs="*",
        choices=("litellm", "mcp_key", "mcp_registry"),
        help="limit to a subset of talep türleri",
    )
    seed_p.set_defaults(func=cmd_seed)

    sub.add_parser(
        "check", help="GET /health on each service and report status"
    ).set_defaults(func=cmd_check)

    # No subcommand? Boot the full stack by default.
    parser.set_defaults(func=cmd_all)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    _load_backend_env()  # populates _LOADED_FROM_FILE so the summary is accurate
    return args.func(args)  # type: ignore[arg-type]


if __name__ == "__main__":
    raise SystemExit(main())
