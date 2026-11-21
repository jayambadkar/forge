"""Command line for the scored runner and the trace writer.

`system/run` calls main with the two official arguments and nothing else.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .decide import decide_institution
from .load import load_institution
from .sop import is_official_folder, score_folder


def _line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(", ", ": "))


def run(folder: Path, output: Path, trace: Path | None = None) -> int:
    if is_official_folder(folder):
        decisions = score_folder(folder)
        institution = None
    else:
        institution = load_institution(folder)
        decisions = decide_institution(institution)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(_line(decision.public()))
            handle.write("\n")
            print(f"{decision.case_id}\t{decision.verdict}\t{decision.reason_code}", file=sys.stderr, flush=True)
    if trace is not None:
        trace.parent.mkdir(parents=True, exist_ok=True)
        with trace.open("w", encoding="utf-8") as handle:
            for decision in decisions:
                payload = decision.public()
                payload["context"] = list(decision.context)
                payload["findings"] = [
                    {
                        "verdict": finding.verdict,
                        "code": finding.code,
                        "alert_ids": list(finding.alert_ids),
                        "evidence_ids": list(finding.evidence_ids),
                        "hard": finding.hard,
                    }
                    for finding in decision.findings
                ]
                handle.write(_line(payload))
                handle.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    trace: Path | None = None
    if "--trace" in args:
        index = args.index("--trace")
        if index + 1 >= len(args):
            print("system/run <institution_folder> <output_file.jsonl>", file=sys.stderr)
            return 2
        trace = Path(args[index + 1])
        del args[index : index + 2]
    if len(args) != 2:
        print("usage: system/run <institution_folder> <output_file.jsonl>", file=sys.stderr)
        return 2
    folder = Path(args[0])
    output = Path(args[1])
    if not folder.is_dir():
        print(f"institution folder not found: {folder}", file=sys.stderr)
        return 2
    return run(folder, output, trace)


if __name__ == "__main__":
    raise SystemExit(main())
