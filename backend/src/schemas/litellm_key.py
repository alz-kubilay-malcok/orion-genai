"""LiteLLM key inbound payload (Bölüm 5.2)."""

from __future__ import annotations

from typing import Annotated

from pydantic import ConfigDict, Field, field_validator

from backend.src.schemas.genai_orion_panel_webhook import SharedGenAiOrionPanelFields

# Closed allowlists (Bölüm 5.2).
MODELS: tuple[str, ...] = (
    "allianz-text",
    "allianz-vision",
    "allianz-text-small",
    "allianz-coder",
    "text2test",
)
RESPONSE_WINDOWS: tuple[str, ...] = ("realtime", "within_1h", "by_17", "by_next_08")
USAGE_FREQUENCIES: tuple[str, ...] = ("0_10", "10_100", "100_1000", "1000_10k")
PURPOSE_CODES: tuple[str, ...] = ("RAG", "CHAT", "AGENT", "DIGERI")
ENVIRONMENTS: tuple[str, ...] = ("DEV", "STG", "PROD")  # sadece LiteLLM
PAGE_INPUT_ALLOWED: tuple[float, ...] = (1.0, 3.0, 5.0, 10.0)
PAGE_OUTPUT_ALLOWED: tuple[float, ...] = (0.5, 1.0, 3.0)


class LiteLLMKeyPayload(SharedGenAiOrionPanelFields):
    """`talep_turu = litellm_api_anahtari` için flat payload."""

    model_config = ConfigDict(extra="forbid")

    departman_adi: Annotated[str, Field(min_length=1, max_length=200)]
    ortam: str
    talep_aciklamasi: Annotated[str, Field(min_length=1, max_length=4000)]
    kullanim_amaci: str
    kullanim_senaryosu: Annotated[str, Field(min_length=1, max_length=4000)]
    modeller: list[str] = Field(min_length=1)
    yanit_suresi: str
    kullanim_sikligi: str
    tahmini_gunluk_istek: int | None = Field(default=None, gt=0)
    maksimum_es_zamanli_istek: int = Field(ge=1)
    ortalama_girdi_sayfasi: float
    ortalama_cikti_sayfasi: float

    @field_validator("modeller")
    @classmethod
    def _validate_models(cls, values: list[str]) -> list[str]:
        unique = list(dict.fromkeys(values))
        unknown = [m for m in unique if m not in MODELS]
        if unknown:
            msg = f"unsupported models: {unknown}"
            raise ValueError(msg)
        if not unique:
            msg = "modeller boş olamaz"
            raise ValueError(msg)
        return unique

    @field_validator("ortam")
    @classmethod
    def _env(cls, v: str) -> str:
        if v not in ENVIRONMENTS:
            msg = f"ortam must be one of {ENVIRONMENTS}"
            raise ValueError(msg)
        return v

    @field_validator("yanit_suresi")
    @classmethod
    def _response_window(cls, v: str) -> str:
        if v not in RESPONSE_WINDOWS:
            msg = f"yanit_suresi must be one of {RESPONSE_WINDOWS}"
            raise ValueError(msg)
        return v

    @field_validator("kullanim_sikligi")
    @classmethod
    def _usage_freq(cls, v: str) -> str:
        if v not in USAGE_FREQUENCIES:
            msg = f"kullanim_sikligi must be one of {USAGE_FREQUENCIES}"
            raise ValueError(msg)
        return v

    @field_validator("kullanim_amaci")
    @classmethod
    def _purpose(cls, v: str) -> str:
        if v not in PURPOSE_CODES:
            msg = f"kullanim_amaci must be one of {PURPOSE_CODES}"
            raise ValueError(msg)
        return v

    @field_validator("ortalama_girdi_sayfasi", "ortalama_cikti_sayfasi")
    @classmethod
    def _page_count(cls, v: float, info) -> float:
        allow = (
            PAGE_INPUT_ALLOWED
            if info.field_name == "ortalama_girdi_sayfasi"
            else PAGE_OUTPUT_ALLOWED
        )
        rounded = round(float(v), 2)
        if rounded not in allow:
            msg = (
                f"{info.field_name} must be one of {allow} (contract enum); got={rounded}"
            )
            raise ValueError(msg)
        return rounded
