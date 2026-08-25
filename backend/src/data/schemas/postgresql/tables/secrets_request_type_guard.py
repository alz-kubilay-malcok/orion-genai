"""`assert_secret_request_type` trigger — secrets yalnız key requestleri için."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE OR REPLACE FUNCTION assert_secret_request_type()
RETURNS TRIGGER AS $$
DECLARE
    req_type request_type;
BEGIN
    SELECT request_type INTO req_type FROM requests WHERE id = NEW.request_id;
    IF req_type NOT IN ('litellm_key', 'mcp_key') THEN
        RAISE EXCEPTION 'secrets yalnız litellm_key/mcp_key request_type için oluşturulabilir';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS secrets_request_type_guard ON secrets;
CREATE TRIGGER secrets_request_type_guard
    BEFORE INSERT OR UPDATE ON secrets
    FOR EACH ROW EXECUTE FUNCTION assert_secret_request_type();
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


secrets_guard_migration = Migration(version=13, name="secrets_request_type_guard", apply=apply)
