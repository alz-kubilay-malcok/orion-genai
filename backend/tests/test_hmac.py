import hashlib
import hmac
from unittest.mock import MagicMock

from fastapi.responses import JSONResponse

from backend.src.api.routes.orion_webhook import webhook_signature_failure
from backend.src.api.utils.hmac_signer import HmacTokenSigner
from backend.src.domain.errors import InvalidActionTokenError


def test_signer_roundtrip():
    signer = HmacTokenSigner("x" * 32)
    token = signer.sign({"sub": "a", "n": 1})
    assert signer.verify(token) == {"n": 1, "sub": "a"}


def test_signer_bad_sig():
    signer = HmacTokenSigner("x" * 32)
    token = signer.sign({"sub": "a"})
    other = HmacTokenSigner("y" * 32)
    try:
        other.verify(token)
        raise AssertionError("expected InvalidActionTokenError")
    except InvalidActionTokenError:
        pass


def test_webhook_hmac_401(monkeypatch):
    secret = "dev-orion-secret"
    monkeypatch.setenv("GENAI_ORION_PANEL_WEBHOOK_AUTH_MODE", "hmac")
    monkeypatch.setenv("GENAI_ORION_PANEL_WEBHOOK_SECRET", secret)
    body = b'{"talep_turu":"x"}'
    request = MagicMock()
    request.headers.get.return_value = "deadbeef"
    rejected = webhook_signature_failure(request, body)
    assert isinstance(rejected, JSONResponse)
    assert rejected.status_code == 401


def test_webhook_hmac_ok(monkeypatch):
    secret = "dev-orion-secret"
    monkeypatch.setenv("GENAI_ORION_PANEL_WEBHOOK_AUTH_MODE", "hmac")
    monkeypatch.setenv("GENAI_ORION_PANEL_WEBHOOK_SECRET", secret)
    body = b'{"talep_turu":"x"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    request = MagicMock()
    request.headers.get.return_value = sig
    assert webhook_signature_failure(request, body) is None
