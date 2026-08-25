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

from .mailer import render_template, send_mail

__all__ = ["send_mail", "render_template"]
