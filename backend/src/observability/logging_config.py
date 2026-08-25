"""Worker + dispatcher log format normalization.

Tek bir JSON line üretir; `extra=` ile verilen tüm struct field'lar
flat çıkar. `correlation_id` kaydını 3 yerden dener:

1. ``LogRecord.correlation_id`` (eğer caller ``extra={"correlation_id":
   ...}`` geçtiyse)
2. ``logging.LoggerAdapter`` üzerinden ``context_correlation_id``
3. ``LOG_CORRELATION_ID`` env (smoke'sız, container-job'i varsa)

NOT: Python 3.14'te ``logger.warning(msg % args, extra=dict)`` artık
``%``-format pitfall'u taşır; caller'lar ya lazy ``logger.warning(...
extra={...})`` ya da ``logger.info("... %s", value, extra={...})``
biçimi kullanır. Bu formatter her iki stili de kabul eder.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
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
        # Eksplicit reset — çağıran taraf sızıntı istemiyorsa.
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


class JsonLogFormatter(logging.Formatter):
    """Her kaydı tek-satır JSON olarak basar.

    Output alanları (stable contract):
      - ts (ISO-8601 UTC, "Z" suffix)
      - level
      - logger
      - message
      - correlation_id (varsa)
      - module/func/lineno
      - extras: caller'ın ``extra=`` ile gönderdiği tüm struct field'lar
      - exc_info: varsa ``{"type": ..., "message": ..., "traceback": ...}``
    """

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


def configure_json_logging(level: int = logging.INFO) -> None:
    """Yapılandırma: kök logger'a ``JsonLogFormatter`` bağla.

    Birden fazla kez çağrılırsa idempotent davranır (mükerrer handler
    eklenmez).
    """
    root = logging.getLogger()
    if any(
        getattr(h, "_is_genai_json_handler", False)
        for h in root.handlers
    ):
        root.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler._is_genai_json_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)


__all__ = [
    "JsonLogFormatter",
    "configure_json_logging",
    "set_correlation_id",
    "get_correlation_id",
]
