"""Backend `core.mailing` — SMTP mail facade + template engine.

Alt dosyalar:
- `mailer.py`           → pub: `send_mail(...)`, `render_template(name, **kw)`
- `templates/*.html`    → 5 adet HTML dosyası (`string.Template` +
                          `#if $key` blok parser'ı).

Receiver listesi bu pakette **çözümlenmez** — dışarıdan (DB/LDAP) çağıran
verir. SMTP server/sender adresi `os.environ`'dan okunur, test
ortamında override edilebilir.
"""

from __future__ import annotations

from .approval_inputs import (
    LitellmApprovalMailInputs,
    McpApprovalMailInputs,
    litellm_approval_inputs,
    mcp_approval_inputs,
)
from .mailer import render_template, send_mail
from .result_inputs import litellm_result_inputs, mcp_result_inputs, result_template_name

__all__ = [
    "LitellmApprovalMailInputs",
    "McpApprovalMailInputs",
    "litellm_approval_inputs",
    "litellm_result_inputs",
    "mcp_approval_inputs",
    "mcp_result_inputs",
    "render_template",
    "result_template_name",
    "send_mail",
]
