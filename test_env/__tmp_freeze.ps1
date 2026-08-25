$ErrorActionPreference = "Stop"
Set-Location "C:\projects\GenAiOrionPanel\backend"
& ".venv\Scripts\python.exe" -m pip freeze 2>&1 |
    Select-String -Pattern '^(fastapi|uvicorn|sqlalchemy|alembic|aiosqlite|asyncpg|pydantic|pydantic_settings|jinja2|httpx|python_multipart|cryptography|starlette|typing_extensions|annotated_types|click|colorama|h11|httpcore|psycopg2) ' |
    ForEach-Object { $_.Line } |
    Sort-Object
