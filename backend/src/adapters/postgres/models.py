"""``/admin`` route'larında kullanılan legacy sembol için takma ad modülü.

Legacy ``genai_orion_panel_adapters.postgres.models.RequestRow`` →
:mod:`backend.src.data.db.models.requests` içindeki ``Request`` modelinin
birebir ORM tanımı. Modül, import edenler için **``RequestRow`` adını**
ihraç eder; ``routes/admin.py`` minimal değişiklikle yeşile geçer.

Data sözleşmesi: alan adları / tipleri aynı (aşağıya bakınız).
Olmayan alanlar: ``error_code``, ``error_message`` (admin_service tarafında
kullanılabilir — sonraki turlarda).
"""

from __future__ import annotations

# `Request` zaten ``backend.src.data.db.models.requests`` içinde.
from backend.src.data.db.models.requests import Request as RequestRow

__all__ = ["RequestRow"]
