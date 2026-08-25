"""Worker + API log format.

Varsayılan: tek satır console (docker logs okunaklı).
``LOG_FORMAT=json`` eski JSON line. LiteLLM satırları kırmızı.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import sys
from typing import Any

try:
    import contextvars as _cv  # type: ignore
    _CORRELATION_ID: _cv.ContextVar[str | None] = _cv.ContextVar(
        "log_correlation_id", default=None,
    )
    _CONTEXTVARS_ENABLED = True
except ImportError:  # extremely unlikely
    _CONTEXTVARS_ENABLED = False


def set_correlation_id(value: str | None) -> None:
    if not _CONTEXTVARS_ENABLED:
        return
    if value is None:
        _CORRELATION_ID.set(None)
        return
    _CORRELATION_ID.set(value)


def get_correlation_id() -> str | None:
    if _CONTEXTVARS_ENABLED:
        cid = _CORRELATION_ID.get()
        if cid:
            return cid
    return os.getenv("LOG_CORRELATION_ID")


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"
    return str(value)


_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

_LITELLM_HINTS = (
    "litellm",
    "/key/generate",
    "/mcp/keys",
    "provision:litellm",
)


def _color_enabled() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    flag = (os.getenv("LOG_COLOR") or "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def _is_litellm_record(record: logging.LogRecord) -> bool:
    blob = " ".join((
        record.name,
        record.getMessage(),
        str(getattr(record, "event", "")),
        str(getattr(record, "job_type", "")),
        str(getattr(record, "kind", "")),
    )).lower()
    return any(hint in blob for hint in _LITELLM_HINTS)


class JsonLogFormatter(logging.Formatter):
    """Her kaydı tek-satır JSON olarak basar (LOG_FORMAT=json)."""

    RESERVED = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "asctime",
        "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _dt.datetime.fromtimestamp(
                record.created, tz=_dt.timezone.utc,
            ).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "lineno": record.lineno,
        }
        cid = getattr(record, "correlation_id", None) or get_correlation_id()
        if cid:
            payload["correlation_id"] = cid

        extras = {
            k: _to_jsonable(v)
            for k, v in record.__dict__.items()
            if k not in self.RESERVED and not k.startswith("_")
            and k not in {"correlation_id"}
        }
        if extras:
            payload["extras"] = extras

        if record.exc_info:
            payload["exc_info"] = self._format_exc(record)

        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def _format_exc(record: logging.LogRecord) -> dict[str, Any]:
        import traceback as _tb
        if record.exc_info and record.exc_info[0] is not None:
            etype, evalue, etb = record.exc_info
            return {
                "type": etype.__name__,
                "message": str(evalue) if evalue else "",
                "traceback": "".join(
                    _tb.format_exception(etype, evalue, etb),
                ).rstrip(),
            }
        return {"type": "Unknown", "message": "", "traceback": ""}


class ConsoleLogFormatter(logging.Formatter):
    """Docker/TTY: ``21:04:15  INFO  worker  başladı``."""

    _KEEP_EXTRA = (
        "event", "job_id", "job_type", "final_status", "error_code",
        "request_id", "status", "kind",
    )

    def format(self, record: logging.LogRecord) -> str:
        ts = _dt.datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        logger_name = record.name.rsplit(".", 1)[-1]
        msg = record.getMessage()
        bits = [f"{ts}", f"{record.levelname:<5}", f"{logger_name:<12}", msg]
        extra_parts: list[str] = []
        for key in self._KEEP_EXTRA:
            value = getattr(record, key, None)
            if value not in (None, "", []):
                extra_parts.append(f"{key}={value}")
        if extra_parts:
            bits.append(" ".join(extra_parts))
        if record.exc_info:
            bits.append(self.formatException(record.exc_info).replace("\n", " | "))
        line = "  ".join(bits)
        if not _color_enabled():
            return line
        litellm = _is_litellm_record(record)
        if litellm or record.levelno >= logging.ERROR:
            return f"{_BOLD}{_RED}{line}{_RESET}"
        if record.levelno >= logging.WARNING:
            return f"{_YELLOW}{line}{_RESET}"
        if record.levelno <= logging.DEBUG:
            return f"{_DIM}{line}{_RESET}"
        return f"{_GREEN}{line}{_RESET}"


def _quiet_noisy_loggers() -> None:
    for name in (
        "httpx",
        "httpcore",
        "urllib3",
        "asyncio",
        "multipart",
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "uvicorn.access",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Kök logger. Varsayılan console; ``LOG_FORMAT=json`` JSON line.

    Birden fazla kez çağrılırsa idempotent (mükerrer handler eklenmez).
    """
    root = logging.getLogger()
    fmt_name = (os.getenv("LOG_FORMAT") or "console").strip().lower()
    formatter: logging.Formatter = (
        JsonLogFormatter() if fmt_name == "json" else ConsoleLogFormatter()
    )

    existing = [
        h for h in root.handlers
        if getattr(h, "_is_genai_json_handler", False)
    ]
    if existing:
        for handler in existing:
            handler.setFormatter(formatter)
        root.setLevel(level)
        _quiet_noisy_loggers()
        return

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(formatter)
    handler._is_genai_json_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)
    _quiet_noisy_loggers()


__all__ = [
    "ConsoleLogFormatter",
    "JsonLogFormatter",
    "configure_json_logging",
    "set_correlation_id",
    "get_correlation_id",
]
