"""MCP access key inbound payload (Bölüm 5.3)."""

from __future__ import annotations

from typing import Annotated

from pydantic import ConfigDict, Field, model_validator

from backend.src.schemas.genai_orion_panel_webhook import SharedGenAiOrionPanelFields

ENVIRONMENTS: tuple[str, ...] = ("TEST", "STG", "PROD")


class MCPKeyPayload(SharedGenAiOrionPanelFields):
    """`talep_turu = mcp_erisim_anahtari` için flat payload."""

    model_config = ConfigDict(extra="forbid")

    departman_adi: Annotated[str, Field(min_length=1, max_length=200)]
    ortam: str
    talep_aciklamasi: Annotated[str, Field(min_length=1, max_length=4000)]
    kullanim_amaci: Annotated[str, Field(min_length=1, max_length=4000)]
    mcp_sunucusu: Annotated[str, Field(min_length=1, max_length=128)]
    araclar: list[str] = Field(default_factory=list)
    tum_araclara_erisim: bool = False

    @model_validator(mode="after")
    def _check_basic_all_tools(self) -> "MCPKeyPayload":
        if self.tum_araclara_erisim and self.araclar:
            msg = "tum_araclara_erisim=true ise araclar boş olmalıdır"
            raise ValueError(msg)
        if not self.tum_araclara_erisim and not self.araclar:
            msg = "tum_araclara_erisim=false iken en az bir araç seçilmelidir"
            raise ValueError(msg)
        # Duplicate olmayan, normalize edilmiş list.
        unique: list[str] = list(dict.fromkeys(self.araclar))
        if self.araclar != unique:
            object.__setattr__(self, "araclar", unique)
        return self
