"""Smoke test for `backend.data.scripts.flyway` (SQLite path).

Senaryolar:
1. Boş sqlite dosyası → tüm 11 migration uygulanır, plan snapshot dolu.
2. İkinci çağrı → boş liste (idempotent), schema bozulmaz.
3. Manuel tablo sil → sadece eksik olanlar tekrar uygulanır.

Çalıştır:
    $env:PYTHONPATH='c:\\projects\\GenAiOrionPanel\\backend\\src'
    py test_env/__tmp_flyway_check.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from data.scripts import flyway_init, flyway_status  # noqa: E402

EXPECTED = [
    "requests", "config_approvers", "worker_heartbeats",
    "config_mcp_servers", "config_mcp_tools",
    "approval_tokens", "secrets", "audit_events",
    "outbox_jobs", "mail_messages", "request_revisions",
]


def _all_tables(path: Path) -> set[str]:
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        con.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "panel.db"
        url = f"sqlite:///{db}"

        print(f"[scenario 1] fresh db at {db}")
        applied = flyway_init(url)
        assert applied == EXPECTED, f"beklenen={EXPECTED}, alınan={applied}"
        print(f"  ✓ applied [{len(applied)}]: {applied}")

        tables = _all_tables(db)
        assert tables == set(EXPECTED) | {"_schema_history"}, tables
        print(f"  ✓ all {len(tables)} tables present (incl. _schema_history)")

        print("[scenario 2] idempotent second call")
        applied2 = flyway_init(url)
        assert applied2 == [], f"ikinci çağrıdan beklenen boş, gelen: {applied2}"
        print("  ✓ no-op on second apply")

        print("[scenario 3] drop one table → re-run → only that one")
        con = sqlite3.connect(db)
        con.execute("DROP TABLE mail_messages")
        con.commit()
        con.close()
        # Mail_messages'i doldurmak için OUT FK zinciri kontrolü:
        # `mail_messages.request_id` → requests(id), o ayakta. DDL `IF NOT
        # EXISTS` ile idempotent, ama sadece eksik tablo için re-apply.
        applied3 = flyway_init(url)
        assert applied3 == ["mail_messages"], applied3
        print(f"  ✓ re-applied: {applied3}")

        print("[scenario 4] flyway_status snapshot")
        snap = flyway_status(url)
        assert snap["dialect"] == "sqlite"
        assert snap["expected_names"] == EXPECTED
        assert snap["expected_versions"] == [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        print(f"  ✓ snapshot dialect={snap['dialect']}, expected_versions={snap['expected_versions']}")

    print("\nPASS — flyway SQLite path: 4/4 scenarios")


if __name__ == "__main__":
    main()
