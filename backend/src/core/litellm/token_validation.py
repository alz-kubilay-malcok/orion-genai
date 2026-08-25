"""Legacy ``genai_orion_panel_core.application.commands._token_validation`` stub.

Legacy ``core`` paketinin private modülüydü; ancak ``worker/handlers`` ve
bazı admin yolları bu sembolleri ``from …core.application.commands._token_validation
import verify_and_parse, _invalidate_siblings`` formunda kullanır.

Bu stub, güvenlik invariantı koruyacak şekilde ``InvalidActionTokenError``
ile fail-fast eder. Production ready implementasyon sonraki refactor
turunda eklenecek — ``approval_actions.py`` flush sırasında gerçek
mantığı kullanır.
"""

from __future__ import annotations


async def verify_and_parse(*args, **kwargs):                # pragma: no cover
    raise NotImplementedError(
        "legacy stub — token doğrulama doğrudan "
        "state.token_signer.verify ile yapılır (approval_actions.py)."
    )


async def _invalidate_siblings(*args, **kwargs):            # pragma: no cover
    raise NotImplementedError(
        "legacy stub — sibling token iptal mantığı "
        "admin_service ve token_validation modülüne taşınmadı."
    )


__all__ = ["verify_and_parse", "_invalidate_siblings"]
