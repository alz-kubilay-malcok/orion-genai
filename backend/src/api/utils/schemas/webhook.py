"""Orion webhook Pydantic modelleri — tek kaynak (ORION-API.md)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

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
    kullanim_senaryosu: str | None = None
    modeller: list[str] = Field(default_factory=list)
    yanit_suresi: str | None = None
    kullanim_sikligi: str | None = None
    tahmini_gunluk_istek: int | None = None
    maksimum_es_zamanli_istek: int | None = None
    ortalama_girdi_sayfasi: float | None = None
    ortalama_cikti_sayfasi: float | None = None


class McpKeyPayload(SharedFields):
    departman_adi: str | None = None
    ortam: str | None = None
    talep_aciklamasi: str | None = None
    kullanim_amaci: str | None = None
    mcp_sunucusu: str | None = None
    araclar: list[str] = Field(default_factory=list)
    tum_araclara_erisim: bool | None = None


class McpRegistryPayload(SharedFields):
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


SCHEMA_BY_TALEP_TURU: dict[str, type[SharedFields]] = {
    "litellm_api_anahtari": LitellmKeyPayload,
    "mcp_erisim_anahtari": McpKeyPayload,
    "mcp_sunucu_kaydi": McpRegistryPayload,
}

__all__ = [
    "LitellmKeyPayload",
    "McpKeyPayload",
    "McpRegistryPayload",
    "SCHEMA_BY_TALEP_TURU",
    "SharedFields",
    "TALEP_TURU_MAPPING",
]
