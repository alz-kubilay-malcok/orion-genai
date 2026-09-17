import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.src.api.auth.dependencies import get_current_superuser
from backend.src.api.routes.batch_keys import router
from backend.src.core.batch_keys.excel import (
    BatchExcelError,
    build_result_csv,
    build_template_xlsx,
    parse_batch_excel,
)
from backend.src.core.batch_keys.service import process_batch
from backend.src.core.litellm.generate_key import LiteLLMKeyError


def _xlsx(headers: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parse_excel_turkish_headers_and_defaults():
    data = _xlsx(
        ["E-posta", "Ad Soyad", "Departman"],
        [["ali.veli@allianz.com.tr", "Ali Veli", "GENAI"]],
    )
    rows = parse_batch_excel(data, model_name="allianz-text", default_environment="DEV")
    assert len(rows) == 1
    assert rows[0].email == "ali.veli@allianz.com.tr"
    assert rows[0].name == "Ali Veli"
    assert rows[0].team == "GENAI"
    assert rows[0].environment == "DEV"
    assert rows[0].key_alias == "ALZ-GENAI-ALIVELI2-DEV-ALLIANZ-TEXT"


def test_parse_excel_rejects_missing_email_column():
    data = _xlsx(["name"], [["Ali"]])
    with pytest.raises(BatchExcelError, match="email"):
        parse_batch_excel(data, model_name="allianz-text")


def test_parse_excel_rejects_bad_email():
    data = _xlsx(["email"], [["not-an-email"]])
    with pytest.raises(BatchExcelError, match="geçersiz email"):
        parse_batch_excel(data, model_name="allianz-text")


def test_template_roundtrip():
    rows = parse_batch_excel(build_template_xlsx(), model_name="allianz-text")
    assert rows[0].email == "ali.veli@allianz.com.tr"


def test_result_csv_appends_api_key_column():
    csv_bytes = build_result_csv(
        ["email", "name"],
        [["ali@allianz.com.tr", "Ali"]],
        ["sk-from-test"],
    )
    text = csv_bytes.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line]
    assert lines[0] == "email,name,api_key"
    assert lines[1] == "ali@allianz.com.tr,Ali,sk-from-test"


def test_result_csv_overwrites_existing_api_key_column():
    csv_bytes = build_result_csv(
        ["email", "api_key"],
        [["ali@allianz.com.tr", "old"]],
        ["sk-new"],
    )
    text = csv_bytes.decode("utf-8-sig")
    assert "email,api_key" in text.splitlines()[0]
    assert "sk-new" in text
    assert "old" not in text


def test_process_batch_generates_and_mails():
    from backend.src.core.batch_keys.excel import BatchRow

    row = BatchRow(
        row=2,
        email="ali@allianz.com.tr",
        name="Ali",
        key_alias="ALZ-GENAI-ALI-DEV-TEXT",
        team="GENAI",
        environment="DEV",
    )
    mailed: list[str] = []

    async def generate(**kwargs):
        assert kwargs["models"] == ["allianz-text"]
        assert kwargs["key_alias"] == row.key_alias
        assert kwargs["max_parallel_requests"] == 5
        return ("sk-live-key", "tok-1")

    def mailer(**kwargs):
        mailed.append(kwargs["recipients"][0])
        assert kwargs["inputs"]["api_key"] == "sk-live-key"
        return True

    results = asyncio.run(
        process_batch(
            [row],
            model_name="allianz-text",
            send_mail=True,
            max_parallel_requests=5,
            generate_key=generate,
            mailer=mailer,
        )
    )
    assert results[0].ok is True
    assert results[0].api_key == "sk-live-key"
    assert results[0].mailed is True
    assert mailed == ["ali@allianz.com.tr"]


def test_process_batch_continues_after_row_error():
    from backend.src.core.batch_keys.excel import BatchRow

    rows = [
        BatchRow(2, "a@allianz.com.tr", "A", "alias-a", "", "DEV"),
        BatchRow(3, "b@allianz.com.tr", "B", "alias-b", "", "DEV"),
    ]

    async def generate(**kwargs):
        if kwargs["key_alias"] == "alias-a":
            raise LiteLLMKeyError("nope", retryable=False)
        return ("sk-b", "tok-b")

    results = asyncio.run(
        process_batch(rows, model_name="m", send_mail=False, generate_key=generate)
    )
    assert results[0].ok is False
    assert results[0].error == "nope"
    assert results[1].ok is True
    assert results[1].api_key == "sk-b"


