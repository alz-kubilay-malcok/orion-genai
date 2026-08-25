"""Read-only request list from Postgres (backend/.env)."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime

from orion_studio._signing import DEFAULT_FRONTEND_BASE_URL, load_backend_env
from orion_studio.ui import apply_chrome, render_sidebar

apply_chrome("Talepler")

_COLUMNS = {
    "id": "id",
    "request_type": "tur",
    "status": "durum",
    "version": "ver",
    "genai_orion_panel_ticket_id": "talep_no",
    "requester_email": "eposta",
    "environment": "ortam",
    "department_name": "departman",
    "litellm_team_id": "team",
    "max_concurrent_requests": "paralel",
    "created_at": "oluşturulma",
}


def _dsn() -> str | None:
    env = load_backend_env()
    url = os.getenv("DATABASE_URL", env.get("DATABASE_URL", "")).strip()
    if url:
        return url.replace("postgresql+asyncpg://", "postgresql://")
    host = env.get("DB_HOST") or os.getenv("DB_HOST")
    name = env.get("DB_NAME") or os.getenv("DB_NAME")
    user = env.get("DB_USERNAME") or os.getenv("DB_USERNAME")
    password = env.get("DB_PASSWORD") or os.getenv("DB_PASSWORD")
    port = env.get("DB_PORT") or os.getenv("DB_PORT", "5432")
    if host and name and user:
        return f"postgresql://{user}:{password}@{host}:{port}/{name}"
    return None


def _fmt(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return value


async def _fetch_requests(dsn: str) -> list[dict[str, object]]:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        try:
            rows = await conn.fetch(
                """
                SELECT id::text, request_type, status, version,
                       genai_orion_panel_ticket_id, requester_email,
                       environment, department_name, litellm_team_id,
                       max_concurrent_requests, created_at
                FROM requests
                ORDER BY created_at DESC
                LIMIT 80
                """
            )
        except Exception:
            rows = await conn.fetch(
                """
                SELECT id::text, request_type, status, version,
                       genai_orion_panel_ticket_id, requester_email,
                       environment, department_name, created_at
                FROM requests
                ORDER BY created_at DESC
                LIMIT 80
                """
            )
    finally:
        await conn.close()
    return [{k: _fmt(v) for k, v in dict(r).items()} for r in rows]


def main() -> None:
    import streamlit as st

    render_sidebar()
    st.title("Talepler")
    st.caption("Salt okunur `requests` listesi (backend/.env Postgres).")

    frontend = os.getenv("PUBLIC_ACTION_BASE_URL", DEFAULT_FRONTEND_BASE_URL)
    origin = frontend.rsplit("/approvals", 1)[0] or "http://localhost:8058"
    st.link_button("Admin panel", f"{origin}/admin")

    dsn = _dsn()
    if not dsn:
        st.warning("DB bağlantısı yok. backend/.env içinde DB_* ayarla.")
        return

    if st.button("Yenile"):
        st.rerun()
    try:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            rows = pool.submit(asyncio.run, _fetch_requests(dsn)).result()
    except Exception as exc:
        st.error(f"Postgres okunamadı: {exc}")
        return
    if not rows:
        st.info("Kayıt yok.")
        return

    statuses = sorted({str(r.get("status") or "") for r in rows})
    picked = st.multiselect("Durum", statuses, default=statuses)
    shown = [r for r in rows if str(r.get("status") or "") in picked]
    display = [
        {_COLUMNS.get(k, k): v for k, v in row.items()}
        for row in shown
    ]
    st.dataframe(display, use_container_width=True, hide_index=True)


if __name__ in {"__main__", "app"}:
    main()
