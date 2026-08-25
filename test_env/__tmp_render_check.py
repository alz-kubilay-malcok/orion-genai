"""Smoke test for `backend.src.core.mailing.render_template`.

5 şablon için:
- valid template load (var mı, debug-resolved mı)
- $placeholder escape (XSS)
- #if/$key ... #else/$key ... #end blok çözümü
- _unescaped bayrakla raw HTML pass-through

Çalıştır:
    powershell -NoProfile -Command "& 'C:/Users/kubilay.malcok/.pyenv/pyenv-win/versions/3.14.0/python.exe' 'test_env/__tmp_render_check.py'"
"""

import sys
from pathlib import Path
import re

# Repo src ağacının python sys.path'ine eklenmesi (`pip install -e` ile değil,
# ad-hoc script için).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from core.mailing import render_template  # noqa: E402

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "backend" / "src" / "core" / "mailing" / "templates"


def test_litellm_approval() -> None:
    out = render_template(
        "litellm_key_approval",
        approver_name="Burak",
        ticket_id="ORION-9001",
        requester_name='<script>alert("x")</script>',
        requester_email="alice@a.com",
        department_name="Claims",
        environment="PROD",
        purpose="Prod özetleme",
        models="gpt-4o, llama3",
        max_concurrent_requests="120",
        estimated_peak_tpm="8000",
        estimated_peak_rpm="900",
        created_at="2026-01-15",
        approve_link="https://panel/approve?token=abc",
        reject_link="https://panel/reject?token=abc",
        request_version="3",
        action_token_ttl_hours="48",
    )
    assert "GenAi Key Dispatcher" in out
    assert "&lt;script&gt;alert" in out, "XSS escape başarısız"
    assert "<span class=\"pill\">PROD</span>" in out
    assert "https://panel/approve?token=abc" in out
    assert "ORION-9001" in out
    assert "<!-- unresolved" not in out, "hayalet unresolved bırakmadı"
    print("DEBUG: Unresolved placeholders:", re.findall(r"\$[a-zA-Z_][a-zA-Z0-9_]*", out))


def test_litellm_result_approved() -> None:
    out = render_template(
        "litellm_key_result",
        requester_name="Deniz",
        ticket_id="ORION-9002",
        environment="DEV",
        models="gpt-4o-mini",
        outcome_class="approved",
        outcome_label="onaylandı",
        key_alias="dev-alias",
        tpm_approved="100k",
        rpm_approved="60",
        expires_at="2026-02-14",
        claim_link="https://panel/claim?token=xyz",
        completed_at="2026-01-15 11:32",
        approved=True,
        rejected=False,
    )
    assert "onaylandı" in out
    assert "dev-alias" in out
    assert "claim_link" not in out, "raw placeholder kalmış olabilir"  # örnek $claim_link çıktıda
    assert "Anahtarımı talep et" in out
    assert "Red sebebi" not in out
    assert "<!-- unresolved" not in out


def test_litellm_result_rejected() -> None:
    out = render_template(
        "litellm_key_result",
        requester_name="Deniz",
        ticket_id="ORION-9003",
        environment="DEV",
        models="gpt-4o-mini",
        outcome_class="rejected",
        outcome_label="reddedildi",
        reject_reason="Paylaşımlı hesap istemiyoruz",
        completed_at="2026-01-15 11:35",
        approved=False,
        rejected=True,
    )
    assert "reddedildi" in out
    assert "Red sebebi" in out
    assert "Anahtarımı talep et" not in out, "red template'i claim link göstermemeli"
    assert "<!-- unresolved" not in out


def test_mcp_approval_tools_rows_unescaped() -> None:
    out = render_template(
        "mcp_key_approval",
        approver_name="Burak",
        ticket_id="ORION-9004",
        requester_name="Rıdvan",
        requester_email="r@b.com",
        department_name="Pricing",
        environment="STG",
        server_display_name="Claims DB",
        server_slug="claims-db",
        all_tools_label="Hayır (seçili 3 araç)",
        created_at="2026-01-15",
        approve_link="https://panel/approve?token=zzz",
        reject_link="https://panel/reject?token=zzz",
        request_version="1",
        action_token_ttl_hours="12",
        tools_rows=(
            "<tr><td>fetch_claim</td><td>Claim getirir</td></tr>"
            "<tr><td>post_note</td><td>Not ekler</td></tr>"
        ),
        _unescaped={"tools_rows"},
    )
    assert "<tr><td>fetch_claim</td><td>Claim getirir</td></tr>" in out
    assert "&lt;tr&gt;&lt;td&gt;fetch_claim" not in out, "tools_rows escape edilmiş"
    assert "Hayır (seçili 3 araç)" in out


def test_revised_diff_unescaped_rows() -> None:
    out = render_template(
        "revised_diff",
        requester_name="Rıdvan",
        ticket_id="ORION-9005",
        diff_rows=(
            "<tr class=\"changed\"><th>modeller</th>"
            "<td>gpt-4o, llama3</td><td>gpt-4o, mistral</td></tr>"
        ),
        completed_at="2026-01-15 11:50",
        _unescaped={"diff_rows"},
    )
    assert "<tr class=\"changed\"><th>modeller</th>" in out
    assert "<!-- unresolved" not in out


def test_unknown_template_raises() -> None:
    try:
        render_template("does_not_exist", foo="bar")
    except FileNotFoundError:
        return
    raise AssertionError("FileNotFoundError atmadı")


if __name__ == "__main__":
    test_litellm_approval()
    print("✓ litellm_key_approval — XSS escape + link geçerli")
    test_litellm_result_approved()
    print("✓ litellm_key_result (approved) — claim link + key alias görünür")
    test_litellm_result_rejected()
    print("✓ litellm_key_result (rejected) — reject_reason görünür, claim link gizli")
    test_mcp_approval_tools_rows_unescaped()
    print("✓ mcp_key_approval — $tools_rows raw HTML olarak geçti")
    test_revised_diff_unescaped_rows()
    print("✓ revised_diff — $diff_rows raw HTML olarak geçti")
    test_unknown_template_raises()
    print("✓ missing template dosyası FileNotFoundError fırlatır")
    print(f"\nTemplates dir: {TEMPLATES_DIR}")
    print("PASS — 5/5")
