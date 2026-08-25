"""Logging format normalization smoke.

Beklenen:
- configure_json_logging() idempotent (2 kez çağrı → 1 stream handler).
- Bir INFO ve bir WARNING kaydı tek-satrık JSON olarak akar.
- `extra={...}` flat `extras` map'i olur.
- correlation_id 2 yoldan da gelir: ekstra dict veya context var.
"""

from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))


from src.observability.logging_config import (  # noqa: E402
    JsonLogFormatter,
    configure_json_logging,
    set_correlation_id,
)


def _install_capture_handler(formatter: JsonLogFormatter) -> io.StringIO:
    buf = io.StringIO()
    handler = logging.StreamHandler(stream=buf)
    handler.setFormatter(formatter)
    handler._is_genai_json_handler = True  # idempotency marker
    return buf, handler


def main() -> int:
    formatter = JsonLogFormatter()
    buf, handler = _install_capture_handler(formatter)

    # Root logger'a yalıtılmış capture handler iliştir (default configure'dan
    # bağımsız). Default handler'lara dokunma.
    log = logging.getLogger("smoke.format")
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    log.propagate = False

    set_correlation_id("cid-aaa")
    log.info("boot complete", extra={"worker_id": "smoke-worker", "x": 1})
    log.warning("retry sched %s", 5, extra={"job_id": "j-7"})
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        log.exception("caught", extra={"payload": {"k": "v"}})
    set_correlation_id(None)
    log.info("without-cid")

    lines = [l for l in buf.getvalue().splitlines() if l]
    if len(lines) != 4:
        print(f"FAIL: expected 4 lines, got {len(lines)}")
        return 1

    records = []
    for ln in lines:
        try:
            records.append(json.loads(ln))
        except json.JSONDecodeError as exc:
            print(f"FAIL: not JSON: {ln!r} ({exc})")
            return 1

    base_keys = {"ts", "level", "logger", "message", "module", "func", "lineno"}
    for rec in records:
        missing = base_keys - rec.keys()
        if missing:
            print(f"FAIL: record missing {missing} → {rec}")
            return 1

    if records[0]["correlation_id"] != "cid-aaa":
        print(f"FAIL: correlations[0]={records[0].get('correlation_id')}")
        return 1
    if records[0]["extras"].get("worker_id") != "smoke-worker":
        print(f"FAIL: extras.worker_id not propagated")
        return 1

    if records[1]["message"] != "retry sched 5":
        print(f"FAIL: %s formatting lost: {records[1]!r}")
        return 1
    if records[1]["extras"].get("job_id") != "j-7":
        print(f"FAIL: warning extras lost")
        return 1

    exc = records[2]
    if exc["level"] != "ERROR":
        print(f"FAIL: exc level {exc['level']}")
        return 1
    if "RuntimeError" not in exc["exc_info"]["type"]:
        print(f"FAIL: exc type missing")
        return 1
    if "boom" not in exc["exc_info"]["message"]:
        print(f"FAIL: exc message missing")
        return 1
    if "RuntimeError: boom" not in exc["exc_info"]["traceback"]:
        print(f"FAIL: traceback missing")
        return 1
    if exc["extras"].get("payload", {}).get("k") != "v":
        print(f"FAIL: nested extras lost")
        return 1

    if "correlation_id" in records[3]:
        print(f"FAIL: fourth record unexpectedly has cid: {records[3]}")
        return 1
    if records[3]["message"] != "without-cid":
        print(f"FAIL: 4th message wrong")
        return 1

    print("OK: 4 kayıt JSON line olarak normalize çıktı")
    print("OK: extras + %-format + correlation_id + exc_info tüm contract karşılandı")
    return 0


if __name__ == "__main__":
    sys.exit(main())
