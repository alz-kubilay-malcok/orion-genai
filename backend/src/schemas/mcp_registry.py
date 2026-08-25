"""MCP server registry inbound payload (Bölüm 5.4)."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import ConfigDict, EmailStr, Field, HttpUrl, field_validator, model_validator

from backend.src.schemas.genai_orion_panel_webhook import SharedGenAiOrionPanelFields

ENVIRONMENTS: tuple[str, ...] = ("TEST", "PROD")
REPO_PLATFORMS: tuple[str, ...] = ("GITHUB", "BITBUCKET")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
JIRA_PATTERN = re.compile(r"^[A-Z][A-Z0-9]+-[1-9][0-9]*$")


class MCPRegistryPayload(SharedGenAiOrionPanelFields):
    """`talep_turu = mcp_sunucu_kaydi` için flat payload."""

    model_config = ConfigDict(extra="forbid")

    departman_adi: Annotated[str, Field(min_length=1, max_length=200)]
    mcp_sunucu_adi: Annotated[str, Field(min_length=1, max_length=200)]
    proje_adi: str
    teknik_sorumlu_eposta: EmailStr
    kullanim_amaci: Annotated[str, Field(min_length=1, max_length=4000)]
    repo_platformu: str
    repo_url: HttpUrl
    devops_jira_no: str | None = None
    ortam: str
    mcp_endpoint_url: HttpUrl
    minimum_evaluation_skoru: int | None = None
    ek_notlar: str | None = Field(default=None, max_length=4000)

    @field_validator("proje_adi")
    @classmethod
    def _slug_source(cls, v: str) -> str:
        slug = v.strip().lower()
        if not SLUG_PATTERN.match(slug):
            msg = f"proje_adi slug pattern'a uymuyor: {slug!r}"
            raise ValueError(msg)
        return slug

    @field_validator("repo_platformu")
    @classmethod
    def _platform(cls, v: str) -> str:
        if v not in REPO_PLATFORMS:
            msg = f"repo_platformu must be one of {REPO_PLATFORMS}"
            raise ValueError(msg)
        return v

    @field_validator("ortam")
    @classmethod
    def _env(cls, v: str) -> str:
        if v not in ENVIRONMENTS:
            msg = f"ortam must be one of {ENVIRONMENTS}; STG MCP için geçerli değildir"
            raise ValueError(msg)
        return v

    @field_validator("devops_jira_no")
    @classmethod
    def _jira(cls, v: str | None) -> str | None:
        if v is None:
            return None
        jira = v.strip().upper()
        if not JIRA_PATTERN.match(jira):
            msg = f"devops_jira_no pattern'a uymuyor: {jira!r}"
            raise ValueError(msg)
        return jira

    @model_validator(mode="after")
    def _canonical_endpoint(self) -> "MCPRegistryPayload":
        """Endpoint URL byte-for-byte canonical olmalı ve `ortam=PROD` için
        `minimum_evaluation_skoru` zorunlu + en az 90 olmalı (Bölüm 5.4)."""
        if self.ortam == "TEST":
            expected = f"https://test-mcp.allianz-tr.local/{self.proje_adi}/mcp"
        else:
            expected = f"https://mcp.allianz-tr.local/{self.proje_adi}/mcp"
        if str(self.mcp_endpoint_url).rstrip("/") != expected:
            msg = f"endpoint canonical değil: expected={expected}"
            raise ValueError(msg)

        if self.ortam == "PROD":
            skor = self.minimum_evaluation_skoru
            if skor is None:
                msg = "ortam=PROD için minimum_evaluation_skoru zorunludur"
                raise ValueError(msg)
            if skor < 90:
                msg = f"ortam=PROD için minimum_evaluation_skoru en az 90 olmalı: got={skor}"
                raise ValueError(msg)
        return self
