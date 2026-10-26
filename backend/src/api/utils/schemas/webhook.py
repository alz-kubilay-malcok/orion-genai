"""Orion webhook Pydantic modelleri — tek kaynak (ORION-API.md)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator, model_validator

from backend.src.core.mcp_scopes import McpScope, normalize_scopes

TALEP_TURU_MAPPING: dict[str, str] = {
    "litellm_api_anahtari": "litellm_key",
    "mcp_erisim_anahtari": "mcp_key",
    "mcp_sunucu_kaydi": "mcp_server_registry",
}


class SharedFields(BaseModel):
    """Tüm tipler için ortak alanlar — `extra='forbid'` ile sıkı doğrula."""

    model_config = ConfigDict(extra="forbid")

    talep_turu: str = Field(min_length=1, max_length=64)
    talep_no: str = Field(min_length=1, max_length=64)
    talep_url: HttpUrl
    talep_eden_adi: str = Field(min_length=1, max_length=200)
    talep_eden_eposta: EmailStr
    olusturulma_tarihi: datetime


class LitellmKeyPayload(SharedFields):
    departman_adi: str | None = None
    ortam: str | None = None
    talep_aciklamasi: str | None = None
    kullanim_amaci: str | None = None
    proje_adi: str | None = None
    kullanim_senaryosu: str | None = None
    modeller: list[str] = Field(default_factory=list)
    yanit_suresi: str | None = None
    kullanim_sikligi: str | None = None
    tahmini_gunluk_istek: int | None = None
    maksimum_es_zamanli_istek: int | None = None
    ortalama_girdi_sayfasi: float | None = None
    ortalama_cikti_sayfasi: float | None = None


class McpErisim(BaseModel):
    """Tek sunucu kapsamı — ``erisimler`` dizisi öğesi."""

    model_config = ConfigDict(extra="ignore")

    mcp_sunucusu: str = Field(min_length=1, max_length=200)
    araclar: list[str] = Field(default_factory=list)
    tum_araclara_erisim: bool = False


class McpKeyPayload(SharedFields):
    model_config = ConfigDict(extra="ignore")

    departman_adi: str | None = None
    ortam: str | None = None
    talep_aciklamasi: str | None = None
    kullanim_amaci: str | None = None
    proje_adi: str | None = None
    mcp_sunucusu: str | list[str] | None = None
    araclar: list[str] | dict[str, list[str]] = Field(default_factory=list)
    tum_araclara_erisim: bool | dict[str, bool] | None = None
    erisimler: list[McpErisim] | None = None

    @model_validator(mode="after")
    def _mcp_scopes_valid(self) -> McpKeyPayload:
        normalize_scopes(
            mcp_sunucusu=self.mcp_sunucusu,
            araclar=self.araclar,
            tum_araclara_erisim=self.tum_araclara_erisim,
            erisimler=(
                [row.model_dump() for row in self.erisimler]
                if self.erisimler is not None
                else None
            ),
        )
        return self

    def mcp_scopes(self) -> list[McpScope]:
        return normalize_scopes(
            mcp_sunucusu=self.mcp_sunucusu,
            araclar=self.araclar,
            tum_araclara_erisim=self.tum_araclara_erisim,
            erisimler=(
                [row.model_dump() for row in self.erisimler]
                if self.erisimler is not None
                else None
            ),
        )


class McpRegistryPayload(SharedFields):
    model_config = ConfigDict(extra="ignore")

    departman_adi: str | None = None
    ortam: str | None = None
    talep_aciklamasi: str | None = None
    kullanim_amaci: str | None = None
    mcp_sunucu_adi: str | None = None
    mcp_sunucusu_goruntulu_ad: str | None = None
    proje_adi: str | None = None
    teknik_sorumlu_eposta: EmailStr | None = None
    repo_platformu: str | None = None
    repo_url: HttpUrl | None = None
    devops_jira_no: str | None = None
    devops_jira_anahtari: str | None = None
    mcp_endpoint_url: HttpUrl | None = None
    minimum_evaluation_skoru: int | None = None
    minimum_degerlendirme_skoru: int | None = None
    ek_notlar: str | None = None

    @field_validator(
        "repo_url", "mcp_endpoint_url", "teknik_sorumlu_eposta",
        "repo_platformu", "ortam",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


SCHEMA_BY_TALEP_TURU: dict[str, type[SharedFields]] = {
    "litellm_api_anahtari": LitellmKeyPayload,
    "mcp_erisim_anahtari": McpKeyPayload,
    "mcp_sunucu_kaydi": McpRegistryPayload,
}

__all__ = [
    "LitellmKeyPayload",
    "McpErisim",
    "McpKeyPayload",
    "McpRegistryPayload",
    "SCHEMA_BY_TALEP_TURU",
    "SharedFields",
    "TALEP_TURU_MAPPING",
]
