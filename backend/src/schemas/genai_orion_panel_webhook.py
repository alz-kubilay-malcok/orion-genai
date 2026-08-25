"""Orion webhook shared alanları (Bölüm 5.1).

Flat JSON'da tüm tipler için zorunlu shared key'ler:
  talep_turu, talep_no, talep_url, talep_eden_adi,
  talep_eden_eposta, olusturulma_tarihi
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

# Turkish ASCII snake_case. Accent/camelCase reddedilir.
TICKET_ID = Annotated[str, Field(min_length=1, max_length=64)]
REQUESTER_NAME = Annotated[str, Field(min_length=1, max_length=200)]


class SharedGenAiOrionPanelFields(BaseModel):
    """Tüm üç automated form için ortak shared alanlar.

    `extra='forbid'` ile bilinmeyen top-level alanlar reddedilir (Bölüm 10.1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    talep_turu: str = Field(min_length=1, max_length=64)
    talep_no: TICKET_ID
    talep_url: HttpUrl
    talep_eden_adi: REQUESTER_NAME
    talep_eden_eposta: EmailStr
    olusturulma_tarihi: datetime


# Talep türü → internal request_type mapping (Bölüm 4.1).
TALEP_TURU_MAPPING: dict[str, str] = {
    "litellm_api_anahtari": "litellm_key",
    "mcp_erisim_anahtari": "mcp_key",
    "mcp_sunucu_kaydi": "mcp_server_registry",
    # chatbot_support external contract netleştiğinde eklenecek.
}