def test_process_batch_skips_mail_when_flag_false():
    from backend.src.core.batch_keys.excel import BatchRow

    row = BatchRow(2, "a@allianz.com.tr", "A", "alias-a", "", "DEV")
    called = {"mail": 0}

    async def generate(**kwargs):
        return ("sk", "id")

    def mailer(**kwargs):
        called["mail"] += 1
        return True

    results = asyncio.run(
        process_batch(
            [row],
            model_name="m",
            send_mail=False,
            generate_key=generate,
            mailer=mailer,
        )
    )
    assert results[0].mailed is False
    assert called["mail"] == 0


def _client(monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_superuser] = lambda: SimpleNamespace(
        username="admin@local",
    )
    monkeypatch.setattr(
        "backend.src.api.routes.batch_keys.resolve_litellm_http",
        lambda ortam, kind="litellm": ("http://litellm.test", "sk-master"),
    )
    return TestClient(app)


def test_batch_keys_endpoint_xlsx_and_model(monkeypatch):
    client = _client(monkeypatch)

    async def fake_process(rows, **kwargs):
        from backend.src.core.batch_keys.service import BatchRowResult

        assert kwargs["model_name"] == "allianz-text"
        assert kwargs["send_mail"] is True
        assert kwargs["max_parallel_requests"] == 5
        return [
            BatchRowResult(
                row=rows[0].row,
                email=rows[0].email,
                name=rows[0].name,
                key_alias=rows[0].key_alias,
                team=rows[0].team,
                environment=rows[0].environment,
                ok=True,
                api_key="sk-from-test",
                mailed=True,
            )
        ]

    monkeypatch.setattr("backend.src.api.routes.batch_keys.process_batch", fake_process)
    data = _xlsx(
        ["email", "name"],
        [["ali@allianz.com.tr", "Ali"]],
    )
    response = client.post(
        "/admin/batch-keys",
        data={
            "model_name": "allianz-text",
            "send_mail": "true",
            "environment": "DEV",
            "max_parallel_requests": "5",
        },
        files={
            "file": (
                "keys.xlsx",
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "orion-batch-keys.csv" in response.headers["content-disposition"]
    text = response.content.decode("utf-8-sig")
    assert "api_key" in text.splitlines()[0]
    assert "sk-from-test" in text
    assert response.headers["x-batch-succeeded"] == "1"


def test_batch_keys_rejects_non_xlsx(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/admin/batch-keys",
        data={"model_name": "allianz-text", "send_mail": "false"},
        files={"file": ("notes.csv", b"email\na@b.com\n", "text/csv")},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "XLSX_REQUIRED"


def test_batch_keys_rejects_bad_max_parallel(monkeypatch):
    client = _client(monkeypatch)
    data = _xlsx(["email"], [["ali@allianz.com.tr"]])
    response = client.post(
        "/admin/batch-keys",
        data={
            "model_name": "allianz-text",
            "max_parallel_requests": "0",
        },
        files={
            "file": (
                "keys.xlsx",
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_MAX_PARALLEL"


def test_batch_template_download(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/admin/batch-keys/template")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]


def test_parse_output_csv_requires_api_key():
    from backend.src.core.batch_keys.csv_io import parse_output_csv

    with pytest.raises(BatchExcelError, match="api_key"):
        parse_output_csv(b"email,name\nali@allianz.com.tr,Ali\n")


def test_parse_output_csv_reads_key_and_email():
    from backend.src.core.batch_keys.csv_io import parse_output_csv

    rows = parse_output_csv(
        "email,name,key_alias,api_key\n"
        "ali@allianz.com.tr,Ali,ALZ-A,sk-aaa\n".encode("utf-8-sig")
    )
    assert rows[0].email == "ali@allianz.com.tr"
    assert rows[0].api_key == "sk-aaa"
    assert rows[0].key_alias == "ALZ-A"


def test_preview_keys_counts_found_and_missing():
    from backend.src.core.batch_keys.csv_io import CsvKeyRow
    from backend.src.core.batch_keys.update import preview_keys
    from backend.src.core.litellm.generate_key import LiteLLMKeyInfo

    rows = [
        CsvKeyRow(2, "ali@allianz.com.tr", "Ali", "ALZ-A", "sk-aaa"),
        CsvKeyRow(3, "ayse@allianz.com.tr", "Ayse", "ALZ-B", "sk-bbb"),
        CsvKeyRow(4, "bos@allianz.com.tr", "", "", ""),
    ]

    async def fetch_info(*, api_key, environment):
        if api_key == "sk-aaa":
            return LiteLLMKeyInfo("ALZ-A", "GENAI", ["allianz-text"], 5, False)
        return None

    result = asyncio.run(preview_keys(rows, environment="DEV", fetch_info=fetch_info))
    assert result.csv_rows == 3
    assert result.with_api_key == 2
    assert result.found == 1
    assert result.missing == 2
    assert result.rows[0].found is True
    assert result.rows[0].team == "GENAI"


def test_update_keys_applies_form_fields():
    from backend.src.core.batch_keys.update import PreviewRow, update_keys

    seen: list[dict] = []

    async def apply(**kwargs):
        seen.append(kwargs)
        return {}

    rows = [
        PreviewRow(2, "ali@allianz.com.tr", "Ali", "sk-aaa", True, "ALZ-A"),
        PreviewRow(3, "ayse@allianz.com.tr", "Ayse", "sk-bbb", False, "ALZ-B", error="yok"),
    ]
    results = asyncio.run(
        update_keys(
            rows,
            environment="DEV",
            team="GENAI",
            max_parallel_requests=8,
            models=["allianz-text"],
            blocked=True,
            update_key=apply,
        )
    )
    assert results[0].status == "updated"
    assert results[1].status == "skipped"
    assert seen[0]["team_id"] == "GENAI"
    assert seen[0]["max_parallel_requests"] == 8
    assert seen[0]["blocked"] is True


def test_preview_endpoint(monkeypatch):
    client = _client(monkeypatch)

    async def fake_preview(rows, **kwargs):
        from backend.src.core.batch_keys.update import PreviewResult, PreviewRow

        assert kwargs["environment"] == "DEV"
        return PreviewResult(
            csv_rows=1,
            with_api_key=1,
            found=1,
            missing=0,
            rows=[
                PreviewRow(
                    row=2,
                    email=rows[0].email,
                    name=rows[0].name,
                    api_key=rows[0].api_key,
                    found=True,
                    key_alias="ALZ-A",
                    team="GENAI",
                    models=["allianz-text"],
                    max_parallel_requests=5,
                )
            ],
        )

    monkeypatch.setattr("backend.src.api.routes.batch_keys.preview_keys", fake_preview)
    response = client.post(
        "/admin/batch-keys/preview",
        data={"environment": "DEV"},
        files={"file": ("out.csv", b"email,api_key\nali@allianz.com.tr,sk-aaa\n", "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["found"] == 1
    assert body["rows"][0]["email"] == "ali@allianz.com.tr"


def test_update_endpoint(monkeypatch):
    client = _client(monkeypatch)

    async def fake_update(rows, **kwargs):
        from backend.src.core.batch_keys.csv_io import MappingRow

        assert kwargs["team"] == "GENAI"
        assert kwargs["max_parallel_requests"] == 8
        assert kwargs["models"] == ["allianz-text"]
        assert kwargs["blocked"] is True
        return [MappingRow(email=rows[0].email, key_alias=rows[0].key_alias, status="updated")]

    monkeypatch.setattr("backend.src.api.routes.batch_keys.update_keys", fake_update)
    response = client.post(
        "/admin/batch-keys/update",
        json={
            "environment": "DEV",
            "team": "GENAI",
            "max_parallel_requests": 8,
            "models": ["allianz-text"],
            "blocked": True,
            "keys": [
                {"api_key": "sk-aaa", "email": "ali@allianz.com.tr", "key_alias": "ALZ-A"},
            ],
        },
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    text = response.content.decode("utf-8-sig")
    assert "updated" in text
    assert "ali@allianz.com.tr" in text


def test_update_endpoint_requires_a_field(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/admin/batch-keys/update",
        json={
            "environment": "DEV",
            "keys": [{"api_key": "sk-aaa", "email": "ali@allianz.com.tr"}],
        },
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "NOTHING_TO_UPDATE"


def test_preview_endpoint_rejects_non_csv(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/admin/batch-keys/preview",
        data={"environment": "DEV"},
        files={
            "file": (
                "keys.xlsx",
                b"not-csv",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "CSV_REQUIRED"
