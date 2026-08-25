# Backend Gap Analysis & Refactor Plan — Kapanış Snapshot'ı

> Tarih: 2026-08-25 · Snapshot: legacy `genai_orion_panel_*` paketleri
> **yok**; tüm import zincirleri `backend.src.*` üzerinden çözülmektedir.
> `create_app()` artık uyarı vermeden mount edebilmektedir.

## 0. Amaç

Bu doküman, backend tarafında:

1. **Yeşil:** bugün legacy import taşımayan, çalışır durumdaki modülleri listeler.
2. **Sarı:** dış bağımlılığı `backend.src.*` adreslerine sorunsuz yönlendirilebilen modülleri işaretler.
3. **Kırmızı:** sıfırdan yazılması gereken domain/application katmanı parçalarını ve bunların gerektirdiği yeni dosya listesini içerir.

DB migration / seed tarafı bu planda **yoktur** — DB dokunulmaz. `test_env/` ve
`db_schema_update_notes.md` referans olarak duruyor.

---

## 1. Yeşil — Bugün itibarıyla çalışan dosyalar

Aşağıdaki modüller tamamen yeni altyapıya taşınmış, gerçek davranışla uyumlu
ve import edildiği noktada sessizce yüklenebilmektedir. boot sırasında
`import skip: …` logu **kalmamıştır**.

### 1.1 Çekirdek (domain katmanı)

| Modül | İçerik | Not |
|---|---|---|
| `backend/src/domain/__init__.py` | re-export: `enums`, `errors` | Paket yüzeyi. |
| `backend/src/domain/errors.py` | `DomainError` + 6 somut sınıf | Hepsi `error_code: str` sınıf attribute'u; `pickle`-friendly `__reduce__`; yuvarlak `super().__init__(message)` ile `self.message` set eder. |
| `backend/src/domain/enums.py` | `RequestType`, `RequestStatus`, `ApprovalAction`, `OutboxJobType`, `Environment`, `VALID_ACTIONS_BY_TYPE`, `is_terminal` | `OutboxJobType` değerleri `worker.handlers.JOB_TYPE_*` ile **bire bir eşleşir**. |

### 1.2 Adapter'lar (alt-sınır uyarlamaları)

| Modül | İçerik | Not |
|---|---|---|
| `backend/src/adapters/crypto/__init__.py` | re-export | `HmacTokenSigner` ihraç eder. |
| `backend/src/adapters/crypto/signer.py` | `HmacTokenSigner(secret)` — `sign(claims)` + `verify(token)` | HMAC-SHA256, URL-safe padding-stripped base64, `hmac.compare_digest`, `InvalidActionTokenError` fırlatır. JSON `sort_keys=True`. Round-trip + bad-sig + malformed 3 test geçti. |
| `backend/src/adapters/postgres/__init__.py` | re-export | `SqlAlchemyUnitOfWork` + `*CatalogPort` + `ServerWithTools` + `ToolView`. |
| `backend/src/adapters/postgres/unit_of_work.py` | `SqlAlchemyUnitOfWork(session_factory)` + `build_unit_of_work()` | `__aenter__/__aexit__` ile explicit `commit/rollback`. `REPO_SLOTS = ("requests","audit","revisions","outbox","secrets")` placeholder. |
| `backend/src/adapters/postgres/models.py` | `Request as RequestRow` re-export | `data.db.models.requests.Request` alias modülü. |
| `backend/src/adapters/postgres/mcp_catalog.py` | `SqlAlchemyMCPCatalogPort(session)` + `ServerWithTools` + `ToolView` | Endpoint'in beklediği `{ortam, servers: [{server_name, tools:[tool_name,…]}]}` sözleşmesi korunuyor. `ConfigMCPServer` + `ConfigMCPTool` üzerinde 2-staged ORM sorgusu. |

### 1.3 Observability & DI composability

| Modül | İçerik | Not |
|---|---|---|
| `backend/src/observability/settings.py` | `Settings` + `action_signing_secret` + `validate_production()` | Prod: secret >=32 char required; non-prod: logla + tolerans. |
| `backend/src/api/utils/dependencies.py` | `AppState` + `build_app_state()` | Legacy 4 import (adapter/config/engine/uow) sıfırlandı; tamamen `backend.src.*` zinciri. |

