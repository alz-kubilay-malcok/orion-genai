"""HMAC tabanlı business-token signer (approval action capability).

Legacy ``genai_orion_panel_adapters.crypto.signer.HmacTokenSigner``
sözleşmesinin **minimal** implementasyonu. Davranış sözleşmesi:

* ``__init__(secret: str)`` — boş secret kabul edilmez.
* ``sign(claims) -> str`` — kullanıcıya tek-POST-wins dışında ihtiyaç
  yok; yine de bırakıldı (ileride test fixture'ı için).
* ``verify(token) -> dict`` — yetkilendirme akışında kullanılır; imza
  uyuşmazsa ``InvalidActionTokenError`` raise eder.

Algoritma: HMAC-SHA256, payload = base64url(json(claims, sort_keys=True,
separators=(",", ":"))); token = ``payload_b64 + "." + sig_b64``.

Güvenlik notları:

* ``hmac.compare_digest`` kullanıldı → timing-safe karşılaştırma.
* ``json.dumps(..., sort_keys=True)`` → aynı claims kümesi her zaman
  aynı bayt üretir (imza deterministik).
* Token süre-aşımı / revocation kontrolü **burada yapılmaz**;
  ``Approve/Reject/ReviseRequestHandler`` içindeki iş mantığı audit
  tablosu üzerinden kontrol eder.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from backend.src.domain.errors import InvalidActionTokenError


class HmacTokenSigner:
    """(payload_b64, sig_b64) formatında HMAC-SHA256 imzalı token üretir/doğrular."""

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("action_signing_secret boş olamaz")
        # bytes'e bir kez çevirip sakla; her çağrıda yeniden encode etme.
        self._secret = secret.encode("utf-8")

    # ---- public API --------------------------------------------------

    def sign(self, claims: dict[str, Any]) -> str:
        """Payload'ı imzalar ve ``"<b64>.<sig>"`` döner.

        Web akışında padding taşımak (``=``) sıkıntı çıkarabilir; partner
        ``%3D`` URL-encode trap'ine düşmesin diye padding kaldırılmış
        base64 kullanılır. Verify tarafında aynı padding'siz kabul
        ``_b64decode`` helper'ı ile telafi edilir.
        """
        payload = self._encode_payload(claims)
        sig = self._sign_payload_b64_raw(payload)
        sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
        return f"{payload}.{sig_b64}"

    def verify(self, token: str) -> dict[str, Any]:
        """İmza doğrular ve payload claims'i döner.

        Raises:
            InvalidActionTokenError: format/imza uyuşmazlığı ya da
                payload decode edilemediğinde.
        """
        if not token or "." not in token:
            raise InvalidActionTokenError("malformed token")
        payload_b64, sig_b64 = token.rsplit(".", 1)
        expected_sig = self._sign_payload_b64_raw(payload_b64)
        try:
            actual_sig = self._b64decode(sig_b64)
        except (ValueError, TypeError, base64.binascii.Error) as exc:
            raise InvalidActionTokenError("base64 decode failed") from exc
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise InvalidActionTokenError("bad signature")
        try:
            raw = self._b64decode(payload_b64)
            return json.loads(raw)
        except (ValueError, TypeError, base64.binascii.Error, json.JSONDecodeError) as exc:
            raise InvalidActionTokenError("payload decode failed") from exc

    # ---- internals ----------------------------------------------------

    @staticmethod
    def _encode_payload(claims: dict[str, Any]) -> str:
        raw = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _sign_payload_b64_raw(self, payload_b64: str) -> bytes:
        return hmac.new(
            self._secret, payload_b64.encode("ascii"), hashlib.sha256,
        ).digest()

    @staticmethod
    def _b64decode(s: str) -> bytes:
        """Padding'siz URL-safe base64'ü güvenle decode eder."""
        pad = "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s + pad)


__all__ = ["HmacTokenSigner"]
