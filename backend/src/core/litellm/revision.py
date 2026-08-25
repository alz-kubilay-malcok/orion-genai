"""Legacy ``genai_orion_panel_core.commands.{approve,reject,revise}`` stub.

Varlık sebebi: ileride diğer tüketiciler (örn. mailer job dispatch tablosu,
CLI tooling) bu komut sınıflarını doğrudan çağırırsa, ``ImportError`` yerine
açıklayıcı ``NotImplementedError`` alırlar. Mevcut admin_service
rotaları bu modüle bağlı değildir.
"""

from __future__ import annotations

# Approve ---------------------------------------------------------------
class ApproveRequestCommand:                                # pragma: no cover
    def __init__(self, **kwargs):
        raise NotImplementedError("legacy stub")


class ApproveRequestResult:                                  # pragma: no cover
    request_id: object = None
    status: object = None


class ApproveRequestHandler:                                 # pragma: no cover
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("legacy stub")

    async def handle(self, command):                          # pragma: no cover
        raise NotImplementedError("legacy stub")


# Reject ---------------------------------------------------------------
class RejectRequestCommand:                                  # pragma: no cover
    def __init__(self, **kwargs):
        raise NotImplementedError("legacy stub")


class RejectRequestResult:                                   # pragma: no cover
    request_id: object = None
    status: object = None


class RejectRequestHandler:                                  # pragma: no cover
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("legacy stub")

    async def handle(self, command):                          # pragma: no cover
        raise NotImplementedError("legacy stub")


# Revise ---------------------------------------------------------------
class ReviseRequestCommand:                                  # pragma: no cover
    def __init__(self, **kwargs):
        raise NotImplementedError("legacy stub")


class ReviseRequestResult:                                   # pragma: no cover
    request_id: object = None
    status: object = None
    snapshot_taken: bool = False


class ReviseRequestHandler:                                  # pragma: no cover
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("legacy stub")

    async def handle(self, command):                          # pragma: no cover
        raise NotImplementedError("legacy stub")


__all__ = [
    "ApproveRequestCommand", "ApproveRequestHandler", "ApproveRequestResult",
    "RejectRequestCommand", "RejectRequestHandler", "RejectRequestResult",
    "ReviseRequestCommand", "ReviseRequestHandler", "ReviseRequestResult",
]
