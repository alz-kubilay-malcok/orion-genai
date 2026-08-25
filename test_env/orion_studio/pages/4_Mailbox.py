"""Local mailbox — rendered HTML + clickable action links."""

from __future__ import annotations

import json
import re
from pathlib import Path

from orion_studio._signing import REPO_ROOT, load_backend_env
from orion_studio.ui import apply_chrome, render_sidebar

apply_chrome("Mailbox")

_LINK_RE = re.compile(
    r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_ACTION_ORDER = ("Onayla", "Revize et", "Reddet")


def _sink_dir() -> Path:
    env = load_backend_env()
    raw = env.get("MAIL_SINK_DIR", "").strip()
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else (REPO_ROOT / path)
    return REPO_ROOT / "test_env" / "mailbox"


def _load_mails(sink: Path) -> list[dict[str, object]]:
    if not sink.is_dir():
        return []
    rows: list[dict[str, object]] = []
    for path in sorted(sink.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        data["_path"] = str(path)
        rows.append(data)
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def _plain_label(raw: str) -> str:
    return " ".join(_TAG_RE.sub("", raw).split())


def _action_links(html: str) -> list[tuple[str, str]]:
    found = [
        (href, _plain_label(label) or href)
        for href, label in _LINK_RE.findall(html)
        if href.startswith("http")
    ]
    ranked: list[tuple[str, str]] = []
    used: set[str] = set()
    for wanted in _ACTION_ORDER:
        for href, label in found:
            if href in used:
                continue
            if label.lower() == wanted.lower() or wanted.lower() in label.lower():
                ranked.append((href, wanted if wanted.lower() in label.lower() else label))
                used.add(href)
                break
    for href, label in found:
        if href not in used:
            ranked.append((href, label))
            used.add(href)
    return ranked


def _mail_label(record: dict[str, object]) -> str:
    created = str(record.get("created_at") or "")[:19].replace("T", " ")
    template = str(record.get("template") or "")
    subject = str(record.get("subject") or "")
    return f"{created}  |  {template}  |  {subject}"


def main() -> None:
    import streamlit as st
    import streamlit.components.v1 as components

    render_sidebar()
    st.title("Mailbox")
    st.caption(
        "Worker MAIL_PROVIDER=placeholder iken HTML buraya yazılır. "
        "Aksiyonlar frontend onay sayfasına gider."
    )

    sink = _sink_dir()
    head_l, head_r = st.columns([4, 1])
    head_l.caption(str(sink))
    if head_r.button("Yenile", use_container_width=True):
        st.rerun()

    mails = _load_mails(sink)
    if not mails:
        st.info("Mail yok. Bir talep gönderip worker’ın çalıştığını kontrol et.")
        return

    list_col, preview_col = st.columns([1, 2], gap="large")
    with list_col:
        st.subheader("Gelen")
        labels = [_mail_label(m) for m in mails]
        choice = st.selectbox(
            "Mail",
            labels,
            index=0,
            label_visibility="collapsed",
        )
        record = mails[labels.index(choice)]
        rec = record.get("recipients") or []
        st.markdown(f"**Konu**  \n{record.get('subject', '')}")
        st.markdown(f"**Şablon**  \n`{record.get('template', '')}`")
        st.markdown(
            "**Kime**  \n"
            + (", ".join(str(x) for x in rec) if rec else "-")
        )
        st.caption(f"{record.get('from_email', '')} · {record.get('delivery_status', '')}")

    html = str(record.get("body_html") or "")
    with preview_col:
        links = _action_links(html)
        if links:
            st.subheader("Aksiyonlar")
            cols = st.columns(len(links) if len(links) <= 4 else 4)
            for idx, (href, label) in enumerate(links):
                cols[idx % len(cols)].link_button(label, href, use_container_width=True)
        st.subheader("Önizleme")
        if html:
            components.html(html, height=720, scrolling=True)
        else:
            st.warning("HTML gövde yok.")


if __name__ in {"__main__", "app"}:
    main()
