"""SOP scenarios. Expected verdicts are derived from the fixture policies, not from a labelled dev set."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fixtures"))
sys.path.insert(0, str(ROOT / "system"))

from build_book import build  # noqa: E402
from forge_engine.decide import decide_case  # noqa: E402
from forge_engine.load import load_institution  # noqa: E402
from forge_engine.policy_text import parse_policy  # noqa: E402

BOOK = ROOT / "fixtures" / "demo" / "institutions"


@pytest.fixture(scope="module")
def expected():
    return build()


def _sentences(reason: str) -> list[str]:
    import re

    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", reason.strip())
    return [part for part in parts if part.strip()]


def test_policy_numbers_come_from_the_sop(expected):
    bank = parse_policy((BOOK / "bank" / "POLICY.md").read_text(encoding="utf-8"))
    fx = parse_policy((BOOK / "payments_fx" / "POLICY.md").read_text(encoding="utf-8"))
    emoney = parse_policy((BOOK / "emoney" / "POLICY.md").read_text(encoding="utf-8"))
    investment = parse_policy((BOOK / "investment" / "POLICY.md").read_text(encoding="utf-8"))
    assert bank.own_account_multiple == 5
    assert bank.cash_escalate_gbp == 8000
    assert bank.allows_expected_activity
    assert fx.requirements[0].keyword == "invoice"
    assert fx.requirements[0].threshold_gbp == 10000
    assert fx.requirements[0].direction == "out"
    assert emoney.requirements[0].keyword == "source of funds"
    assert emoney.requirements[0].threshold_gbp == 5000
    assert emoney.requirements[0].direction == "in"
    assert investment.requirements[0].threshold_gbp == 25000


def test_every_scenario_matches_the_sop(expected):
    for institution, cases in expected.items():
        loaded = load_institution(BOOK / institution)
        by_id = {case.id: case for case in loaded.cases}
        assert set(by_id) == set(cases)
        for case_id, target in cases.items():
            decision = decide_case(loaded, by_id[case_id])
            assert decision.verdict == target["verdict"], (case_id, decision.reason)
            assert decision.reason_code == target["reason_code"], (case_id, decision.reason)
            assert set(decision.evidence) <= loaded.all_ids
            assert decision.evidence
            sentences = _sentences(decision.reason)
            assert 2 <= len(sentences) <= 4, (case_id, sentences)
            if decision.verdict == "RFI":
                assert "Ask " in decision.reason
            if case_id in {"b-context", "b-expected"}:
                assert "not used as a ground" in decision.reason


def test_context_does_not_close_or_decide_the_code(expected):
    loaded = load_institution(BOOK / "bank")
    case = next(item for item in loaded.cases if item.id == "b-context")
    decision = decide_case(loaded, case)
    assert decision.verdict == "ESCALATE"
    assert decision.reason_code == "ACTIVITY_UNEXPLAINED"
    assert "dev-shared" not in decision.reason_code


def test_system_run_is_deterministic(expected, tmp_path):
    folder = BOOK / "payments_fx"
    first = tmp_path / "a.jsonl"
    second = tmp_path / "b.jsonl"
    runner = ROOT / "system" / "run"
    for target in (first, second):
        completed = subprocess.run(
            [sys.executable, str(runner), str(folder), str(target)],
            check=False,
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert completed.returncode == 0, completed.stderr
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(expected["payments_fx"])
    for row in rows:
        assert row["verdict"] == expected["payments_fx"][row["case_id"]]["verdict"]
        assert set(row) == {"case_id", "alert_ids", "verdict", "reason_code", "reason", "evidence"}
