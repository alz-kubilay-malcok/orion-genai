"""SMTP mail gönderimi — `send_mail(...)` ve `render_template(...)` iki public yüz.

İki giriş noktası:
- `send_mail(...)`                 — SMTP üzerinden gönderir.
- `render_template(name, **kw)`   — sadece HTML çıktısı üretir (test/önizleme).

Template'ler `templates/ klasöründe .html dosyasıdır; `string.Template`
ile `$identifier` placeholder çözümü + `#if key ... #else ... #end`
blok parser'ı (yalnız basit truthy/falsy test).

Receiver listesi bu modülde **çözümlenmez** — dışarıdan verilir; SMTP
sunucu/sender adresi `os.environ`'dan okunur.

Örnek kullanım:
    send_mail(
        recipients=["admin1@allianz.com.tr", "admin2@allianz.com.tr"],
        subject="[GenAi] LiteLLM key — onayınız bekleniyor",
        template_name="litellm_key_approval",
        ticket_id="ORION-1234",
        approver_name="Burak",
        ...
    )
"""

from __future__ import annotations

import html
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
from pathlib import Path
from string import Template

_DEFAULT_SENDER = "GenAi Key Dispatcher <genai_key_dispatcher@info.com>"
_DEFAULT_SERVER = "mailenable.allianz-tr.local"
_DEFAULT_PORT = 25

# Bu dosya backend/src/core/mailing/mailer.py; templates/ kardeş klasördür.
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_PLACEHOLDER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
# #if <ident> ... (#else ...) ... #end  — basit blok parser.
# `re.DOTALL` çok satırlı blokları yakalar.
_IF_RE = re.compile(
    r"#if\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?P<body>.*?)(?:#else\s*(?P<alt>.*?))?#end",
    re.DOTALL,
)
# Tepedeki tek seferlik yorum bloğunu (örn. `<!-- ... $identifier ... -->
# ↴ <!DOCTYPE...>`) render'dan önce sıyır. `$` içeren örnek syntax rehin
# alınmasın.
_LEADING_COMMENT = re.compile(r"^\s*<!--.*?-->\s*", re.DOTALL)


# ---- Template render ---------------------------------------------------


def _resolve_condition(token: str, ctx: dict[str, object]) -> bool:
    """`#if $X` için truthy test. Bilinmeyen key False sayılır."""
    return bool(ctx.get(token))


def _escape(value: object) -> str:
    """Caller tarafından geçilen tüm inputlar `html.escape` edilir."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _evaluate_blocks(source: str, ctx: dict[str, object]) -> str:
    """`#if $X ... #end` ve `#if $X ... #else ... #end` bloklarını indirger.

    Yalnız `#if <python-benzer-isim>` formunu destekler; karşılaştırma/
    operatör YOK (FSM karmaşıklığına girmez).
    """
    def repl(match: re.Match[str]) -> str:
        cond_name = match.group(1)
        body = match.group("body") or ""
        alt = match.group("alt")
        if _resolve_condition(cond_name, ctx):
            return body
        return alt or ""

    return _IF_RE.sub(repl, source)


def _resolve_unresolved_marker(marker: str) -> str:
    """Unresolved placeholder'ı HTML güvenli debug commentsine çevirir."""
    return f"<!-- unresolved:{marker} -->"


def render_template(name: str, **inputs: object) -> str:
    """`templates/<name>.html` dosyasını oku, render et, geri döndür.

    Input değerleri `html.escape` ile güvenli hale getirilir; XSS'e kapalı.
    `inputs` içindeki `_unescaped` set'i içindeki key'ler için raw HTML
    pass-through (örn. önceden render edilmiş tablo satırları).
    """
    unescaped_keys: set[str] = set(inputs.pop("_unescaped", ()) or ())  # type: ignore[arg-type]
    path = _TEMPLATES_DIR / f"{name}.html"
    if not path.is_file():
        msg = f"Template bulunamadı: {path}"
        raise FileNotFoundError(msg)
    source = path.read_text(encoding="utf-8")
    # Tepedeki `<!-- açıklama -->` bloğu `$identifier` örneklerini içerir;
    # bunlar placeholder olarak yutulmasın.
    source = _LEADING_COMMENT.sub("", source, count=1)

    def _resolve_ctx() -> dict[str, object]:
        # Eğer koşul blokları render sırasında bir key'i arıyorsa
        # truthy testi burada `inputs` üzerinden çalışır.
        return inputs  # noqa: F841 — kullanıcıya kalmış alanlar

    rendered = _evaluate_blocks(source, _resolve_ctx())

    # Context'te olan key için `$X` → escaped value; olmayan için debug marker.
    ctx_escape = {k: _escape(v) for k, v in inputs.items() if k not in unescaped_keys}
    ctx_raw = {k: inputs[k] for k in inputs if k in unescaped_keys}
    full_ctx: dict[str, object] = {**ctx_escape, **ctx_raw}
    # Undefined placeholder `string.Template` için güvenli: missing → marker.
    template = Template(rendered)
    rendered = template.safe_substitute(full_ctx)
    rendered = _PLACEHOLDER.sub(lambda m: _resolve_unresolved_marker(m.group(1)), rendered)
    return rendered


# ---- SMTP ---------------------------------------------------------------


def _build_mime(
    *,
    sender: str,
    recipients: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    html_body: str,
) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = COMMASPACE.join(recipients)
    msg["Cc"] = COMMASPACE.join(cc) if cc else ""
    msg["Date"] = formatdate(localtime=False)
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    return msg


def _resolve_smtp(sender: str | None, server: str | None, port: int | None) -> tuple[str, str, int]:
    return (
        sender or os.getenv("SMTP_SENDER", _DEFAULT_SENDER),
        server or os.getenv("SMTP_SERVER", _DEFAULT_SERVER),
        port if port is not None else int(os.getenv("SMTP_PORT", str(_DEFAULT_PORT))),
    )


def send_mail(
    recipients: list[str],
    *,
    subject: str,
    template_name: str | None = None,
    message: str | None = None,
    sender: str | None = None,
    server: str | None = None,
    port: int | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    inputs: dict[str, object] | None = None,
) -> bool:
    """Tek public giriş. İki render modundan birini seç:

    1. `template_name` verildiyse → `templates/<name>.html` render edilir.
       `inputs` template'e geçirilecek placeholder + koşul değerleridir.
    2. Verilmezse ve `message` zaten biçimlendirilmiş HTML ise ham olarak
       gönderir (geriye uyumluluk / özel scriptler için).

    Returns True başarılı.
    """
    if not recipients:
        msg = "recipients listesi boş; mail gönderilmedi"
        raise ValueError(msg)

    if template_name is not None:
        body_html = render_template(template_name, **(inputs or {}))
    else:
        if not message or not message.strip():
            msg = "template_name veya message gerekli"
            raise ValueError(msg)
        body_html = _escape(message).replace("\n", "<br>")

    sender_addr, server_host, server_port = _resolve_smtp(sender, server, port)
    cc = cc or []
    bcc = bcc or []

    msg = _build_mime(
        sender=sender_addr,
        recipients=recipients,
        cc=cc,
        bcc=bcc,
        subject=subject,
        html_body=body_html,
    )
    smtp = smtplib.SMTP(server_host, server_port)
    try:
        smtp.sendmail(sender_addr, recipients + cc + bcc, msg.as_string())
    finally:
        smtp.close()
    print("Rapor Maili Gonderildi!!! \n\n")
    return True


__all__ = ["send_mail", "render_template"]
