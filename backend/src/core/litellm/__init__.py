"""Legacy ``genai_orion_panel_core.application.commands`` facade.

Refactor (2026-08-25): modül yalnızca public isimleri ihraç eder;
command handler gövdeleri bu PRD turunda sıfırdan inşa edilmedi.
``worker/handlers.py`` string-literal dispatch kullandığı için bu facade
pasifdir — kaldırıldığında import kapsamı daraltılabilir.

Aşağıdaki semboller ileride gerçek handler'lar için Protocol sınıfları
haline getirilecek:

* :class:`ApproveRequestCommand` / :class:`ApproveRequestHandler` /
  :class:`ApproveRequestResult`
* :class:`ReviseRequestCommand`  / :class:`ReviseRequestHandler`  /
  :class:`ReviseRequestResult`
* :class:`RejectRequestCommand`  / :class:`RejectRequestHandler` /
  :class:`RejectRequestResult`
* :func:`provision_litellm_key` / :func:`provision_mcp_key`

Bu modül şu sürümde ``backend.src.api.utils.admin_service`` yüzeyi
üzerinden rotaları besler; ``worker.handlers`` ise aynı isimleri
``JOB_TYPE_*`` string dispatch ile bire bir geçer.
"""

from __future__ import annotations

# Bu facade PRD turunda boş bırakıldı: import eden tüketiciler başka bir
# modüle yönlendirildi (admin_service, lifecycle adapters).
__all__: list[str] = []
