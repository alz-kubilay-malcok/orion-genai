"""create_app çıktısını listeleyen bir kerelik smoke script."""

from backend.src.api.main import create_app

app = create_app()
unique = {}
for r in app.routes:
    if hasattr(r, 'path'):
        methods = sorted(getattr(r, 'methods', set()) or [])
        # aynı path+method tekrarlarını birleştirmek için set kullanmıyoruz
        # — sırası önemli değil, toplamı raporlamak yeterli.
        unique.setdefault(r.path, set()).update(methods)

print(f"total routes: {len(unique)}")
for path in sorted(unique):
    methods = sorted(unique[path])
    print(f"  [{','.join(methods):30s}] {path}")
