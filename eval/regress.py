#!/usr/bin/env python3
"""Diff two scored output folders, one JSONL file per institution.

Prints how many cases moved, grouped by old verdict and reason code to the new
ones. A case that is only in one folder is listed as missing. Exit status is 0
even when cases moved: this is a report, not a gate.

    python3 eval/regress.py previous/ output/
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def _load(folder: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if not folder.is_dir():
        raise SystemExit(f"not a folder: {folder}")
    files = sorted(folder.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"no jsonl in {folder}")
    for path in files:
        institution = path.stem
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SystemExit(f"{path}:{line_number}: {exc}") from exc
                case_id = row.get("case_id")
                if not case_id:
                    raise SystemExit(f"{path}:{line_number}: missing case_id")
                row["_institution"] = institution
                if case_id in rows:
                    raise SystemExit(f"duplicate case_id {case_id} in {folder}")
                rows[case_id] = row
    return rows


def _label(row: dict) -> str:
    return f"{row.get('verdict')} {row.get('reason_code')}"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python3 eval/regress.py <previous_folder> <new_folder>", file=sys.stderr)
        return 2
    previous = _load(Path(argv[1]))
    current = _load(Path(argv[2]))
    transitions: Counter[tuple[str, str]] = Counter()
    missing_now = []
    missing_before = []
    for case_id, old in previous.items():
        new = current.get(case_id)
        if new is None:
            missing_now.append(case_id)
            continue
        if old.get("verdict") != new.get("verdict") or old.get("reason_code") != new.get("reason_code"):
            transitions[(_label(old), _label(new))] += 1
    for case_id in current:
        if case_id not in previous:
            missing_before.append(case_id)
    moved = sum(transitions.values())
    print(f"{len(previous)} previous, {len(current)} new, {moved} changed")
    if missing_now:
        print(f"missing from new: {len(missing_now)}")
    if missing_before:
        print(f"only in new: {len(missing_before)}")
    width = max((len(f"{old} -> {new}") for old, new in transitions), default=20)
    for (old, new), count in transitions.most_common():
        print(f"{count:5}  {old} -> {new}".ljust(width + 8))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
