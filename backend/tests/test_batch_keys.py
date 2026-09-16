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
        max_parallel_requests=None,
    )
    mailed: list[str] = []

    async def generate(**kwargs):
        assert kwargs["models"] == ["allianz-text"]
        assert kwargs["key_alias"] == row.key_alias
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
        BatchRow(2, "a@allianz.com.tr", "A", "alias-a", "", "DEV", None),
        BatchRow(3, "b@allianz.com.tr", "B", "alias-b", "", "DEV", None),
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

    row = BatchRow(2, "a@allianz.com.tr", "A", "alias-a", "", "DEV", None)
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


def test_batch_template_download(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/admin/batch-keys/template")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