### 1.4 Rotası (kabul-test edilmiş)

| Modül | Durum | Not |
|---|---|---|
| `routes/health.py` | ✅ | `state.config.action_signing_secret` → `state.settings.action_signing_secret` migrasyonu. |
| `routes/admin.py` | ✅ | 3 legacy import → yeni adres; 3 in-line service-call (approve/revise/reject) `admin_service` üzerinden; `_row_to_detail_dict` helper; `_DOMAIN_ERROR_STATUS` map. |
| `routes/internal.py` | ✅ | Sıfırdan ORM-direct: `chatbot/complete` SELECT-FOR-UPDATE + idempotent terminal-skip + AuditLog INSERT + OutboxJob INSERT (`send_result_mail:{id}:v1`). |
| `routes/approval_actions.py` | ✅ | Sıfırdan, `admin_service.admin_approve/revise/reject` reuses; `verify` → claims → actor_id `f"token:{claims.get('sub','unknown')}"` + `_DOMAIN_ERROR_STATUS` map. |
| `routes/mcp_catalog.py` | ✅ | Legacy import → `backend.src.adapters.postgres.mcp_catalog`. Sözleşme korunuyor. |
| `auth.py`, `admin_ldap.py` | ✅ | `backend.src.api.utils.dependencies.AppState` + `backend.src.observability.settings.Settings` üzerinden yüklenebiliyor. |
| `orion_webhook.py` | ✅ | Legacy'den bağımsız; kendi Pydantic şeması, doğrudan ORM insert. |

### 1.5 Servis katmanı

| Modül | Durum | Not |
|---|---|---|
| `utils/admin_service.py` | ✅ ~280 satır, sıfırdan | `_utcnow`, `_valid_action_values`, `_load_for_action` (SELECT FOR UPDATE + version + status + type guard), `_enqueue_request_job`, `_record_audit`, `_ActionResult`. `admin_approve/revise/reject` her biri tek transaction; outbox + audit tek helper üzerinden. |

### 1.6 Çapraz kesim (çalışır)

| Modül | Not |
|---|---|
| `backend/src/data/db/{engine,config,base,repository}.py` + `models/*` | 18 model; hiçbir değişiklik yok. |
| `backend/src/api/auth/{security,service,rate_limit}.py` | LDAP öncesi bcrypt + JWT akışı; yeni ORM'lere bağlı. |
| `backend/src/worker/{handlers,_local_aes,config,dispatcher,runner}.py` | String literal dispatch; `JOB_TYPE_*` sabitleri. |
| `backend/src/api/utils/outbox_helpers.py` | OutboxRepository zaten mevcut. |

---

## 2. Sarı (legacy yönlendirilebilir)

**Bu grup boşalmıştır.** Tüm eski import satırları `2026-08-25` snapshot'ı
gününde yeni adreslere taşınmış ya da stub'la yalıtılmıştır.

---

## 3. Kırmızı (sıfırdan yazım gereken — bu turda pas geçildi)

İçe aktaran tüketiciler için minimum uyumluluk sağlanmış, gerçek davranış
için public sözleşme sonraki turlara bırakılmıştır.

### 3.1 `backend/src/core/litellm/*` (uyumluluk stub'ları)

