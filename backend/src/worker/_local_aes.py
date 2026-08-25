"""Backend `worker` — Çalışan süreçler için adapter + yardımcılar.

Bu modül yerelde AES-256-GCM şifreleme sağlar; harici
`genai_orion_panel_adapters.crypto.cipher.AesGcmSecretCipher` paketi
editable olarak bağlı değilse veya ``KEY_ENCRYPTION_KEY`` env boşsa
fallback sunar.

Tasarım amacı:
    * Production'da dış adapter varsa onu tercih et, davranışı değiştirme.
    * Dev/CI'da auto-generated 32 byte base64 key + AESGCM ile aynı
      contract'ı sağla ki handler'lar ``cipher.encrypt/decrypt`` çağırırsa
      ``Secret`` tablosuna yazılabilir.
    * Key ring / rotation **desteklenmez** — sadece ``current_key``.
      Eski key'leri çözümlemek için dış adapter şart. Lokal adapter
      yalnızca **encrypt-path** + **current-key decrypt** yapar; farklı
      ``key_version`` ile ``decrypt`` çağrısı ``ValueError`` raise eder
      (handoff: production'da dış adapter'a dönüş gerekir).

Envelope contract (Secret ORM ile uyumlu):
    * ``nonce`` — 12 byte CSPRNG (``os.urandom(12)``) — AES-GCM 96-bit.
    * ``ciphertext`` — AES-256-GCM çıkışı, **tag hariç** (tag ayrı tutulur).
    * ``auth_tag`` — 16 byte (AES-GCM default 128-bit tag).
    * ``key_version`` — encrypt anındaki current version.
    * ``key_hint`` — current key'in son 2 byte'ının hex'i (4 char); DB
      ``CHAR(4)`` ile uyumlu.
"""

from __future__ import annotations

import base64
import os
import secrets as _secrets
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True, slots=True)
class Envelope:
    """AES-GCM envelope — `Secret` ORM satırıyla 1:1 eşleşir."""

    nonce: bytes          # 12 byte
    ciphertext: bytes     # tag hariç
    auth_tag: bytes       # 16 byte
    key_version: int
    key_hint: str         # 4 char


class LocalAesGcmSecretCipher:
    """Legacy ``AesGcmSecretCipher`` ile aynı interface.

    Constructor ``(current_key_b64: str, current_key_version: int)``.
    ``current_key_b64`` base64-decode edilince **exactly 32 byte**
    olmalı (AES-256). Aksi halde ``ValueError``.
    """

    NONCE_LEN: int = 12
    TAG_LEN: int = 16
    KEY_LEN: int = 32
    HINT_LEN: int = 4

    def __init__(self, current_key_b64: str, current_key_version: int) -> None:
        try:
            key = base64.b64decode(current_key_b64.encode("ascii"), validate=True)
        except Exception as exc:
            raise ValueError(f"current_key_b64 invalid base64: {exc}") from exc
        if len(key) != self.KEY_LEN:
            raise ValueError(
                f"current_key_b64 must decode to {self.KEY_LEN} bytes; got {len(key)}"
            )
        self._key = key
        self._version = current_key_version
        # hint = last-2-byte hex (4 chars); DB CHAR(4) ile uyumlu
        self._hint = key[-2:].hex()[: self.HINT_LEN]

    @property
    def key_hint(self) -> str:
        return self._hint

    @property
    def key_version(self) -> int:
        return self._version

    def encrypt(self, plaintext: bytes, *, aad: bytes = b"") -> Envelope:
        """AES-256-GCM encrypt; AAD opsiyonel, encrypt+decrypt aynı olmalı."""
        if not isinstance(plaintext, (bytes, bytearray, memoryview)):
            raise TypeError("plaintext must be bytes-like")
        nonce = os.urandom(self.NONCE_LEN)
        aead = AESGCM(self._key)
        ct_with_tag = aead.encrypt(nonce, bytes(plaintext), aad or None)
        ct = ct_with_tag[: -self.TAG_LEN]
        tag = ct_with_tag[-self.TAG_LEN :]
        return Envelope(
            nonce=bytes(nonce),
            ciphertext=ct,
            auth_tag=tag,
            key_version=self._version,
            key_hint=self._hint,
        )

    def decrypt(
        self,
        nonce: bytes,
        ciphertext: bytes,
        auth_tag: bytes,
        *,
        aad: bytes = b"",
        key_version: Optional[int] = None,
        key_hint: Optional[str] = None,
    ) -> bytes:
        """AES-256-GCM decrypt. ``key_version`` farklıysa ``ValueError``.

        Key rotation yok — eski key'leri çözmek için dış adapter'a dönmek
        gerekir. ``key_hint`` şimdilik yalnızca insan-okunur fingerprint.
        """
        if key_version is not None and key_version != self._version:
            raise ValueError(
                f"key_version mismatch: enciphered={key_version} current={self._version}; "
                "local adapter does not implement key-ring, fallback erforderlich"
            )
        if len(nonce) != self.NONCE_LEN:
            raise ValueError(f"nonce must be {self.NONCE_LEN} bytes; got {len(nonce)}")
        aead = AESGCM(self._key)
        return aead.decrypt(nonce, bytes(ciphertext) + bytes(auth_tag), aad or None)


def generate_dev_key_b64() -> str:
    """32-byte CSPRNG base64 string — dev/test için.

    Production'da asla kullanma; her restart'ta farklı key üretir → Secret
    tablosundaki kayıtlar çözümsüz olur.
    """
    return base64.b64encode(_secrets.token_bytes(32)).decode("ascii")


__all__ = [
    "Envelope",
    "LocalAesGcmSecretCipher",
    "generate_dev_key_b64",
]
