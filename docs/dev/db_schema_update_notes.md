# DB Schema Update Notes

Bu dosya DB şema değişikliklerinin **niyetini** ve **netleşmemiş
kararlarını** takip eder. Apply edilen DDL `_schema_history` üzerinden
ilerler; bu dosya pipeline onayı bekleyen taslakları tutar.

---

## Pending: `mail_jwt_tokens` (mail-capability JWT policy katmanı)

**Tarih:** 2026-08-22
**Durum:** ORM-only committed; DDL + migration **beklemede**.

### Amaç

Mail üzerinden giden onay linkleri için `core.mailing.jwt_mail.issue(...)`
çıktısı (compact JWT + jti + hash) burada policy olarak tutulur:

- **Replay protection** — `used_at` flip ile tek-kullanım.
- **Manuel revoke** — `revoked_at` + `revoked_reason`.
- **Audit trail** — `recipient`, `action`, request context.

İmza `HmacTokenSigner` benzeri legacy'den **bağımsız**; mail-flow
için ayrılmış salt-stdlib JWT (HS256).

### Final kolon şeması (target — henüz apply edilmedi)

| kolon              | tip              | notlar                                                                |
|--------------------|------------------|-----------------------------------------------------------------------|
| `id`               | UUID             | PK; sequence'siz DB. Uygulama tarafı UUID üretir.                     |
| `jti`              | VARCHAR(36)      | UNIQUE — JWT ID claim; DB lookup.                                     |
| `token_hash`       | LARGEBINARY(32)  | UNIQUE — `sha256(compact_token)`; secondary lookup.                   |
| `request_id`       | UUID FK          | `requests.id` ON DELETE CASCADE.                                      |
| `request_type`     | VARCHAR(32)      | CHECK IN (`litellm_key`, `mcp_key`).                                  |
| `action`           | TEXT             | CHECK IN (`approve`, `revise`, `reject`).                             |
| `recipient`        | TEXT             | mail-alıcısı; audit amaçlı.                                           |
| `issued_at`        | TIMESTAMPTZ      | when JWT imzalandı.                                                   |
| `expires_at`       | TIMESTAMPTZ      | `MAIL_JWT_TTL_DAYS` ile belirlenir.                                   |
| `used_at`          | TIMESTAMPTZ?     | nullable; non-null → consumed.                                        |
| `revoked_at`       | TIMESTAMPTZ?     | nullable; admin/manual kill-switch.                                   |
| `revoked_reason`   | TEXT?            | nullable.                                                             |
| `created_at`       | TIMESTAMPTZ      | server default `now()`.                                               |

### CHECK constraint isimleri (DDL'de birebir korunacak)

- `mail_jwt_tokens_action_check`
- `mail_jwt_tokens_request_type_check`
- `mail_jwt_tokens_expiry_check`

### İndeks kararları (TBD — final aşamada)

- `mail_jwt_tokens_request_idx` → `(request_id)`
- `mail_jwt_tokens_expiry_idx`  → `(expires_at) WHERE used_at IS NULL
  AND revoked_at IS NULL`

PG'de partial index; SQLite sürümünde kısmen farklılaşabilir
(`CREATE INDEX` WHERE-clause SQLite ≥ 3.8 destekler).

### Dialect mapping kararları

| Kolon           | PostgreSQL              | SQLite                  |
|-----------------|-------------------------|-------------------------|
| `id`, `request_id` | `UUID`               | `CHAR(36)`              |
| `jti`           | `VARCHAR(36)` ↔ `TEXT`  | `TEXT`                  |
| `token_hash`    | `BYTEA`                 | `BLOB`                  |
| `request_type`  | `VARCHAR(32)` (string)  | `TEXT`                  |
| `action`, `recipient` | `TEXT`           | `TEXT`                  |
| TIMESTAMPTZ alanları | `TIMESTAMP WITH TIME ZONE` | ISO-8601 naive UTC TEXT (`types.UtcDateTime` zaten konvert eder) |

### Migration versioning

Next free `Migration.version` `flyway_status(...)` ile
kontrol edilip boş slot'tan verilecek. `approval_tokens` v17
(legacy tahmini — apply'i öncesi `backend/src/data/scripts/flyway.py`
üzerinden registry dump al).

### Apply checklist (apply aşamasında)

1. PG tarafı:
   `backend/src/data/schemas/postgresql/tables/mail_jwt_tokens.py`
   (DDL + `apply` + `mail_jwt_tokens_migration = Migration(...)`).
2. SQLite tarafı:
   `backend/src/data/schemas/sqlite/tables/mail_jwt_tokens.py`
   (mirror; partial index için dialect-aware karar).
