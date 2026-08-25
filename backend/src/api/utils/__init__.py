"""API utils paketi — middleware, schemas, security, mapping, dependencies, admin_service.

Hexagonal sınır: `genai_orion_panel_core` (domain) ↔ `genai_orion_panel_api.utils`
(composition & transport glue). Route handler'ları sadece bu paket üzerinden
adapter'lara erişir; core'a import edilmez.
"""
