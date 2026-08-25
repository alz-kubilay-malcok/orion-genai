"""Read-only SQLite dashboard (no writes).

Uses stdlib `sqlite3` in URI read-only mode. Refreshes on each click.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="DB Inspect",
    page_icon="🗄",
    layout="wide",
)

DEFAULT_DB_PATH = Path(r"C:\projects\GenAiOrionPanel\db\orion.db")


def _connect(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return [row["name"] for row in cur.fetchall()]


def _row_counts(conn: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for tbl in tables:
        try:
            out[tbl] = conn.execute(f'SELECT COUNT(*) AS n FROM "{tbl}"').fetchone()["n"]
        except sqlite3.DatabaseError as exc:  # noqa: BLE001
            out[tbl] = -1
            st.warning(f"{tbl}: {exc!s}")
    return out


def main() -> None:
    st.title("🗄 DB Inspect — `db/orion.db`")
    st.caption(
        "Salt okunur görüntüleme; webhook'ları göndermek için sol menüdeki form sayfalarını kullanın. "
        "Bu sayfa yalnızca test ortamı için tasarlanmıştır; üretimde kullanılmaz."
    )
    db_path = Path(
        st.text_input("DB dosya yolu", value=str(DEFAULT_DB_PATH))
    )

    if not db_path.exists():
        st.error(f"DB dosyası yok: {db_path}")
        return

    try:
        conn = _connect(db_path)
    except sqlite3.DatabaseError as exc:  # noqa: BLE001
        st.error(f"DB açılamadı: {exc!s}")
        return

    try:
        tables = _list_tables(conn)
        counts = _row_counts(conn, tables)
        st.subheader("Tablo satır sayıları")
        st.json(counts)

        # Backend migration tabloları `requests` (Postgres modelleriyle aynı isim).
        # Bu sayfa tarihsel olarak `genai_orion_panel_request` arıyordu; hâlâ böyle
        # bir tablo yoksa kullanıcıya migrate çalıştırması gerektiğini söyle.
        if "requests" not in tables:
            st.warning(
                "`requests` tablosu yok. Backend kökünde `alembic upgrade head` "
                "çalıştırıp tekrar deneyin."
            )
            return

        cur = conn.execute(
            """
            SELECT
                id,
                request_type,
                environment,
                status,
                genai_orion_panel_ticket_id,
                requester_email,
                created_at,
                updated_at
            FROM requests
            ORDER BY id DESC
            LIMIT 50
            """
        )
        rows = cur.fetchall()
        st.subheader(f"Son {len(rows)} talep")
        st.dataframe(rows, use_container_width=True)

        if rows:
            ids = [row["id"] for row in rows]
            selected_id = st.selectbox("Detay için talep seçin", ids)
            detail_row = conn.execute(
                "SELECT * FROM requests WHERE id = ?",
                (selected_id,),
            ).fetchone()
            if detail_row is None:
                st.info("Talep bulunamadı.")
                return
            keys = detail_row.keys()
            detail = {key: detail_row[key] for key in keys}
            # Raw payload is JSON-typed (migration: raw_genai_orion_panel_payload)
            payload_keys = (
                "raw_genai_orion_panel_payload",
                "raw_payload",
            )
            for key in payload_keys:
                if key in detail and isinstance(detail[key], (str, bytes, bytearray)):
                    try:
                        detail[key] = json.loads(detail[key])
                    except (TypeError, ValueError):
                        pass
            st.json(detail)
    finally:
        conn.close()
    if st.button("Yenile"):
        st.rerun()


if __name__ in {"__main__", "app"}:
    main()