3. Her iki registry'e ekle
   (`.../postgresql/tables/__init__.py`,
   `.../sqlite/tables/__init__.py`). Sıralama: trigger'lardan önce,
   `audit_events`/`outbox_jobs`'dan sonra kabul edilebilir — FK
   yalnız `requests`'e.
4. `flyway_init(url)` smoke test.

### Bugün committed olanlar

- `backend/src/data/db/models/mail_jwt_tokens.py`   — `MailJwtToken` ORM
- `backend/src/data/db/models/__init__.py`          — registry'ye eklendi
- `backend/src/data/schemas/postgresql/tables/mail_jwt_tokens.py` — DDL v14
- `backend/src/data/schemas/sqlite/tables/mail_jwt_tokens.py`     — DDL v14
- her iki `tables/__init__.py` — registry'ye v14 eklendi
- `backend/src/core/mailing/jwt_mail.py`             — PyJWT HS256
- `backend/src/core/mailing/mail_jwt_validator.py`   — DB-backed tek-kullanım
- `backend/requirements.txt`                          — `pyjwt>=2.8`

### Open items (apply aşaması dışı, kullanıcı/harness sorumluluğu)

- `.env` dosyası `MAIL_JWT_SECRET` env'ini **içermiyor**; secret set
  edilmeden ilk `issue()` çağrısı `MailJwtConfigError` fırlatacak.
  PyJWT 32-byte HMAC secret öneriyor (RFC 7518 §3.2) — bunun
  altındaki secret'ler **uyarı** verir, token üretimini bloklamaz.
- `mail_jwt_validator.validate_and_consume(...)` route tarafından
  çağrıldığında `AsyncSession` transaction sınırı route handler'a
  bağlı (UoW deseni).
- Claim standardizasyonu (key adları: `sub/typ/act/rec/iat/exp/jti`)
  HTML template'ler ve `core.mailing.mailer.send_mail` ile birlikte
  senkronize edilecek — sonraki tur.

## Pending: `receivers` (mail alıcısı authoritative kaydı)

**Tarih:** 2026-08-22
**Durum:** ORM + DDL + registry committed (v15). Apply edildi mi? Test smoke
(`flyway_init`) sonrası işaretlenecek.

### Amaç

LDAP entegrasyonu bağlanana kadar mail alıcıları burada tutulacak.
`mail_messages.recipients` aynı universe'i kullanır; `receivers` source
of truth olarak düşünülmeli. LDAP gelince bu tablo soft-deleted
(`inactive_at` kolonu) olarak taşınır ya da kaldırılır.

### Kolon şeması

| kolon         | tip             | notlar                              |
|---------------|-----------------|-------------------------------------|
| `id`          | UUID            | PK; client tarafı üretilir.         |
| `first_name`  | TEXT            | not null.                           |
| `last_name`   | TEXT            | not null.                           |
| `email`       | TEXT            | not null; UNIQUE (`receivers_email_key`). |
| `created_at`  | TIMESTAMPTZ     | not null default `now()` (audit).   |

### Dialect mapping

| Kolon         | PostgreSQL        | SQLite                |
|---------------|-------------------|-----------------------|
| `id`          | `UUID`            | `CHAR(36)`            |
| first/last/email | `TEXT`          | `TEXT`                |
| `created_at`  | `TIMESTAMPTZ`     | ISO-8601 TEXT         |

### Apply checklist

1. ✅ ORM: `backend/src/data/db/models/receivers.py` (`Receiver`).
2. ✅ ORM registry: `backend/src/data/db/models/__init__.py`.
3. ✅ PG DDL: `backend/src/data/schemas/postgresql/tables/receivers.py`
   (`receivers_migration = Migration(version=15, ...)`).
4. ✅ SQLite DDL: `backend/src/data/schemas/sqlite/tables/receivers.py`
   (mirror, aynı version).
5. ⏳ Apply smoke: `flyway_init(url)`, `_schema_history`'de v15 kaydı.
6. ⏳ Repository/service katmanı: `ReceiverRepository` + uygulama kancası
   (mailer öncesi upsert) — **bu tur yazılmadı**, sadece DB kontratı.

### Open items

- Receiver'ı mailer üzerinde nasıl çözeceğimizi bağlamadık —
  `mail_messages.recipients` array'ine yazılırken bu tabloda
  upsert/reject politikası ayrı bir karar.
- LDAP geldiğinde FK bağlama (`users.id ON DELETE SET NULL` + back-fill)
  — ayrı migration, farklı tur.
