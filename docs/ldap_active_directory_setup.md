# LDAP / Active Directory Setup

GenAiOrionPanel — kurumsal dizin servisi entegrasyonu için operatör
notu. Ürün sözleşmesi [`baseline.md`](baseline.md); LDAP bağlantı
kontratı için [`backend/src/api/auth/ldap.py`](../backend/src/api/auth/ldap.py)
ve env referansı için
[`backend/src/observability/settings.py`](../backend/src/observability/settings.py)
"single source of truth"tır.

## 1. Domain Controller tarafı — AD üzerinde bir Read-Only
service account oluşturun

Aşağıdaki PowerShell parçacığı domain controller'ın DHCP-deployed
management agent'ında çalıştırılır. Yeni bir OU altında
`genai-orion-panel-sa` adında standart user account:

```powershell
# AD PowerShell modülünü yükle (sunucu tarafında default gelir)
Import-Module ActiveDirectory

# 1. Service account'u özel bir OU altında oluştur
$ou  = "OU=ServiceAccounts,DC=corp,DC=example,DC=local"
$upn = "genai-orion-panel-sa@corp.example.local"

New-ADUser `
    -Name            "GenAiOrionPanel Service Account" `
    -SamAccountName  "genai-orion-panel-sa" `
    -UserPrincipalName $upn `
    -Path             $ou `
    -AccountPassword  (ConvertTo-SecureString -AsPlainText 'REPLACE_ME_AT_PROVISIONING' -Force) `
    -Enabled          $true `
    -PasswordNeverExpires $true `
    -Description      "Read-only service account for GenAiOrionPanel LDAP"

# 2. Sadece okuma izinleri — kullanıcıları ve grupları görebilsin
#    (Domain Users grubu zaten miras yoluyla base DN'i okuyabilir;
#    eğer daha sıkı bir OU kullanıyorsanız bu OU'ya ACE verin.)

# 3. Sırlar Vault'a not düşülür; .env'e plaintext YAZILMAZ.
```

> **Secret rotation**: parola 90 günde bir döndürülüp Vault üzerinden
> konteyner secret'ı olarak push'lanır. Bu komut tekrar çalıştırılırsa
> eski hesap silinmez, yeni bir hesap açılır (failover).

## 2. .env dosyası — deployment/.env

