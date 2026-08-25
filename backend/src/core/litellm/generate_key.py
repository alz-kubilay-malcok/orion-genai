"""LiteLLM Proxy `/key/generate` gövdesi.

Docs:
  https://docs.litellm.ai/docs/proxy/virtual_keys
  GenerateKeyRequest: `team_id`, `max_parallel_requests`, `models`, `key_alias`.

`max_parallel_requests`: eşzamanlı (in-flight) istek tavanı; aşınca 429.
`team_id`: key'i LiteLLM team satırına bağlar. UI "team adı" verir;
`GET /team/list` içinden `team_alias` veya `team_id` eşleşmesi çözülür.
TPM/RPM (`tpm_limit` / `rpm_limit`) bu üründe gönderilmez.
"""

from __future__ import annotations

from typing import Any, Mapping

TEAM_LIST_PATH = "/team/list"


def parse_team_list(payload: object) -> list[dict[str, Any]]:
    """`GET /team/list` hem `{teams: [...]}` hem düz liste dönebilir."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("teams", "data", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def match_team_id(teams: list[Mapping[str, Any]], name: str) -> str | None:
    """`team_alias` veya `team_id` (casefold) → LiteLLM `team_id`."""
    needle = name.strip().casefold()
    if not needle:
        return None
    for team in teams:
        team_id = str(team.get("team_id") or "").strip()
        alias = str(
            team.get("team_alias") or team.get("team_name") or "",
        ).strip()
        if team_id.casefold() == needle or alias.casefold() == needle:
            return team_id or alias
    return None


def build_key_generate_body(
    *,
    key_alias: str,
    models: list[str] | None,
    team_id: str | None,
    max_parallel_requests: int | None,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """`POST /key/generate` JSON. TPM/RPM yok."""
    body: dict[str, object] = {
        "key_alias": key_alias,
        "models": list(models or []),
        "metadata": dict(metadata or {}),
    }
    if team_id and team_id.strip():
        body["team_id"] = team_id.strip()
    if max_parallel_requests is not None:
        body["max_parallel_requests"] = int(max_parallel_requests)
    return body


__all__ = [
    "TEAM_LIST_PATH",
    "build_key_generate_body",
    "match_team_id",
    "parse_team_list",
]
