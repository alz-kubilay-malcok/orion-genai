"""Mailbox — backend'in `mail_messages` tablosunu salt okunur görüntüler.

`MAIL_PROVIDER=db` modunda backend worker gönderilecek her maili bu
tabloya yazar (``delivery_status='skipped'`` = sessiz placeholder).
Aynı DB yolunu paylaştığı için `pages/4_🗄_DB_Inspect.py` ile aynı
URI mode=ro pattern'i kullanılır; API üzerinden gitmeye gerek yoktur.

Front-end (Next.js admin) için ayrı bir mailbox UI'si vardır; bu
sayfa yalnızca yerel geliştirme/QA içindir ve authentication gerektirmez.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import streamlit as st

DEFAULT_DB_PATH = Path(r"C:\projects\GenAiOrionPanel\db\orion.db")

st.set_page_config(
    page_title="Mailbox",
    page_icon="📬",
    layout="wide",
)


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)


def _row_to_record(row: sqlite3.Row) -> dict[str, object]:
    recipients = json.loads(row["recipients"]) if row["recipients"] else []
    context = json.loads(row["context"]) if row["context"] else {}
    return {
        "id": row["id"],
        "template": row["template"],
        "subject": row["subject"],
        "from_email": row["from_email"],
        "recipients": recipients,
        "context": context,
        "body_text": row["body_text"],
        "body_html": row["body_html"],
        "has_secret": bool(row["has_secret"]),
        "correlation_id": row["correlation_id"],
        "app_env": row["app_env"],
        "delivery_status": row["delivery_status"],
        "read_at": row["read_at"],
        "created_at": row["created_at"],
    }


@st.cache_data(ttl=10)
def _load_mail(db_path_str: str) -> list[dict[str, object]]:
    db_path = Path(db_path_str)
    if not db_path.exists():
        return []
    with _connect(db_path) as conn:
        try:
            cur = conn.execute(
                """
                SELECT id, template, subject, from_email, recipients,
                       context, body_text, body_html, has_secret,
                       correlation_id, app_env, delivery_status,
                       read_at, created_at
                FROM mail_messages
                ORDER BY created_at DESC
                LIMIT 200
                """
            )
            return [_row_to_record(row) for row in cur.fetchall()]
        except sqlite3.OperationalError:
            # Tablo henüz migrate edilmedi → sessizce boş liste döndür.
            return []


def main() -> None:
    st.title("📬 Mailbox (DB-backed)")
    st.caption(
        "`db/orion.db` içindeki `mail_messages` tablosu; worker tarafından "
        "yazılır, bu sayfa salt okunur bağlanır. Login gerektirmez."
    )

    db_path = Path(
        st.text_input("DB dosya yolu", value=str(DEFAULT_DB_PATH))
    )
    records = _load_mail(str(db_path))
    if not records:
        if not db_path.exists():
            st.error(f"DB dosyası yok: {db_path}")
        else:
            st.info(
                "Mail kaydı yok. Bir talep atıp worker'ı çalıştırmayı deneyin."
            )
        return

    st.success(f"{len(records)} mail yüklendi (en yeni 200)")

    col_t, col_s = st.columns([2, 3])
    with col_t:
        templates = sorted({r["template"] for r in records})
        template_choice = st.multiselect(
            "Template", templates, default=templates, key="mb_tpl"
        )
    with col_s:
        search = st.text_input(
            "Ara", placeholder="subject, recipient, ticket_id…", key="mb_search"
        )

    filtered = [
        r for r in records
        if r["template"] in template_choice
        and (
            not search.strip()
            or search.lower() in json.dumps(r, ensure_ascii=False).lower()
        )
    ]
    if not filtered:
        st.info("Filtreye uyan mail yok.")
        return

    list_col, detail_col = st.columns([2, 3])
    if "mb_idx" not in st.session_state:
        st.session_state.mb_idx = 0
    if st.session_state.mb_idx >= len(filtered):
        st.session_state.mb_idx = 0

    with list_col:
        st.markdown("##### Mailler")
        for idx, record in enumerate(filtered):
            subject = record["subject"]
            short = subject[:60] + ("…" if len(subject) > 60 else "")
            label = f"{'   ' if record['read_at'] else '🔵 '}{short}"
            if st.button(
                label,
                key=f"pick-{record['id']}",
                use_container_width=True,
                type=("primary" if st.session_state.mb_idx == idx else "secondary"),
                help=f"{record['created_at']} | {record['template']} | "
                     f"{', '.join(record['recipients']) or '-'}",
            ):
                st.session_state.mb_idx = idx

    with detail_col:
        record = filtered[st.session_state.mb_idx]
        st.subheader(record["subject"])
        meta_cols = st.columns(2)
        with meta_cols[0]:
            st.markdown(f"**Template:** `{record['template']}`")
            st.markdown(f"**From:** `{record['from_email']}`")
            rec = record["recipients"] or ["-"]
            st.markdown(f"**To:** `{'`, `'.join(rec)}`")
            st.markdown(f"**Delivery:** `{record['delivery_status']}`")
        with meta_cols[1]:
            st.markdown(f"**Created:** `{record['created_at']}`")
            st.markdown(f"**App env:** `{record['app_env']}`")
            st.markdown(f"**Correlation:** `{record['correlation_id'] or '-'}`")
            st.markdown(f"**Read at:** `{record['read_at'] or '-'}`")

        if record["has_secret"]:
            st.error(
                "Bu mailde teslim edilecek bir anahtar referansı var; gizli "
                "değer bu tabloda tutulmaz — backend log/audit'ında."
            )

        with st.expander("Context metadata", expanded=False):
            st.json(record["context"])

        st.markdown("### Body (text)")
        st.code(record["body_text"] or "", language="text")

        if record["body_html"]:
            with st.expander("Body (HTML önizleme)"):
                st.components.v1.html(
                    record["body_html"], height=520, scrolling=True
                )


if __name__ in {"__main__", "app"}:
    main()
