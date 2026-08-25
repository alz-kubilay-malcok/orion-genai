"""test_env — Orion Studio test ortamı paketi.

Tüm gerçek notlar ve launcher yönergeleri için bkz. ``test_env/README.md``.

Bu dosya bilinçli olarak sade bir Python modülüdür; ``import test_env``
çağrılarında ``SyntaxError`` üretmemesi için içinde köşeli parantezli
checklist satırları yer almaz.
"""

__all__: list[str] = []


# --- Eski "tournament defteri" notu (referans amaçlı) ----------------------------
# Test ortami acilis notebook'u.
# Backend (apps/api, apps/worker) ve mock servisleri test_env/scripts/ icinden
# ayri sekilde acabilirsin.
#
# ( ) Mock LiteLLM           -- 127.0.0.1:8200 -- scripts/run_mock.ps1
# ( ) Backend API            -- 127.0.0.1:8001 -- scripts/run_api.ps1
# ( ) Backend worker         -- arkaplan      -- scripts/run_worker.ps1
# ( ) Streamlit orion_studio -- 127.0.0.1:8501 -- scripts/run_panel.ps1
#
# ortam degiskenleri (ornek):
#     LITELLM_ACCESS_KEY=asd123
#     GENAI_ORION_PANEL_WEBHOOK_SECRET=dev-orion-secret
#     DATABASE_URL=sqlite+aiosqlite:///../db/orion.db
# ---------------------------------------------------------------------------------
