"""Admin action POST payload'ları (Bölüm 10.3).

- Approve: token + request_version (litellm_key ve mcp_key 'de ek olarak yalnız mcp_registry `allows_all_tools`)
- Revise  : yalnız litellm_key; LiteLLM team_id + max_parallel_requests.
- Reject  : tüm automated tipler; reject_reason 1..2000 char.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class PostApproveBody(BaseModel):
    """Approve POST gövdesi — ortak alanlar."""

    model_config = ConfigDict(extra="forbid")

    # Token query'den değil gövdeden de gelebilir; burada payload tarafı.
    token: str
    request_version: int = Field(ge=0)
    # mcp_server_registry için admin decision (default false).
    allows_all_tools: bool | None = None


class PostReviseBody(BaseModel):
    """LiteLLM-only Revise POST gövdesi.

    `team_id` LiteLLM `/key/generate` team_id (alias da kabul; worker
    `GET /team/list` ile çözer). `max_parallel_requests` eşzamanlı istek
    tavanıdır. Client-facing üç alan opsiyoneldir.
    """

    model_config = ConfigDict(extra="forbid")

    token: str
    request_version: int = Field(ge=0)
    team_id: Annotated[str, Field(min_length=1, max_length=128)]
    max_parallel_requests: int = Field(ge=1)
    admin_note: Annotated[str | None, Field(default=None, max_length=2000)] = None
    models: Annotated[list[str] | None, Field(default=None)] = None
    response_window: Annotated[str | None, Field(default=None, max_length=64)] = None
    usage_frequency: Annotated[str | None, Field(default=None, max_length=64)] = None


class PostRejectBody(BaseModel):
    """Tüm automated tipler için ortak Reject POST gövdesi."""

    model_config = ConfigDict(extra="forbid")

    token: str
    request_version: int = Field(ge=0)
    reject_reason: Annotated[str, Field(min_length=1, max_length=2000)]


class ApprovalViewModel(BaseModel):
    """`GET /actions/{token}/view` JSON yanıtı — viewer-only frontend için (read-only, side-effect yok)."""

    model_config = ConfigDict(extra="forbid")

    action: str
    request_id: str
    request_type: str
    status: str
    request_version: int
    genai_orion_panel_ticket_id: str
    genai_orion_panel_ticket_url: str
    requester_name: str
    requester_email: str
    environment: str
    created_at: datetime
    detail: dict[str, Any]
    litellm_teams: list[dict[str, str]] = Field(default_factory=list)
