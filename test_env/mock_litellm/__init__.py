"""Standalone mock for the LiteLLM admin API + MCP Gateway.

Run:
    uvicorn mock_litellm.app:app --host 127.0.0.1 --port 8200

Auth: `Authorization: Bearer ${LITELLM_ACCESS_KEY}` (default `asd123`).
State: in-process dicts + on-disk JSON snapshot at `mock_litellm/_data/keys.json`.
"""

from .app import create_app, run

__all__ = ["create_app", "run"]
