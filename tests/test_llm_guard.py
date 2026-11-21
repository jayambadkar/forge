"""The reviewer can suggest. It cannot invent a close, and bad JSON is dropped."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "system"))

from forge_engine.llm import apply_guard, content_hash, validate_suggestion  # noqa: E402


def test_hash_is_stable():
    payload = {"case_id": "b-1", "notes": ["z", "a"]}
    assert content_hash(payload) == content_hash({"notes": ["z", "a"], "case_id": "b-1"})


def test_low_confidence_and_unknown_evidence_are_dropped():
    allowed = {"al-1", "ev-1"}
    low = {
        "verdict": "RFI",
        "reason_code": "INVOICE_REQUIRED",
        "reason": "Ask for the invoice.",
        "evidence": ["ev-1"],
        "confidence": 0.4,
    }
    assert validate_suggestion(low, allowed) is None
    unknown = dict(low, confidence=0.95, evidence=["ev-missing"])
    assert validate_suggestion(unknown, allowed) is None
    bad_code = dict(low, confidence=0.95, reason_code="NOT_A_CODE")
    assert validate_suggestion(bad_code, allowed) is None


def test_close_cannot_override_rules():
    suggestion = {
        "verdict": "CLOSE",
        "reason_code": "EXPECTED_ACTIVITY",
        "reason": "Looks fine.",
        "evidence": ["al-1"],
        "confidence": 0.99,
    }
    checked = validate_suggestion(suggestion, {"al-1"})
    assert checked is not None
    assert apply_guard("ESCALATE", checked) is None
    assert apply_guard("CLOSE", checked)["verdict"] == "CLOSE"


def test_valid_rfi_is_kept_as_a_suggestion_only():
    suggestion = {
        "verdict": "RFI",
        "reason_code": "INVOICE_REQUIRED",
        "reason": "Ask the customer for the invoice covering the timber.",
        "evidence": ["al-1"],
        "confidence": 0.91,
    }
    checked = validate_suggestion(suggestion, {"al-1"})
    assert apply_guard("ESCALATE", checked)["verdict"] == "RFI"
