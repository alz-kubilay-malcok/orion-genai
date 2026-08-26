"""Orion payload → ``requests`` ORM kolonları."""

from __future__ import annotations

import json
from typing import Any

from backend.src.api.utils.schemas.webhook import SharedFields, TALEP_TURU_MAPPING

_TURKISH_TO_SNAKE: dict[str, str] = {
    "departman_adi": "department_name",
    "ortam": "environment",
    "talep_aciklamasi": "request_description",
    "kullanim_amaci": "purpose_text",
    "kullanim_senaryosu": "use_case",
    "modeller": "models",
    "yanit_suresi": "response_window",
    "kullanim_sikligi": "usage_frequency",
    "tahmini_gunluk_istek": "estimated_daily_requests",
    "maksimum_es_zamanli_istek": "max_concurrent_requests",
    "ortalama_girdi_sayfasi": "input_pages",
    "ortalama_cikti_sayfasi": "output_pages",
    "mcp_sunucusu": "mcp_server_slug",
    "araclar": "mcp_tool_names",
    "tum_araclara_erisim": "all_tools",
    "mcp_sunucu_adi": "mcp_server_display_name",
    "mcp_sunucusu_goruntulu_ad": "mcp_server_display_name",
    "proje_adi": "project_name",
    "teknik_sorumlu_eposta": "technical_owner_email",
    "repo_platformu": "repo_platform",
    "repo_url": "repo_url",
    "devops_jira_no": "devops_jira_key",
    "devops_jira_anahtari": "devops_jira_key",
    "mcp_endpoint_url": "mcp_endpoint_url",
    "minimum_evaluation_skoru": "minimum_evaluation_score",
    "minimum_degerlendirme_skoru": "minimum_evaluation_score",
    "ek_notlar": "additional_notes",
}

_SHARED_WIRE_KEYS = {
    "talep_turu", "talep_no", "talep_url", "talep_eden_adi",
    "talep_eden_eposta", "olusturulma_tarihi",
}

_RESERVED_ORM = {
    "request_type", "status", "version",
    "genai_orion_panel_ticket_id",
    "genai_orion_panel_ticket_url",
    "requester_name", "requester_email",
    "genai_orion_panel_created_at",
    "raw_genai_orion_panel_payload",
}


def resolve_request_type(talep_turu: str) -> str:
    if talep_turu not in TALEP_TURU_MAPPING:
        msg = f"unsupported talep_turu: {talep_turu!r}"
        raise ValueError(msg)
    return TALEP_TURU_MAPPING[talep_turu]


def payload_to_request_fields(
    payload: SharedFields, request_type: str, raw: dict[str, Any],
) -> dict[str, Any]:
    """Pydantic payload → ORM ``requests`` satır field'ları."""
    fields: dict[str, Any] = {
        "request_type": request_type,
        "status": "waiting_approval",
        "version": 0,
        "genai_orion_panel_ticket_id": payload.talep_no,
        "genai_orion_panel_ticket_url": str(payload.talep_url),
        "requester_name": payload.talep_eden_adi,
        "requester_email": payload.talep_eden_eposta,
        "genai_orion_panel_created_at": payload.olusturulma_tarihi,
        "raw_genai_orion_panel_payload": json.dumps(
            raw, ensure_ascii=False, default=str,
        ),
    }
    for k, v in payload.model_dump(mode="json").items():
        if k in _SHARED_WIRE_KEYS:
            continue
        snakecase = _TURKISH_TO_SNAKE.get(k, k)
        if snakecase in _RESERVED_ORM:
            continue
        fields[snakecase] = v
    if request_type == "litellm_key":
        purpose = payload.model_dump().get("kullanim_amaci")
        if purpose:
            fields["purpose_code"] = purpose
        input_pages = float(fields.get("input_pages") or 0)
        output_pages = float(fields.get("output_pages") or 0)
        tokens = max(int((input_pages + output_pages) * 1000), 1000)
        fields["estimated_tokens_per_request"] = tokens
        if (fields.get("department_name") or "").strip():
            fields["litellm_team_id"] = str(fields["department_name"]).strip()
    if request_type in {"litellm_key", "mcp_key"}:
        from backend.src.core.naming import key_alias_for_request

        fields["key_alias"] = key_alias_for_request(fields, request_type)
    return fields


__all__ = ["payload_to_request_fields", "resolve_request_type"]
