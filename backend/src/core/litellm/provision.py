"""Legacy ``application.jobs.provision_*`` modülü boşaltılmış iskelet.

Gerçek provision akışı (LiteLLM key / MCP key / MCP registry registration)
şu anda ``worker/handlers.py`` içindeki string-literal dispatch
kullanılarak çağrılır; bu modülün varlık sebebi:

1. İçe aktaran (örn. eski testler, ``import backend.src.api.utils.admin_service``
   dolaylı yoldan bu modüle değil) varsa ``ImportError`` yerine açıklayıcı
   ``NotImplementedError`` alır.
2. Sonraki refactor turu ProvisionLiteLLMKeyJob / ProvisionMCPKeyJob
   protokollerini burada sergiletmeden önce geçici bir uyumluluk katmanı.

Davranış sözleşmesi (yeniden inşa gereken):

* Paydaş: ``worker/handlers._make_provision_litellm_handler`` →
  ``provision_litellm_key(session=..., deps=..., payload=...)``.
* Native dispatch burada olmadığı için referanslar NotImplemented.
"""

from __future__ import annotations

async def provision_litellm_key(*, session, deps, payload):  # pragma: no cover
    raise NotImplementedError(
        "legacy compat stub — gerçek implementasyon "
        "worker/handlers.build_handlers içindedir (string dispatch)."
    )


async def provision_mcp_key(*, session, deps, payload):  # pragma: no cover
    raise NotImplementedError(
        "legacy compat stub — gerçek implementasyon "
        "worker/handlers.build_handlers içindedir (string dispatch)."
    )


__all__ = ["provision_litellm_key", "provision_mcp_key"]