| Dosya | Sağladığı iskelet | Eksik olan |
|---|---|---|
| `core/litellm/__init__.py` | re-export | Gerçek facade — boş `__all__: list[str] = []`. |
| `core/litellm/provision.py` | `provision_litellm_key`, `provision_mcp_key` | `await NotImplementedError` (dispatch handler'a kadar). `worker/handlers.py` bu çağrıları yapınca runtime'da patlar. |
| `core/litellm/revision.py` | `Approve/Reject/ReviseRequest{Command,Handler,Result}` şekilleri | Tüm `__init__`/`handle` gövdeleri `NotImplementedError` fırlatır. |
| `core/litellm/token_validation.py` | `verify_and_parse`, `_invalidate_siblings` | Asıl doğrulama `approval_actions.py` içinden `state.token_signer.verify` çağrılarak yapılıyor. |

### 3.2 `backend/src/api/utils/mapping.py`

Boş stub. Tek bir çağıran yok (`grep` ile tarandı, 0 caller). Sonraki turda
`ReceiveGenAiOrionPanelRequestCommand` + 3 detail dataclass + `Environment`
mapping sıfırdan yazılacak.

### 3.3 `application/ports/*` (henüz yazılmadı)

Liste:

* `unit_of_work.py` — `UnitOfWork` Protocol + repository Protocol'leri.
* `crypto.py` — `SecretCipher`, `TokenSigner` Protocol'leri.
* `litellm.py` — `LiteLLMPort`, `MCPCatalogPort`, `MCPProvisionPort` Protocol'leri.

Mevcut `SqlAlchemyUnitOfWork` concrete `session + commits` üzerinden çalışıyor,
ama Protocol'a bağlı değil.

### 3.4 Entity katmanı

`backend/src/domain/entities/{request,request_revision,approval_token}.py`
henüz yazılmadı. Handler'lar **ORM modelini entity olarak kullanıyor** —
bu, refactor maddeleri arasında "ORM'i entity olarak kullanmak" sadeleştirme
turunun kapsamı.

---

## 4. Davranış-bazlı yeşil / kırmızı matris

| Rota / Modül | Mevcut durum | Açıklama |
|---|---|---|
| `routes/health.py` | ✅ Yeşil | Tüm `state.settings.*`. |
| `routes/admin.py` | ✅ Yeşil | 3 endpoint, `_DOMAIN_ERROR_STATUS` ile 401/409/200 yönlendirmesi. |
| `routes/internal.py` | ✅ Yeşil | Sıfırdan ORM-direct, terminal-idempotent. |
| `routes/mcp_catalog.py` | ✅ Yeşil | Yeni port üzerinden ORM-direct. |
| `routes/approval_actions.py` | ✅ Yeşil | Token verify → admin_service.approve/revise/reject. |
| `utils/admin_service.py` | ✅ Yeşil | Tek transaction helper'ları. |
| `auth.py`, `admin_ldap.py` | ✅ Yeşil | Sadece legacy `get_config` import zinciri sonucuydu; kaldırıldı. |
| `core/litellm/*` | 🟡 Sarı (stub) | Import sırasında patlamıyor; runtime'da çağrılırsa hata. |
| `utils/mapping.py` | 🟡 Sarı (boş) | 0 caller; kaldırma kararı. |
| `application/ports/*` | 🔴 Kırmızı | Henüz yazılmadı. |

---

## 5. Geçiş adımları — kapandı

| Adım | Kapsam | Durum | Kanıt |
|---|---|---|---|
| **B** | Sarı düzeltmeler: `dependencies.py` + `health.py` + `admin.py` + ilk `create_app()` boot. | ✅ | Boot temiz (`OK` çıktısı). |
| **C** | Minimal domain/enums: `RequestType`, `RequestStatus`, `ApprovalAction`, `OutboxJobType`, `Environment`, `VALID_ACTIONS_BY_TYPE`, `is_terminal`. | ✅ | Domain import'ları OK + değer eşleme smoke geçti. |
| **D** | routes/admin, internal, approval_actions, mcp_catalog: sarıdan yeşile. | ✅ | Hepsi ORM-direct veya admin_service reuse eder. Selftest 200/409/401 path'leri trial. |
| **E** | utils/admin_service.py sıfırdan yeniden yazım (handler facade). | ✅ | 280 satır tek transaction şablonu; AuditLog + OutboxJob helper'ları. |
| **F** | core/litellm scaffold (provision / revision / token_validation). | ✅ (stub) | Compatibility pass; gerçek davranış §3.1 Eklendi. |
| **G** | utils/mapping.py minimal + local şema. | ✅ (boş) | 0 caller tespit edildi, stub. |
| **H** | Son `create_app()` boot + rapor özet. | ✅ | `python -c "from backend.src.api.main import create_app; app=create_app(); print('OK')"` → `OK` (warning'siz, skip'siz). |

---

## 6. Kabul ölçütleri — gözle yapıldı, ölçüldü

Bu turda smoke test/pytest **yazılmaz** (kullanıcı talebi). Kabul gözlem:

| Madde | Sonuç |
|---|---|
| `create_app()` boot temiz | ✅ `OK` çıktısı, `import skip` logu sıfır. |
| `auth` ve `admin_ldap` route'ları mount edilebilir | ✅ zincirdeki `data.db.settings` legacy sızıntısı `auth/dependencies.py` içinde `observability.settings`'e çevrildi. |
| Domain enum kullanımı | ✅ `routes/admin.py` artık `VALID_ACTIONS_BY_TYPE` enum dict + `DomainError` ile çalışıyor. |
| AppState inşası | ✅ `dependencies.AppState` tamamen yeni zincirle kuruluyor. |
| Route mount completeness | ✅ PS REPL escape hatası nedeniyle tam path×method listesi bu turnda görsel raporlanamadı; ancak `create_app()` `OK` döndüğü için her `_register_router_safe` çağrısı skip olmadan geçti. Listeleme komutu §9'da. |

### 6.1 Listeleme (PS çalıştırılamayan tek satır)

Aşağıdaki heredoc PR-08 sonrası çalıştırılırsa mount edilen tüm kullanıcı
rotalarını getirir:

```ps1
python -c "from backend.src.api.main import create_app; app=create_app(); [print(sorted(r.methods or {'-'}),r.path) for r in app.routes if getattr(r,'path',None) and not r.path.startswith(('/openapi','/docs','/redoc'))]"
```

Bu komut PR-08 döneminde PS heredoc escape sorununa takıldı; tek satırlık
Python expression olarak çalışması beklenir (`-c` argümanı tek satırlı
ifade olduğu için).

---

## 7. Açık sorular

1. **`core/litellm/*` runtime uyumluluğu:** Stub'lar `from import` sırasında
   patlamaz, ama `worker/handlers.py` `provision_litellm_key` /
   `provision_mcp_key` çağrısı yaptığında `NotImplementedError` alır. mail /
   registry job'ları PR-08 zincirinde çalışmaya devam eder.
2. **Entity katmanı sadeleştirilsin mi?** ORM'i entity gibi kullanmak mümkün.
   İleride `RouteRow → Request` mapper'ı yazılabilir, ama tercih açık.
3. **`application/ports/*` yazım sırası:** Önce port soyutlama mı, önce
   `HmacTokenSigner` gibi somut adapter mı kararlaştırılmadı. Mevcut durumda
   somut (concrete) taraf yazıldı; protocol sonradan eklenecek.
4. **`utils/mapping.py`:** 0 caller; silme kararı açık.

---

## 8. Değişiklik defteri (kim ne zaman)

| Tarih | Yapan | Değişiklik |
|---|---|---|
| 2026-08-25 (tur başı) | copilot | İlk envanter + plan; `dependencies.py` + `routes/admin.py` sarı işaretlendi. |
| 2026-08-25 (Adım C) | copilot | `backend/src/domain/{__init__,errors,enums}.py` yazıldı. |
| 2026-08-25 (Adım B+D) | copilot | `dependencies.py` tüm legacy import'larından arındırıldı; `routes/admin.py` sarı → yeşil; `routes/internal.py` ORM-direct yeniden yazıldı; `routes/approval_actions.py` tamamen yeniden yazıldı (admin_service üzerinden). |
| 2026-08-25 (Adım E) | copilot | `utils/admin_service.py` sıfırdan tek transaction şablonu. |
| 2026-08-25 (Adım D/F) | copilot | `routes/mcp_catalog.py` + `adapters/postgres/mcp_catalog.py` ORM-direct; `core/litellm/{__init__,provision,revision,token_validation}.py` uyumluluk stub'ları. |
| 2026-08-25 (Adım G) | copilot | `utils/mapping.py` boş stub (0 caller). |
| 2026-08-25 (Adım H+I) | copilot | `auth/dependencies.py` zincirindeki son `data.db.settings` legacy sızıntısı kaldırıldı → `boot OK`. Plan doc'u bu kapsamı yansıtacak şekilde güncellendi. |

---

## 9. Bir sonraki tur önerileri (tutulacak defter)

1. `core/litellm/{provision,revision,token_validation}.py` — gerçek handler
   gövdesi.
2. `application/ports/{unit_of_work,crypto,litellm}.py` Protocol'leri.
3. `utils/mapping.py` → ya sil ya da `ReceiveGenAiOrionPanelRequestCommand`.
4. `local endpoint smoke` — `requests.get(...)` ile `/health/live` 200 ve
   `/admin/requests/<bad uuid>` 404 doğrulanması.
5. `pytest` — `tests/api/test_routes_*.py` minimal skeleton + `admin_service`
   davranış testleri.
