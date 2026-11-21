"""Schema, determinism, and verdict-mix checks for one institution folder."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "system"))

from forge_engine.codes import verdict_for  # noqa: E402
from forge_engine.load import load_institution  # noqa: E402

REQUIRED = ("case_id", "alert_ids", "verdict", "reason_code", "reason", "evidence")


def _sentences(reason: str) -> list[str]:
    import re

    return [part for part in re.split(r"(?<=[.!?])\s+(?=[A-Z])", reason.strip()) if part.strip()]


def validate(folder: Path, output: Path) -> list[str]:
    institution = load_institution(folder)
    errors = []
    seen = []
    text = output.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: {exc}")
            continue
        seen.append(row.get("case_id"))
        if tuple(row) != REQUIRED and set(row) != set(REQUIRED):
            errors.append(f"{row.get('case_id')}: keys {sorted(row)}")
        verdict = row.get("verdict")
        code = row.get("reason_code")
        if verdict_for(code) != verdict:
            errors.append(f"{row.get('case_id')}: {code} is not a {verdict} code")
        missing = [item for item in row.get("evidence", []) if item not in institution.all_ids]
        if missing:
            errors.append(f"{row.get('case_id')}: unknown evidence {missing}")
        count = len(_sentences(row.get("reason", "")))
        if not 2 <= count <= 4:
            errors.append(f"{row.get('case_id')}: {count} sentences")
        if verdict == "RFI" and "Ask " not in row.get("reason", ""):
            errors.append(f"{row.get('case_id')}: RFI does not say what to ask")
    expected_ids = [case.id for case in institution.cases]
    if seen != expected_ids:
        errors.append(f"case id sequence differs: missing {set(expected_ids) - set(seen)}")
    return errors


def distribution(output: Path) -> Counter:
    counts: Counter = Counter()
    for line in output.read_text(encoding="utf-8").splitlines():
        counts[json.loads(line)["verdict"]] += 1
    return counts


def deterministic(folder: Path, work: Path) -> bool:
    runner = ROOT / "system" / "run"
    first = work / "first.jsonl"
    second = work / "second.jsonl"
    for target in (first, second):
        subprocess.run([sys.executable, str(runner), str(folder), str(target)], check=True, cwd=work)
    return first.read_bytes() == second.read_bytes()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python eval/harness.py <institution_folder> <output.jsonl>", file=sys.stderr)
        return 2
    folder = Path(argv[0]).resolve()
    output = Path(argv[1]).resolve()
    errors = validate(folder, output)
    print("distribution", dict(distribution(output)))
    same = deterministic(folder, output.parent)
    print("deterministic", same)
    if errors or not same:
        for error in errors:
            print("error", error)
        return 1
    print("ok", folder.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
