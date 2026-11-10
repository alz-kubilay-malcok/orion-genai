"""POST /admin/batch-keys — Excel ile LiteLLM key batch üretimi."""

from __future__ import annotations

import logging
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, EmailStr, Field

from backend.src.api.auth.dependencies import get_current_superuser
from backend.src.core.batch_keys import (
    BatchExcelError,
    BatchRow,
    PreviewRow,
    build_export_csv,
    build_export_xlsx,
    build_template_xlsx,
    parse_batch_csv,
    parse_batch_workbook,
    parse_output_file,
    preview_keys,
    process_batch,
    update_keys,
)
from backend.src.core.litellm.generate_key import (
    LiteLLMKeyError,
    create_litellm_team,
    fetch_litellm_teams,
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


@router.get("/litellm-teams")
async def list_litellm_teams(
    _user: Annotated[User, Depends(get_current_superuser)],
    environment: str = "DEV",
) -> JSONResponse:
    """Batch ekranı için gerçek LiteLLM team listesi (dropdown)."""
    env = (environment or "DEV").strip().upper() or "DEV"
    teams = await fetch_litellm_teams(env)
    return JSONResponse(content={"environment": env, "teams": teams})


class CreateTeamBody(BaseModel):
    environment: str = "DEV"
    team_alias: str = Field(min_length=1, max_length=128)


@router.post("/litellm-teams")
async def create_new_litellm_team(
    _user: Annotated[User, Depends(get_current_superuser)],
    body: CreateTeamBody,
) -> JSONResponse:
    """LiteLLM'de gerçek bir team oluşturur (idempotent — var olan alias reuse edilir)."""
    env = (body.environment or "DEV").strip().upper() or "DEV"
    try:
        team = await create_litellm_team(environment=env, team_alias=body.team_alias)
    except LiteLLMKeyError as exc:
        status_code = 503 if exc.retryable else 422
        return JSONResponse(
            status_code=status_code,
            content={"error_code": "LITELLM_TEAM_CREATE_FAILED", "detail": str(exc)},
        )
    return JSONResponse(content=team)


class ManualKeyBody(BaseModel):
    """Orion talebi olmadan tek LiteLLM key. ``team`` gerçek team id veya alias."""

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    environment: str = "DEV"
    model_name: str = Field(min_length=1, max_length=128)
    team: str = Field(min_length=1, max_length=128)
    key_alias: str = ""
    max_parallel_requests: int | None = Field(default=None, ge=1)
    send_mail: bool = False


@router.post("/keys")
async def create_manual_key(
    user: Annotated[User, Depends(get_current_superuser)],
    body: ManualKeyBody,
) -> JSONResponse:
    """Panelden tek key üretir. ``requests`` tablosuna yazılmaz."""
    from backend.src.core.batch_keys.excel import _default_alias

    environment = (body.environment or "DEV").strip().upper() or "DEV"
    team = body.team.strip()
    model = body.model_name.strip()
    name = body.name.strip()
    alias = (body.key_alias or "").strip() or _default_alias(
        team=team,
        name=name,
        environment=environment,
        model_name=model,
    )
    base, credential = resolve_litellm_http(environment, kind="litellm")
    if not base or not credential:
        return JSONResponse(
            status_code=503,
            content={"error_code": "LITELLM_NOT_CONFIGURED"},
        )
    logger.info(
        "manual-key start alias=%s env=%s model=%s by=%s",
        alias, environment, model, user.username,
    )
    results = await process_batch(
        [
            BatchRow(
                row=1,
                email=str(body.email),
                name=name,
                key_alias=alias,
                team=team,
                environment=environment,
            )
        ],
        model_name=model,
        send_mail=body.send_mail,
        max_parallel_requests=body.max_parallel_requests,
        auto_create_team=False,
        metadata={"source": "admin_manual_key", "actor": user.username},
    )
    item = results[0]
    if not item.ok:
        return JSONResponse(
            status_code=422,
            content={"error_code": "KEY_CREATE_FAILED", "detail": item.error},
        )
    logger.info(
        "manual-key ok alias=%s mailed=%s by=%s",
        item.key_alias, item.mailed, user.username,
    )
    return JSONResponse(
        content={
            "api_key": item.api_key,
            "key_alias": item.key_alias,
            "email": item.email,
            "name": item.name,
            "team": item.team,
            "environment": item.environment,
            "model_name": model,
            "mailed": item.mailed,
            "mail_error": item.error,
        }
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
    """Excel/CSV satırları için LiteLLM virtual key üretir; JSON döner (satır+``api_key``).

    Form: ``file`` (.xlsx veya .csv), ``model_name``, ``send_mail`` (true/false),
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
    is_xlsx = filename.endswith(".xlsx")
    is_csv = filename.endswith(".csv")
    if not is_xlsx and not is_csv:
        return JSONResponse(status_code=422, content={"error_code": "XLSX_OR_CSV_REQUIRED"})

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

    parse = parse_batch_workbook if is_xlsx else parse_batch_csv
    try:
        sheet = parse(data, model_name=model, default_environment=default_env)
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
        auto_create_team=True,
        metadata={"source": "admin_batch_keys", "actor": _user.username},
    )
    succeeded = sum(1 for item in results if item.ok)
    failed = len(results) - succeeded
    logger.info(
        "batch-keys done rows=%s succeeded=%s failed=%s by=%s",
        len(results), succeeded, failed, _user.username,
    )
    return JSONResponse(
        content={
            "environment": default_env,
            "model_name": model,
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "rows": [item.as_dict() for item in results],
        },
        headers={
            "X-Batch-Total": str(len(results)),
            "X-Batch-Succeeded": str(succeeded),
            "X-Batch-Failed": str(failed),
        },
    )


class UpdateKeyItem(BaseModel):
    api_key: str = Field(min_length=1)
    email: str = ""
    key_alias: str = ""
    # Preview'da görülen mevcut (LiteLLM'deki ham) team değeri — yalnız
    # `resolve_team_per_row=True` iken kullanılır.
    team: str = ""


class UpdateBatchBody(BaseModel):
    environment: str = "DEV"
    team: str | None = None
    max_parallel_requests: int | None = Field(default=None, ge=1)
    models: list[str] | None = None
    blocked: bool | None = None
    clear_metadata: bool | None = None
    strip_row_count: bool | None = None
    resolve_team_per_row: bool | None = None
    keys: list[UpdateKeyItem] = Field(min_length=1)


@router.post("/batch-keys/preview")
async def preview_batch_keys(
    _user: Annotated[User, Depends(get_current_superuser)],
    file: Annotated[UploadFile, File(...)],
    environment: Annotated[str, Form()] = "DEV",
) -> JSONResponse:
    """Create-output CSV veya .xlsx: `api_key` ile LiteLLM `/key/info` bakılır."""
    default_env = (environment or "DEV").strip().upper() or "DEV"
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv") and not filename.endswith(".xlsx"):
        return JSONResponse(status_code=422, content={"error_code": "CSV_OR_XLSX_REQUIRED"})
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
        rows = parse_output_file(data, filename)
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
) -> JSONResponse:
    """Preview'daki bulunan (seçilen) key'lere form alanlarını uygular; JSON döner."""
    team = (body.team or "").strip() or None
    models = [part.strip() for part in (body.models or []) if part.strip()] or None
    blocked = True if body.blocked is True else None
    clear_metadata = body.clear_metadata is True
    strip_row_count = body.strip_row_count is True
    resolve_team_per_row = body.resolve_team_per_row is True
    if (
        team is None
        and body.max_parallel_requests is None
        and models is None
        and blocked is None
        and not clear_metadata
        and not strip_row_count
        and not resolve_team_per_row
    ):
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
            team=item.team,
        )
        for index, item in enumerate(body.keys, start=1)
    ]
    logger.info(
        "batch-keys update n=%s team=%s parallel=%s models=%s blocked=%s clear_metadata=%s "
        "strip_row_count=%s resolve_team_per_row=%s by=%s",
        len(preview_rows), team, body.max_parallel_requests, models, blocked,
        clear_metadata, strip_row_count, resolve_team_per_row, _user.username,
    )
    try:
        results = await update_keys(
            preview_rows,
            environment=default_env,
            team=team,
            max_parallel_requests=body.max_parallel_requests,
            models=models,
            blocked=blocked,
            clear_metadata=clear_metadata,
            strip_row_suffix=strip_row_count,
            resolve_team_per_row=resolve_team_per_row,
        )
    except LiteLLMKeyError as exc:
        status_code = 503 if exc.retryable else 422
        return JSONResponse(
            status_code=status_code,
            content={"error_code": "LITELLM_TEAM_RESOLVE_FAILED", "detail": str(exc)},
        )
    succeeded = sum(1 for item in results if item.status == "updated")
    failed = sum(1 for item in results if item.status == "error")
    logger.info(
        "batch-keys update done rows=%s succeeded=%s failed=%s by=%s",
        len(results), succeeded, failed, _user.username,
    )
    return JSONResponse(
        content={
            "environment": default_env,
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "rows": [
                {
                    "email": item.email,
                    "key_alias": item.key_alias,
                    "team": item.team,
                    "status": item.status,
                    "error": item.error,
                }
                for item in results
            ],
        },
        headers={
            "X-Batch-Total": str(len(results)),
            "X-Batch-Succeeded": str(succeeded),
            "X-Batch-Failed": str(failed),
        },
    )


class ExportRowItem(BaseModel):
    email: str = ""
    name: str = ""
    key_alias: str = ""
    team: str = ""
    environment: str = ""
    api_key: str = ""
    status: str = ""
    error: str = ""


class ExportBatchBody(BaseModel):
    format: Literal["csv", "xlsx"] = "csv"
    filename: str = "orion-batch-keys"
    rows: list[ExportRowItem] = Field(min_length=1)


@router.post("/batch-keys/export")
async def export_batch_keys(
    _user: Annotated[User, Depends(get_current_superuser)],
    body: ExportBatchBody,
) -> Response:
    """Ekranda seçilen (checkbox'lı) satırları CSV veya Excel olarak indirir."""
    rows = [item.model_dump() for item in body.rows]
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", body.filename.strip()) or "orion-batch-keys"
    if body.format == "xlsx":
        content = build_export_xlsx(rows)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{safe_name}.xlsx"
    else:
        content = build_export_csv(rows)
        media_type = "text/csv; charset=utf-8"
        filename = f"{safe_name}.csv"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
