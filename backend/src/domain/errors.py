"""Hexagonal domain hata sözleşmesi.

``DomainError`` ve alt-sınıfları application katmanı + admin_service
modülünün ihtiyaç duyduğu **daraltılmış** yüzeydir. İsimlendirme ve
``error_code`` sınıf attribute'u legacy sözleşmesiyle birebir aynıdır.

Kapsam (bu turda):

* ``DomainError`` — taban sınıf.
* ``RequestNotFoundError`` — admin_service.py L39-41.
* ``OptimisticLockConflictError`` — admin_service.py L43-45.
* ``LiteLLMEstimateMissingError`` — admin_service.py L47-49.
* ``ActionNotAllowedForTypeError`` — admin_service.py L21-24.
* ``InvalidActionTokenError`` — approval_actions.py & signer.verify()
  için. ``error_code = "INVALID_ACTION_TOKEN"``.

Genişletme: refactor turunda ``domain/transitions.py`` ve
``domain/entities/request.py`` eklendiğinde domain-specific hata
sınıfları (örn. ``TransitionNotAllowedError``) buraya eklenir.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Uygulamanın semantik hatalarını temsil eder.

    ``error_code`` sınıf attribute'u API katmanında HTTP durum kodu
    eşlemesine kaynak olur (bkz. ``_DOMAIN_ERROR_STATUS`` haritaları).
    Mesaj, kullanıcı/operatöre gösterilebilecek Türkçe kısa tümce
    önerilir; PII içermemelidir.
    """

    error_code: str = "DOMAIN_ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__

    # Uyumluluk: legacy ``details: dict`` ya da ``args: tuple`` tüketen
    # yerler için ``.args`` üzerinden bağlanır.
    def __reduce__(self) -> Any:  # pragma: no cover - debug helper
        return (self.__class__, (self.message,))


class RequestNotFoundError(DomainError):
    error_code = "NOT_FOUND"


class OptimisticLockConflictError(DomainError):
    error_code = "OPTIMISTIC_LOCK_CONFLICT"


class LiteLLMEstimateMissingError(DomainError):
    error_code = "LITELLM_ESTIMATE_MISSING"


class ActionNotAllowedForTypeError(DomainError):
    error_code = "ACTION_NOT_ALLOWED_FOR_TYPE"


class InvalidActionTokenError(DomainError):
    error_code = "INVALID_ACTION_TOKEN"


class AlreadyProcessedError(DomainError):
    error_code = "ALREADY_PROCESSED"


__all__ = [
    "ActionNotAllowedForTypeError",
    "AlreadyProcessedError",
    "DomainError",
    "InvalidActionTokenError",
    "LiteLLMEstimateMissingError",
    "OptimisticLockConflictError",
    "RequestNotFoundError",
]
