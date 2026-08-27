"""Result-mail placeholder sözleşmesi.

`litellm_key_result.html` / `mcp_key_result.html` — alıcı requester.
`claim_link` boşsa şablon anahtar butonunu gizler (dry-run / registry).
"""

from __future__ import annotations

from typing import Mapping

import html


def _s(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _models_label(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if item is not None)
    text = str(value).strip()
    if text.startswith("(") and text.endswith(")"):
        return text.strip("()").replace("'", "").replace('"', "")
    return text


_RESPONSE_WINDOW_LABELS = {
    "realtime": "Gerçek zamanlı",
    "within_1h": "1 saat içinde",
    "by_17": "Aynı gün saat 17.00'ye kadar",
    "by_next_08": "Ertesi gün saat 08.00'ye kadar",
}
_USAGE_FREQUENCY_LABELS = {
    "0_10": "Günde 0–10 istek",
    "10_100": "Günde 10–100 istek",
    "100_1000": "Günde 100–1.000 istek",
    "1000_10k": "Günde 1.000–10.000 istek",
}


def _response_window_label(value: object) -> str:
    raw = _s(value)
    return _RESPONSE_WINDOW_LABELS.get(raw, raw)


def _usage_frequency_label(value: object) -> str:
    raw = _s(value)
    return _USAGE_FREQUENCY_LABELS.get(raw, raw)


def _change_display(old: object, new: object, *, fmt) -> tuple[str, bool]:
    before = fmt(old)
    after = fmt(new)
    if before == after:
        return after, False
    if not before:
        return after, True
    return f"{before} → {after}", True


def _diff_row(label: str, display: str, changed: bool) -> str:
    cls = ' class="changed"' if changed else ""
    return (
        f"<tr{cls}><th>{html.escape(label)}</th>"
        f"<td>{html.escape(display)}</td></tr>"
    )


def litellm_revision_diff_html(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> str:
    """Requester revize maili: modeller / paralel / yanıt / sıklık, `eski → yeni`."""
    specs = (
        ("Modeller", "models", _models_label),
        ("Anlık paralel istek", "max_concurrent_requests", _s),
        ("Yanıt süresi", "response_window", _response_window_label),
        ("Kullanım sıklığı", "usage_frequency", _usage_frequency_label),
    )
    rows: list[str] = []
    for label, key, fmt in specs:
        display, changed = _change_display(before.get(key), after.get(key), fmt=fmt)
        if not display:
            display = "—"
        rows.append(_diff_row(label, display, changed))
    return "".join(rows)


def _scope_label(request: Mapping[str, object]) -> str:
    if request.get("registry_allows_all_tools"):
        return "Tüm araçlar"
    from backend.src.core.mcp_scopes import scope_label, scopes_from_row

    try:
        scopes = scopes_from_row(
            request.get("mcp_server_slug") or request.get("server_slug"),
            request.get("mcp_tool_names"),
            request.get("all_tools"),
        )
    except ValueError:
        scopes = []
    if scopes:
        return scope_label(scopes)
    if request.get("all_tools"):
        return "Tüm araçlar"
    tools = request.get("mcp_tool_names")
    if isinstance(tools, (list, tuple)) and tools:
        return ", ".join(str(item) for item in tools)
    return _s(tools)


def _outcome(status: str) -> tuple[bool, bool, str, str]:
    if status == "completed":
        return True, False, "approved", "tamamlandı"
    if status == "rejected":
        return False, True, "rejected", "reddedildi"
    return False, False, "", status or "güncellendi"


def litellm_result_inputs(
    request: Mapping[str, object],
    *,
    claim_link: str = "",
    api_key: str = "",
    revision_before: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """`templates/litellm_key_result.html` girdileri."""
    status = _s(request.get("status"))
    approved, rejected, outcome_class, outcome_label = _outcome(status)
    was_revised = bool(revision_before)
    revision_diff = litellm_revision_diff_html(
        revision_before if revision_before else request,
        request,
    )
    return {
        "requester_name": _s(request.get("requester_name")),
        "ticket_id": _s(request.get("genai_orion_panel_ticket_id")),
        "ticket_url": _s(request.get("genai_orion_panel_ticket_url")),
        "environment": _s(request.get("environment")),
        "models": _models_label(request.get("models")),
        "response_window": _response_window_label(request.get("response_window")),
        "usage_frequency": _usage_frequency_label(request.get("usage_frequency")),
        "outcome_class": outcome_class,
        "outcome_label": outcome_label,
        "key_alias": _s(request.get("key_alias")),
        "litellm_team_id": _s(request.get("litellm_team_id") or request.get("department_name")),
        "max_parallel_requests": request.get("max_concurrent_requests") or "",
        "expires_at": _s(request.get("expires_at")),
        "claim_link": claim_link,
        "api_key": api_key,
        "reject_reason": _s(request.get("reject_reason") or request.get("error_message")),
        "completed_at": _s(request.get("completed_at")),
        "approved": approved,
        "rejected": rejected,
        "was_revised": was_revised,
        "revision_diff": revision_diff,
        "_unescaped": ("revision_diff",),
    }


def mcp_result_inputs(
    request: Mapping[str, object],
    *,
    claim_link: str = "",
    api_key: str = "",
) -> dict[str, object]:
    """`templates/mcp_key_result.html` — MCP key ve registry özeti."""
    status = _s(request.get("status"))
    approved, rejected, outcome_class, outcome_label = _outcome(status)
    return {
        "requester_name": _s(request.get("requester_name")),
        "ticket_id": _s(request.get("genai_orion_panel_ticket_id")),
        "ticket_url": _s(request.get("genai_orion_panel_ticket_url")),
        "environment": _s(request.get("environment")),
        "server_display_name": _s(
            request.get("mcp_server_display_name") or request.get("server_display_name"),
        ),
        "server_slug": _s(request.get("mcp_server_slug") or request.get("server_slug")),
        "outcome_class": outcome_class,
        "outcome_label": outcome_label,
        "key_alias": _s(request.get("key_alias")),
        "scope_label": _scope_label(request),
        "expires_at": _s(request.get("expires_at")),
        "claim_link": claim_link,
        "api_key": api_key,
        "reject_reason": _s(request.get("reject_reason") or request.get("error_message")),
        "completed_at": _s(request.get("completed_at")),
        "approved": approved,
        "rejected": rejected,
    }


def result_template_name(request_type: str) -> str:
    if request_type == "litellm_key":
        return "litellm_key_result"
    return "mcp_key_result"


__all__ = [
    "litellm_result_inputs",
    "litellm_revision_diff_html",
    "mcp_result_inputs",
    "result_template_name",
]