LDAP sırları `deployment/.env` içindedir (compose `env_file`).
`docker-compose.yml` `environment:` bloğuna `LDAP_*` yazılmaz — bind
parolasındaki `$` compose interpolasyonu ile bozulur. Production'da
CI/CD secrets manager'dan inject edilir; asla commit edilmez
([.gitignore](.gitignore) zaten `.env`'i exclude eder).

Şablon: [`deployment/.env.example`](../../../deployment/.env.example).
CA PEM: `deployment/certs/` → container `/etc/ssl/corp/`.

```ini
# JWT — login imzalama
JWT_SECRET=<rand 32+ chars, base64>

# Bootstrap admin (LDAP dışı break-glass)
BOOTSTRAP_ADMIN_ENABLED=true
BOOTSTRAP_ADMIN_USERNAME=admin@local
BOOTSTRAP_ADMIN_PASSWORD=<12+ chars, vault-issued>
BOOTSTRAP_ADMIN_EMAIL=admin@local

# LDAP — connection
LDAP_ENABLED=true
LDAP_HOST=ldaps.corp.example.local
LDAP_PORT=636
LDAP_USE_SSL=true
LDAP_TLS_VERIFY=true
LDAP_CA_CERT=/etc/ssl/corp/ca-bundle.pem   # container side; volume-mount
LDAP_CONNECT_TIMEOUT=5

# LDAP — directory + bind
LDAP_BASE_DN=DC=corp,DC=example,DC=local
LDAP_BIND_DN=CN=GenAiOrionPanel Service Account,OU=ServiceAccounts,DC=corp,DC=example,DC=local
LDAP_BIND_PASSWORD=<injected from vault>
LDAP_REQUIRED_GROUP=CN=GenAiOrionPanel-Users,OU=Groups,DC=corp,DC=example,DC=local

# LDAP — attribute mapping (AD varsayılanları zaten doğru; değiştirmeyin)
LDAP_USER_ATTR=sAMAccountName
LDAP_MAIL_ATTR=mail
LDAP_DISPLAY_NAME_ATTR=displayName
LDAP_OBJECT_CLASS=user
LDAP_ADMIN_GROUP=CN=GenAiOrionPanel-Admins,OU=Groups,DC=corp,DC=example,DC=local
LDAP_GROUP_MEMBER_ATTR=memberOf

# Local fallback (dev/test). Prod'da KAPALI olmalı + break-glass ack.
LDAP_ALLOW_LOCAL_FALLBACK=true
DEFAULT_NAMESPACE_SLUG=demo

# Login rate-limit
LOGIN_RATE_LIMIT_MAX_ATTEMPTS=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=60
LOGIN_RATE_LIMIT_LOCKOUT_SECONDS=300

# Prod gate override'ları — sadece incident sırasında `true` yapın,
# post-mortem'de geri alın.
ALLOW_PROD_LOCAL_BREAK_GLASS=false
ALLOW_PROD_INSECURE_LDAP_TLS=false
```

## 3. Mapping kurulumu — ilk admin

`/auth/login` üzerinden `admin@local` ile girin, ardından **superuser**
`bootstrap_admin` üzerinden `LDAP_REQUIRED_GROUP`'taki bir Azure AD
group DN'i → `admin` role mapping kaydı girilir. Bu artık sonraki
herkes için LDAP üzerinden yöneteceğiniz "manifest".

```bash
# 1) bootstrap admin seed
cd backend && python -m scripts.seed_roles

# 2) LDAP bağlantısını smoke-test et
cd backend && python -m scripts.ldap_check --bind-user kubilay  # interaktif şifre sorar

# 3) API'yi ayağa kaldır
uvicorn backend.src.api.main:create_app --factory --reload

# 4) Tarayıcı → http://localhost:8000/admin/ldap-mappings?org_id=<uuid>
#    "+ Yeni mapping" formu:
#       group_dn  = "CN=GenAiOrionPanel-Users,OU=Groups,DC=corp,DC=example,DC=local"
#       role      = "admin"
#       namespace = boş (cluster-wide) veya belirli UUID
```

Tüm mapping CRUD `audit_log` tablosuna yazılır; rollback için:

```sql
SELECT created_at, actor_id, action, target_id, payload
FROM audit_log
WHERE target_type = 'ldap_group_mapping'
ORDER BY created_at DESC
LIMIT 50;
```

## 4. Sorun giderme

| Semptom | Olası sebep | Çözüm |
|--|--|--|
| `/auth/login` 503 + `LdapUnavailableError` | LDAP host:port unreachable; TCP timeout | `python -m scripts.ldap_check --host ...` → DNS/firewall |
| `Invalid credentials` her denemede | Bind DN veya parola yanlış | `LDAP_BIND_DN` tam DN olsun; Vault üzerinden yenileyin |
| `400 Bad Request: Search … is invalid` | `LDAP_BASE_DN` içinde encode gereken karakter | RFC 4515 escape (helper `auth/ldap._ldap_escape`) — özel `,` veya `=` için ne yapıldığını kontrol edin |
| Login OK ama rolü gelmiyor | `ldap_group_mappings` kaydı eksik veya `memberOf` attribute'ü DN'den farklı bir formatta dönüyor | AD tarafında `Get-ADUser -Properties memberOf` ile kullanıcının `memberOf`'larını kontrol edin |
| Health check `ldap=false` | TLS verify CA mismatch | `LDAP_CA_CERT` PEM bundle'a ekleyin **veya** `LDAP_TLS_VERIFY=false` (sadece dev) |

## 5. Pivot: LDAP'tan uzaklaşma / kapatma

Migrating off yolu:
1. `LDAP_ENABLED=false` + `BOOTSTRAP_ADMIN_ENABLED=true` (bkz. env)
2. `python -m scripts.ldap_check --no-bind` → sadece adım 1 (TCP) skip
3. Tüm LDAP-source `role_bindings` kayıtları `audit_log` üzerinden
   auditlenir; ops manuel olarak `source='ldap' → 'manual'` günceller
4. Bir sonraki login'de kullanıcı yerel bcrypt hesabına düşmez —
   LDAP DN'i user satırından temizlemek için tek seferlik bir SQL:

   ```sql
   -- Tüm kullanıcıların LDAP bağlantısını kopar (audit ihtiyacı varsa UPDATE'ten önce SELECT):
   UPDATE users SET ldap_dn = NULL WHERE ldap_dn IS NOT NULL;
   DELETE FROM ldap_group_mappings;
   ```
