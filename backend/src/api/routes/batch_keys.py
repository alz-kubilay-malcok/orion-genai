"""POST /admin/batch-keys — Excel ile LiteLLM key batch üretimi."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from backend.src.api.auth.dependencies import get_current_superuser
from backend.src.core.batch_keys import (
    BatchExcelError,
    PreviewRow,
    build_result_csv,
    build_template_xlsx,
    build_update_result_csv,
    parse_batch_workbook,
    parse_output_csv,
    preview_keys,
    process_batch,
    update_keys,
)
from backend.src.core.litellm.target import resolve_litellm_http
from backend.src.data.db.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_TRUE = {"1", "true", "yes", "on", "evet"}


def _as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUE


def _as_optional_int(value: str) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    number = int(text)
    if number < 1:
        raise ValueError("max_parallel_requests en az 1 olmalı")
    return number


@router.get("/batch-keys/template")
async def download_batch_template(
    _user: Annotated[User, Depends(get_current_superuser)],
) -> Response:
    return Response(
        content=build_template_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="orion-batch-keys.xlsx"',
        },
    )


@router.post("/batch-keys")
async def create_batch_keys(
    _user: Annotated[User, Depends(get_current_superuser)],
    file: Annotated[UploadFile, File(...)],
    model_name: Annotated[str, Form(...)],
    send_mail: Annotated[str, Form()] = "false",
    environment: Annotated[str, Form()] = "DEV",
    max_parallel_requests: Annotated[str, Form()] = "",
) -> Response:
    """Excel satırları için LiteLLM virtual key üretir; CSV döner (`api_key` kolonu).

    Form: ``file`` (.xlsx), ``model_name``, ``send_mail`` (true/false),
    ``environment`` (satırda yoksa varsayılan, default DEV),
    ``max_parallel_requests`` (tüm satırlara, boşsa LiteLLM'e gitmez).
    """
    model = (model_name or "").strip()
    if not model:
        return JSONResponse(status_code=422, content={"error_code": "MODEL_NAME_REQUIRED"})
    default_env = (environment or "DEV").strip().upper() or "DEV"
    mail = _as_bool(send_mail)
    try:
        parallel = _as_optional_int(max_parallel_requests)
    except ValueError:
        return JSONResponse(
            status_code=422, content={"error_code": "INVALID_MAX_PARALLEL"},
        )

    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        return JSONResponse(status_code=422, content={"error_code": "XLSX_REQUIRED"})

    data = await file.read()
    if not data:
        return JSONResponse(status_code=422, content={"error_code": "EMPTY_FILE"})
    if len(data) > _MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content={"error_code": "FILE_TOO_LARGE"})

    base, credential = resolve_litellm_http(default_env, kind="litellm")
    if not base or not credential:
        return JSONResponse(
            status_code=503,
            content={"error_code": "LITELLM_NOT_CONFIGURED"},
        )

    try:
        sheet = parse_batch_workbook(
            data, model_name=model, default_environment=default_env,
        )
    except BatchExcelError as exc:
        return JSONResponse(
            status_code=422,
            content={"error_code": "INVALID_EXCEL", "detail": str(exc)},
        )

    logger.info(
        "batch-keys start rows=%s model=%s send_mail=%s parallel=%s by=%s",
        len(sheet.rows), model, mail, parallel, _user.username,
    )
    results = await process_batch(
        sheet.rows,
        model_name=model,
        send_mail=mail,
        max_parallel_requests=parallel,
        metadata={"source": "admin_batch_keys", "actor": _user.username},
    )
    csv_bytes = build_result_csv(
        sheet.headers,
        sheet.values,
        [item.api_key for item in results],
    )
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="orion-batch-keys.csv"',
            "X-Batch-Total": str(len(results)),
            "X-Batch-Succeeded": str(sum(1 for item in results if item.ok)),
            "X-Batch-Failed": str(sum(1 for item in results if not item.ok)),
        },
    )


class UpdateKeyItem(BaseModel):
    api_key: str = Field(min_length=1)
    email: str = ""
    key_alias: str = ""


class UpdateBatchBody(BaseModel):
    environment: str = "DEV"
    team: str | None = None
    max_parallel_requests: int | None = Field(default=None, ge=1)
    models: list[str] | None = None
    blocked: bool | None = None
    keys: list[UpdateKeyItem] = Field(min_length=1)


@router.post("/batch-keys/preview")
async def preview_batch_keys(
    _user: Annotated[User, Depends(get_current_superuser)],
    file: Annotated[UploadFile, File(...)],
    environment: Annotated[str, Form()] = "DEV",
) -> JSONResponse:
    """Create-output CSV: `api_key` ile LiteLLM `/key/info` bakılır."""
    default_env = (environment or "DEV").strip().upper() or "DEV"
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        return JSONResponse(status_code=422, content={"error_code": "CSV_REQUIRED"})
    data = await file.read()
    if not data:
        return JSONResponse(status_code=422, content={"error_code": "EMPTY_FILE"})
    if len(data) > _MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content={"error_code": "FILE_TOO_LARGE"})
    base, credential = resolve_litellm_http(default_env, kind="litellm")
    if not base or not credential:
        return JSONResponse(
            status_code=503,
            content={"error_code": "LITELLM_NOT_CONFIGURED"},
        )
    try:
        rows = parse_output_csv(data)
    except BatchExcelError as exc:
        return JSONResponse(
            status_code=422,
            content={"error_code": "INVALID_CSV", "detail": str(exc)},
        )
    except UnicodeDecodeError:
        return JSONResponse(
            status_code=422,
            content={"error_code": "INVALID_CSV", "detail": "CSV UTF-8 olmalı"},
        )
    result = await preview_keys(rows, environment=default_env)
    logger.info(
        "batch-keys preview rows=%s found=%s by=%s",
        result.csv_rows, result.found, _user.username,
    )
    payload = result.as_dict()
    payload["environment"] = default_env
    return JSONResponse(content=payload)


@router.post("/batch-keys/update")
async def update_batch_keys(
    _user: Annotated[User, Depends(get_current_superuser)],
    body: UpdateBatchBody,
) -> Response:
    """Preview'daki bulunan key'lere form alanlarını uygular; CSV döner."""
    team = (body.team or "").strip() or None
    models = [part.strip() for part in (body.models or []) if part.strip()] or None
    blocked = True if body.blocked is True else None
    if team is None and body.max_parallel_requests is None and models is None and blocked is None:
        return JSONResponse(status_code=422, content={"error_code": "NOTHING_TO_UPDATE"})
    default_env = (body.environment or "DEV").strip().upper() or "DEV"
    base, credential = resolve_litellm_http(default_env, kind="litellm")
    if not base or not credential:
        return JSONResponse(
            status_code=503,
            content={"error_code": "LITELLM_NOT_CONFIGURED"},
        )
    preview_rows = [
        PreviewRow(
            row=index,
            email=item.email,
            name="",
            api_key=item.api_key,
            found=True,
            key_alias=item.key_alias,
        )
        for index, item in enumerate(body.keys, start=1)
    ]
    logger.info(
        "batch-keys update n=%s team=%s parallel=%s models=%s blocked=%s by=%s",
        len(preview_rows), team, body.max_parallel_requests, models, blocked, _user.username,
    )
    results = await update_keys(
        preview_rows,
        environment=default_env,
        team=team,
        max_parallel_requests=body.max_parallel_requests,
        models=models,
        blocked=blocked,
    )
    csv_bytes = build_update_result_csv(results)
    succeeded = sum(1 for item in results if item.status == "updated")
    failed = sum(1 for item in results if item.status == "error")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="orion-batch-keys-update.csv"',
            "X-Batch-Total": str(len(results)),
            "X-Batch-Succeeded": str(succeeded),
            "X-Batch-Failed": str(failed),
        },
    )
