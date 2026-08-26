# API'ye özgü transport sözleşmeleri (admin action body + catalog + webhook).
from backend.src.api.utils.schemas.webhook import (
    SCHEMA_BY_TALEP_TURU,
    TALEP_TURU_MAPPING,
)

__all__ = ["SCHEMA_BY_TALEP_TURU", "TALEP_TURU_MAPPING"]
