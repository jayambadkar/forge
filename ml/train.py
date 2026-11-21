# mypy: disable-error-code="no-untyped-def"
"""Grouped cross-validation of a risk model trained on SOP labelling functions.

The label is the rules verdict. Metrics measure agreement with that function,
not with the hidden test set. The model is not loaded by system/run.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, recall_score
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "system"))

from forge_engine.features import BEHAVIOURAL, FEATURE_NAMES, labelled_rows  # noqa: E402
from forge_engine.load import load_institution  # noqa: E402

BOOKS = ("bank", "emoney", "investment", "payments_fx")
SEED = 42


def _matrix(rows: list[dict], names: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.array([[row["features"][name] for name in names] for row in rows], dtype=float)
    y = np.array([row["verdict"] for row in rows])
    groups = np.array([row["group"] for row in rows])
    return x, y, groups


def _splits(y: np.ndarray, groups: np.ndarray):
    notes: list[str] = []
    n_groups = len(set(groups))
    counts = Counter(y.tolist())
    smallest = min(counts.values()) if counts else 0
    stratified = min(5, smallest, n_groups)
    if stratified >= 2:
        splitter = StratifiedGroupKFold(n_splits=stratified, shuffle=True, random_state=SEED)
        return splitter.split(np.zeros(len(y)), y, groups), {
            "method": "StratifiedGroupKFold",
            "n_splits": stratified,
            "grouped_by": "institution::customer",
            "class_counts": dict(counts),
            "notes": notes,
        }
    n_group = min(3, n_groups)
    notes.append(
        f"StratifiedGroupKFold needs at least 2 groups in every class; the smallest class has {smallest}. "
        f"Fell back to GroupKFold with {n_group} splits. Customers still do not cross the fold boundary."
    )
    if n_group < 2:
        return None, {
            "method": "none",
            "n_splits": 0,
            "grouped_by": "institution::customer",
            "class_counts": dict(counts),
            "notes": notes + ["Too few customer groups to cross-validate."],
        }
    splitter = GroupKFold(n_splits=n_group)
    return splitter.split(np.zeros(len(y)), y, groups), {
        "method": "GroupKFold",
        "n_splits": n_group,
        "grouped_by": "institution::customer",
        "class_counts": dict(counts),
        "notes": notes,
    }


def _models():
    logistic = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=400, random_state=SEED),
    )
    boosting = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.1, max_iter=80, random_state=SEED)
    return (("logistic_regression", logistic), ("hist_gradient_boosting", boosting))


def _score(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    labels = ["CLOSE", "RFI", "ESCALATE"]
    present = [label for label in labels if label in set(y_true) or label in set(y_pred)]
    per_class = {}
    for label in present:
        per_class[label] = round(
            float(recall_score(y_true, y_pred, labels=[label], average="macro", zero_division=0)), 4
        )
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, average="macro", labels=present, zero_division=0)), 4),
        "recall": per_class,
        "n": int(len(y_true)),
    }


def evaluate(rows: list[dict], names: tuple[str, ...]) -> dict:
    if len(rows) < 4:
        return {"error": "not enough rows", "n": len(rows)}
    x, y, groups = _matrix(rows, names)
    splits, meta = _splits(y, groups)
    report = {"features": list(names), "split": meta, "models": {}}
    if splits is None:
        return report
    # Materialise splits once so every model sees the same folds.
    folds = list(splits)
    for model_name, _ in _models():
        predictions = np.empty(len(y), dtype=object)
        failed = 0
        for train, test in folds:
            if len(set(y[train])) < 2:
                predictions[test] = "ESCALATE"
                failed += 1
                continue
            model = dict(_models())[model_name]
            model.fit(x[train], y[train])
            predictions[test] = model.predict(x[test])
        block = _score(y, predictions)
        block["folds_missing_a_class"] = failed
        report["models"][model_name] = block
    # Coefficients on the full slice are descriptive. They are not a CV score.
    if len(set(y)) >= 2:
        logistic = dict(_models())["logistic_regression"]
        logistic.fit(x, y)
        classifier = logistic.named_steps["logisticregression"]
        # Binary-looking shape when there are 2 classes; otherwise one row per class.
        coefs = classifier.coef_
        classes = list(classifier.classes_)
        report["logistic_coefficients_full_fit"] = {
            "warning": "Fit on every row in this slice, including what CV held out. Illustrative only.",
            "classes": classes,
            "weights": {
                classes[index]: {feature: round(float(weight), 4) for feature, weight in zip(names, coefs[index], strict=False)}
                for index in range(len(classes))
            },
        }
    return report


def load_rows() -> list[dict]:
    official = ROOT / "data" / "hackathon" / "institutions"
    demo = ROOT / "fixtures" / "demo" / "institutions"
    base = official if (official / "bank" / "cases.jsonl").is_file() else demo
    rows = []
    for name in BOOKS:
        folder = base / name
        if not folder.is_dir():
            continue
        rows.extend(labelled_rows(load_institution(folder)))
    return rows


def main() -> int:
    rows = load_rows()
    by_institution = {}
    for name in BOOKS:
        subset = [row for row in rows if row["institution"] == name]
        if subset:
            by_institution[name] = {
                "all_features": evaluate(subset, FEATURE_NAMES),
                "behavioural_features_only": evaluate(subset, BEHAVIOURAL),
            }
    report = {
        "label_source": "SOP labelling functions. These metrics are not accuracy against hidden-test labels.",
        "what_this_does_not_do": "The model does not close cases. system/run never loads it.",
        "n_cases": len(rows),
        "book": "official"
        if (ROOT / "data" / "hackathon" / "institutions" / "bank" / "cases.jsonl").is_file()
        else "fixture",
        "institutions": by_institution,
        "pooled": {
            "all_features": evaluate(rows, FEATURE_NAMES),
            "behavioural_features_only": evaluate(rows, BEHAVIOURAL),
        },
    }
    out = ROOT / "ml" / "report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows)} cases, book={report['book']})")
    pooled = cast(dict[str, Any], cast(dict[str, Any], report["pooled"])["all_features"])["models"]
    behavioural = cast(dict[str, Any], cast(dict[str, Any], report["pooled"])["behavioural_features_only"])["models"]
    assert isinstance(pooled, dict)
    assert isinstance(behavioural, dict)
    for name in pooled:
        print(
            f"  {name}: macro-F1 {pooled[name]['macro_f1']} with policy features, "
            f"{behavioural[name]['macro_f1']} on behaviour only"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
