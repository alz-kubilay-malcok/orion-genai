"""SMTP mail gönderimi — `send_mail(...)` ve `render_template(...)` iki public yüz.

İki giriş noktası:
- `send_mail(...)`                 — SMTP üzerinden gönderir.
- `render_template(name, **kw)`   — sadece HTML çıktısı üretir (test/önizleme).

Template'ler `templates/ klasöründe .html dosyasıdır; `string.Template`
ile `$identifier` placeholder çözümü + `#if key ... #else ... #end`
blok parser'ı (yalnız basit truthy/falsy test).

Receiver listesi bu modülde **çözümlenmez** — dışarıdan verilir; SMTP
sunucu/sender adresi `os.environ`'dan okunur.

Allianz dahili relay (`mailenable.allianz-tr.local:25`) ile aynı desen:
`MIMEMultipart` + HTML `MIMEText`, `COMMASPACE` / `formatdate`,
`smtplib.SMTP(host, 25)` — auth/TLS yok. Alıcı listesi hardcoded değil;
çağıran (approver seed / requester email) verir.

`MAIL_PROVIDER=placeholder` iken SMTP'ye gitmez (yerel docker).
Canlı gönderim: `MAIL_PROVIDER=smtp`.


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
import json
import logging
import os
import re
import smtplib
import uuid
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
from pathlib import Path
from string import Template

_DEFAULT_SENDER = "GenAi Key Dispatcher <genai_key_dispatcher@info.com>"
_DEFAULT_SERVER = "mailenable.allianz-tr.local"
_DEFAULT_PORT = 25
_DEFAULT_TIMEOUT = 15

# Bu dosya backend/src/core/mailing/mailer.py; templates/ kardeş klasördür.
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _mail_sink_dir() -> Path | None:
    raw = os.getenv("MAIL_SINK_DIR", "").strip()
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else (_REPO_ROOT / path)
    provider = os.getenv("MAIL_PROVIDER", "placeholder").strip().lower()
    if provider in {"placeholder", "none", "log", "jsonfile"}:
        return _REPO_ROOT / "test_env" / "mailbox"
    return None


def _write_mail_sink(
    *,
    recipients: list[str],
    subject: str,
    template_name: str | None,
    body_html: str,
    from_email: str,
) -> None:
    sink = _mail_sink_dir()
    if sink is None:
        return
    sink.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    slug = (template_name or "message").replace("/", "_")
    name = f"{stamp}_{slug}_{uuid.uuid4().hex[:8]}"
    record = {
        "id": name,
        "template": template_name or "",
        "subject": subject,
        "from_email": from_email,
        "recipients": list(recipients),
        "body_html": body_html,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "delivery_status": "skipped",
    }
    (sink / f"{name}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (sink / f"{name}.html").write_text(body_html, encoding="utf-8")

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


def _clean_addrs(addrs: list[str] | None) -> list[str]:
    """Boş / whitespace adresleri at — `['']` envelope'a gitmesin."""
    if not addrs:
        return []
    return [item.strip() for item in addrs if item and str(item).strip()]


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


def _resolve_smtp(
    sender: str | None, server: str | None, port: int | None,
) -> tuple[str, str, int, float]:
    return (
        sender or os.getenv("SMTP_SENDER", _DEFAULT_SENDER),
        server or os.getenv("SMTP_SERVER", _DEFAULT_SERVER),
        port if port is not None else int(os.getenv("SMTP_PORT", str(_DEFAULT_PORT))),
        float(os.getenv("SMTP_TIMEOUT", str(_DEFAULT_TIMEOUT))),
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
    """Tek public giriş. MAIL_PROVIDER=placeholder/jsonfile ise SMTP yok; mailbox'a yazar."""
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

    sender_addr, server_host, server_port, timeout = _resolve_smtp(sender, server, port)
    to_addrs = _clean_addrs(recipients)
    cc_addrs = _clean_addrs(cc)
    bcc_addrs = _clean_addrs(bcc)
    if not to_addrs:
        msg = "recipients listesi boş; mail gönderilmedi"
        raise ValueError(msg)

    _write_mail_sink(
        recipients=to_addrs,
        subject=subject,
        template_name=template_name,
        body_html=body_html,
        from_email=sender_addr,
    )

    provider = os.getenv("MAIL_PROVIDER", "placeholder").strip().lower()
    if provider in {"placeholder", "none", "log", "jsonfile"}:
        logging.getLogger(__name__).info(
            "mail placeholder: to=%s subject=%s", to_addrs, subject,
        )
        return True

    msg = _build_mime(
        sender=sender_addr,
        recipients=to_addrs,
        cc=cc_addrs,
        bcc=bcc_addrs,
        subject=subject,
        html_body=body_html,
    )
    smtp = smtplib.SMTP(server_host, server_port, timeout=timeout)
    try:
        smtp.sendmail(sender_addr, to_addrs + cc_addrs + bcc_addrs, msg.as_string())
    finally:
        smtp.close()
    return True


__all__ = ["send_mail", "render_template"]
