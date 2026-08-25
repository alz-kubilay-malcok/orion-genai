# Backend Implementation Plan — Tier 1 (Production-Ready Push)

**Sahip:** backend-core  
**Tarih:** 2026-08-25  
**Durum:** A checkpoint'i kapatıldı; Faz B-F açık  
**Referans:** `backend_gap_analysis.md` (refactor kapanış snapshot'ı)

## TL;DR

Tier-1 refactor sonrası backend'i uçtan uca çalışır hale getirmek için 30 adımlık bir plan.

- **A — CLI & runtime çekirdek** — `backend/main.py` orchestrator; worker heartbeat wiring.
- **B — Application/Domain katmanı** — Protocol + entity katmanı.
- **C — Adapter katmanı** — `core/litellm/*` gerçek httpx implementasyonları.
- **D — Worker uçtan uca** — handler/factory/dispatcher rewrite.
- **E — Cross-cutting & smoke** — yeni 2 smoke testi.
- **F — Temizlik** — temp dosya silme, export cleanup.

**Onaylar (2026-08-25):** LiteLLM adapter = `httpx iskeleti + ENV-varsa HTTP`; CLI entry = mevcut `backend/main.py` rewrite; Worker heartbeat = tick-sonu upsert; DB = yeni tablo gerekirse izin var, mevcut şemaya dokunulmuyacak.

---

## Faz A — CLI & runtime çekirdek

| # | Dosya | İş | Yöntem |
|---|---|---|---|
| A-1 | `backend/main.py` | yeniden yaz | Şu an 5 sub-command + defaults: `migrate`, `api`, `worker`, `debug-routes`, `defaults`. `debug-routes` `openapi()["paths"]` ile flat enumerate eder |
| A-2 | `backend/src/worker/dependencies_factory.py` | heartbeat callback factory | `_build_heartbeat_callback(session_factory)` → sync wrapper, içeride `asyncio.run(_upsert())` ile `WorkerHeartbeatRepository(session).upsert(...)`. Worker sync outer zone'da çalıştığı için nested-loop safe |
| A-3 | `backend/src/data/db/__init__.py` | repo re-export | `WorkerHeartbeatRepository` `__all__`'a eklendi |

### A-1 doğrulama

```
python backend\main.py --help
python backend\main.py debug-routes
```

8 rota JSON: `/admin/ldap-mappings` (GET/POST/DELETE), `/auth/{login,me,refresh}`, `/health/{live,ready}`, `/webhooks/orion`.

### A-2/A-3 doğrulama

Repl içinde sqlite ayağa kaldırılıp callback 2 kez çağrıldı:
- 1. çağrı → INSERT
- 2. çağrı → last_seen_at UPDATE

Uyumluluk: `WorkerHeartbeatRepository.upsert(self, *, worker_id, version, started_at, last_seen_at, active_job_id=None, scheduler_last_run_at=None)` — Repository pattern; session constructor'da.

---

## Faz B — Application / Domain katmanı

| # | Dosya | İçerik |
|---|---|---|
| 5 | `backend/src/application/__init__.py` | paket iskeleti |
| 6 | `backend/src/application/ports/__init__.py` | re-export |
| 7 | `backend/src/application/ports/unit_of_work.py` | `UnitOfWork(Protocol)`: `session`, `requests`, `audit`, `revisions`, `outbox` Protocol'ler + `commit/rollback` |
| 8 | `backend/src/application/ports/crypto.py` | `SecretCipher`, `TokenSigner` Protocol'ler |
| 9 | `backend/src/application/ports/litellm.py` | `LiteLLMPort`, `MCPProvisionPort`, `MCPCatalogPort` + `ProvisionLiteLLMKeyCommand`/`ProvisionMCPKeyCommand`/`ProvisionResult` dataclasses |
| 10-13 | `backend/src/domain/entities/{__init__,request,request_revision,approval_token}.py` | yalın dataclass'lar; ORM ile aynı field set |

---

## Faz C — Adapter katmanı

| # | Dosya | İçerik |
|---|---|---|
| 14 | `backend/src/core/litellm/__init__.py` | public API: `provision_litellm_key`, `provision_mcp_key`, approve/reject/revise handler'ları, `verify_and_parse` |
| 15 | `backend/src/core/litellm/provision.py` (~240 satır) | httpx: `LiteLLMKeyHttpAdapter`, `MCPScopedKeyHttpAdapter`. `LITELLM_BASE_URL` env yoksa `DummyLiteLLMKeyAdapter` (dry-run). Hata sınıfları: `LiteLLMUnavailableError`, `LiteLLMPermanentError` |
| 16 | `backend/src/core/litellm/revision.py` (~120 satır) | `Approve/Reject/ReviseRequestHandler` artık `admin_service.admin_approve/revise/reject` çağrısı (lazy import cycle-safe) |
| 17 | `backend/src/core/litellm/token_validation.py` (~140 satır) | `verify_and_parse` → `core.mailing.mail_jwt_validator.validate_and_consume()` → `ApproveApprovalToken` |
| 18 | `backend/src/api/utils/mapping.py` (~150 satır) | `ReceiveGenAiOrionPanelRequestCommand` + 3 detail dataclass + handler |

---

## Faz D — Worker uçtan uca

| # | Dosya | İş |
|---|---|---|
| 19 | `dependencies_factory.py` | legacy `genai_orion_panel_adapters.*` import zincirini sil; `LiteLLMKeyHttpAdapter` construct |
| 20 | `handlers.py` | `_handle_provision_litellm/_mcp` artık `await core.litellm.provision.provision_*` çağrısı yapar |
| 21 | `dispatcher.py` | `tick()` sonu opsiyonel heartbeat dispatch (mevcut `deps.heartbeat_callback` reuse) |
| 22 | `runner.py` | `run_forever` içinde tick + heartbeat; zaten wired (libs §53) |
| 23 | `data/db/repository.py` | `WorkerHeartbeatRepository.upsert` mevcut (satır 314) — ekleme yok |

---

## Faz E — Cross-cutting & smoke

| # | Dosya | İş |
|---|---|---|
| 24 | `worker_import_check.py` | mevcut; opsiyonel --version binding |
| 25 | `dispatch_dlq_smoke.py` | mevcut; sadece çalıştığını doğrula |
| 26 | `heartbeat_smoke.py` | **yeni** — sync outer zone manual tablo drop/create + 2 çağrı ile INSERT/UPDATE assert |
| 27 | `scripts/checks/__init__.py` | boş paket marker |
| 28 | `admin_service_unit_check.py` | **yeni** — 3 positive + 4 negative (mock sqlalchemy session) |

---

## Faz F — Temizlik

| # | İş |
|---|---|
| 29 | `__tmp_route_audit.py` ve diğer `__tmp_*` dosyaları sil |
| 30 | `core/litellm/__init__.py` `__all__` gerçek public API'yi export etsin |

---

## Verification (Tier-1 kabul)

1. `python backend\main.py debug-routes` → 8 rota JSON dump.
2. `python backend\main.py api` → uvicorn → `create_app()` ayakta.
3. `python -c "from backend.src.worker.__main__ import main; main()"` → DB varsa 1 başarılı tick.
4. `python -c "from backend.src.core.litellm.provision import LiteLLMKeyHttpAdapter"` → sınıf import edilebilir (Faz C sonrası).
5. `python backend\main.py debug-routes | head -3` → uçtan uca rapor.

---

## Decisions & Inclusions

- ❌ **DB schema migration yok** — yeni tablo için izin var, ama mevcut şemaya dokunulmuyacak.
- ❌ **pytest/integration tests yok** (Tier-2 §33'e ertelendi).
- ✅ **httpx tabanlı LiteLLM/MCP adapter**.
- ✅ **CLI entry** = mevcut `backend/main.py` rewrite.
- ✅ **Worker heartbeat** her tick sonu upsert.

---

## Risks / Open-cap Decisions

- `core/litellm/revision.py` → admin_service çağrısı döngüsel import riski taşıyor. Çözüm: function-scope **lazy import**.
- `application/ports/unit_of_work.py` Protocol'lerin mevcut SqlAlchemyUnitOfWork'le birebir örtüşmesi gerekmiyor; duck-typing yeterli.
- DLQ pattern: Mevcut handler'lar TransientError'da backoff uyguluyor; yeni adapter bu kalıbı korur.

---

## Changelog

| Tarih | Yazar | Not |
|---|---|---|
| 2026-08-25 | backend-core | İlk plan (memory → docs snapshot) |
| 2026-08-25 | assistant | A-checkpoint kapatıldı; A-1 (CLI rewrite) + A-2 (heartbeat callback) + A-3 (`__init__.py` export) ✅ |
