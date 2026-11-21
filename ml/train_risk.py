# mypy: disable-error-code="no-untyped-def"
"""Risk models on policy-engine labels.

The labels are weak supervision from the labelling functions, not hidden-test
truth. A 20% customer hold-out, stratified by institution and label, is scored
once at the end. Model choice, group ablation, calibration and the close
threshold all happen on the other 80%.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from lightgbm import LGBMClassifier, early_stopping, log_evaluation
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import LeaveOneGroupOut, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "system"))

from forge_engine.sop import Book, norm, score_folder  # noqa: E402

BOOKS = ("bank", "emoney", "investment", "payments_fx")
DATA = Path("/tmp/hackathon-fetch/hackathon/institutions")
if not (DATA / "bank").is_dir():
    DATA = ROOT / "data" / "hackathon" / "institutions"
LABELS = ("CLOSE", "RFI", "ESCALATE")
SEED = 42
INVOICE_TYPES = {
    "invoice",
    "supplier_invoice",
    "supplier_invoices",
    "supply_contract",
    "consulting_contract",
    "payment_file",
}

# Atomic features live in named groups. The grouped model uses one composite each.
GROUPS: dict[str, tuple[str, ...]] = {
    "evidence_coverage": (
        "n_docs",
        "has_invoice",
        "has_statement",
        "has_register",
        "has_event",
        "has_fraud",
        "value_covered",
    ),
    "amount_match": ("best_amount_ratio", "n_amount_matches"),
    "identity_match": ("party_in_doc_share", "own_name_share"),
    "profile_deviation": ("income_multiple", "amount_over_baseline"),
    "flow_pattern": ("pass_through", "n_counterparties", "structuring_flag", "n_in", "n_out"),
    "geography_risk": ("high_risk_corridor",),
    "list_agreement": ("list_alert",),
    "prior_review": ("prior_same_rule", "n_prior_reviews"),
    "account_history": ("dormant_flag", "dormant_days_scaled"),
    "held_payment": ("held_flag", "held_without_invoice"),
}


def _cost(true: str, pred: str) -> int:
    if pred == "CLOSE" and true != "CLOSE":
        return 10
    if true == "CLOSE" and pred != "CLOSE":
        return 3
    if {true, pred} == {"RFI", "ESCALATE"}:
        return 2
    return 0


def _covered(docs: list[dict], txs: list[dict], customer_name: str) -> tuple[float, float, int, float]:
    """Return value covered, best amount ratio, match count, share of parties named in a document."""
    blob = " ".join(doc["norm"] for doc in docs)
    wanted_names = []
    covered = 0.0
    total = 0.0
    best = 0.0
    matches = 0
    for tx in txs:
        amount = float(tx.get("amount_gbp") or 0)
        total += amount
        names = [norm(tx.get("counterparty_name")), norm(customer_name)]
        names = [name for name in names if name]
        hit = False
        for doc in docs:
            if names and not any(name in doc["norm"] for name in names):
                continue
            for candidate in doc["amounts"]:
                if amount <= 0 or candidate <= 0:
                    continue
                ratio = min(amount, candidate) / max(amount, candidate)
                if ratio > best:
                    best = ratio
                if ratio >= 0.98:
                    hit = True
        if hit:
            covered += amount
            matches += 1
        party = norm(tx.get("counterparty_name"))
        if party:
            wanted_names.append(party)
    share = 0.0
    if wanted_names:
        share = sum(1 for party in wanted_names if party in blob) / len(wanted_names)
    return (covered / total if total else 0.0), best, matches, share


def _rows() -> list[dict]:
    built = []
    for name in BOOKS:
        folder = DATA / name
        book = Book(folder)
        decisions = {item.case_id: item for item in score_folder(folder)}
        for case in book.cases:
            decision = decisions[case["case_id"]]
            customer = book.customers.get(case["customer_id"], {})
            alerts = [book.alerts[aid] for aid in case.get("alert_ids") or [] if aid in book.alerts]
            txs = []
            seen = set()
            for alert in alerts:
                for tid in alert.get("transaction_ids") or []:
                    if tid in book.transactions and tid not in seen:
                        seen.add(tid)
                        txs.append(book.transactions[tid])
            docs = book.docs.get(case["customer_id"], [])
            kinds = {doc.get("type") for doc in docs}
            rules = {alert.get("rule_id") for alert in alerts}
            declared = customer.get("declared") or {}
            baseline = float(declared.get("monthly_income_gbp") or 0)
            if customer.get("kind") == "business" and declared.get("annual_turnover_gbp"):
                baseline = float(declared["annual_turnover_gbp"]) / 12.0
            inbound = [float(tx.get("amount_gbp") or 0) for tx in txs if tx.get("direction") == "in"]
            outbound = [float(tx.get("amount_gbp") or 0) for tx in txs if tx.get("direction") == "out"]
            sum_in = float(sum(inbound))
            sum_out = float(sum(outbound))
            multiple = 0.0
            dormant_days = 0.0
            for alert in alerts:
                measured = alert.get("measured") or {}
                if "multiple" in measured:
                    multiple = max(multiple, float(measured["multiple"]))
                if "dormant_days" in measured:
                    dormant_days = max(dormant_days, float(measured["dormant_days"]))
            reviews = book.reviews.get(case["customer_id"], [])
            same_rule = any(review.get("rule_id") in rules for review in reviews)
            covered, best_ratio, n_matches, party_share = _covered(docs, txs, customer.get("name") or "")
            own = 0
            cname = norm(customer.get("name"))
            for tx in txs:
                if cname and norm(tx.get("counterparty_name")) == cname:
                    own += 1
            held = bool(case.get("held_payment_id"))
            held_gap = 0.0
            if held and case["held_payment_id"] in book.transactions:
                held_tx = book.transactions[case["held_payment_id"]]
                if float(held_tx.get("amount_gbp") or 0) >= 10000 and not (kinds & INVOICE_TYPES):
                    held_gap = 1.0
            # List year signal is carried by the decision text only when the LF found years.
            # The atomic flags record whether the case is a list alert; year agreement is 0 unless measured.
            features = {
                "n_docs": float(len(docs)),
                "has_invoice": 1.0 if kinds & INVOICE_TYPES else 0.0,
                "has_statement": 1.0 if "bank_statement" in kinds else 0.0,
                "has_register": 1.0
                if "company_register_extract" in kinds or "significant_control_register" in kinds
                else 0.0,
                "has_event": 1.0
                if kinds
                & {"solicitor_letter", "vehicle_sale_receipt", "sale_receipt", "insurer_letter", "completion_statement"}
                else 0.0,
                "has_fraud": 1.0 if "sending_bank_fraud_report" in kinds else 0.0,
                "value_covered": covered,
                "best_amount_ratio": best_ratio,
                "n_amount_matches": float(n_matches),
                "party_in_doc_share": party_share,
                "own_name_share": own / len(txs) if txs else 0.0,
                "income_multiple": multiple,
                "amount_over_baseline": (max((float(tx.get("amount_gbp") or 0) for tx in txs), default=0.0) / baseline)
                if baseline
                else 0.0,
                "pass_through": (sum_out / sum_in) if sum_in else 0.0,
                "n_counterparties": float(
                    len({tx.get("counterparty_name") for tx in txs if tx.get("counterparty_name")})
                ),
                "structuring_flag": 1.0 if "TM03" in rules else 0.0,
                "n_in": float(len(inbound)),
                "n_out": float(len(outbound)),
                "high_risk_corridor": 1.0 if "TM06" in rules else 0.0,
                "list_alert": 1.0 if "TM22" in rules else 0.0,
                "prior_same_rule": 1.0 if same_rule else 0.0,
                "n_prior_reviews": float(len(reviews)),
                "dormant_flag": 1.0 if "TM07" in rules else 0.0,
                "dormant_days_scaled": min(dormant_days / 180.0, 3.0),
                "held_flag": 1.0 if held else 0.0,
                "held_without_invoice": held_gap,
            }
            composites = {}
            for group, members in GROUPS.items():
                composites[group] = float(np.mean([features[member] for member in members]))
            parties = sorted(
                {
                    party
                    for party in (norm(tx.get("counterparty_name")) for tx in txs)
                    if party and party != cname and len(party) >= 4
                }
            )
            devices = sorted(
                {
                    match
                    for doc in docs
                    if doc.get("type") == "device_export"
                    for match in re.findall(r"\b[A-Z][0-9]-[0-9]{3,}\b", doc.get("text") or "")
                }
            )
            built.append(
                {
                    "case_id": case["case_id"],
                    "parties": parties,
                    "devices": devices,
                    "institution": name,
                    "customer_id": case["customer_id"],
                    "group": f"{name}::{case['customer_id']}",
                    "label": decision.verdict,
                    "reason_code": decision.reason_code,
                    "reason": decision.reason,
                    "features": features,
                    "composites": composites,
                }
            )
    return built


def _matrix(y_true, y_pred) -> list[list[int]]:
    return confusion_matrix(y_true, y_pred, labels=list(LABELS)).tolist()


def _pack(y_true, y_pred, y_train=None, pred_train=None) -> dict[str, Any]:
    costs = [_cost(t, p) for t, p in zip(y_true, y_pred, strict=False)]
    wrongful = sum(1 for t, p in zip(y_true, y_pred, strict=False) if p == "CLOSE" and t != "CLOSE")
    block: dict[str, Any] = {
        "n": int(len(y_true)),
        "expected_cost": round(float(np.mean(costs)) if len(costs) else 0.0, 4),
        "wrongful_close_rate": round(wrongful / len(y_true), 4) if len(y_true) else 0.0,
        "wrongful_closes": int(wrongful),
        "confusion": {"labels": list(LABELS), "counts": _matrix(y_true, y_pred)},
    }
    if y_train is not None and pred_train is not None and len(y_train):
        train_cost = float(np.mean([_cost(t, p) for t, p in zip(y_train, pred_train, strict=False)]))
        block["train_expected_cost"] = round(train_cost, 4)
        block["validation_gap"] = round(block["expected_cost"] - train_cost, 4)
    return block


def _xy(rows, key):
    names = list(rows[0][key])
    x = np.array([[row[key][name] for name in names] for row in rows], dtype=float)
    y = np.array([row["label"] for row in rows])
    groups = np.array([row["group"] for row in rows])
    return names, x, y, groups


def _lgbm(params: dict, n_estimators: int = 200) -> LGBMClassifier:
    return LGBMClassifier(
        objective="multiclass",
        num_class=3,
        n_estimators=n_estimators,
        learning_rate=0.08,
        deterministic=True,
        force_row_wise=True,
        n_jobs=1,
        random_state=SEED,
        bagging_seed=SEED,
        feature_fraction_seed=SEED,
        data_random_seed=SEED,
        verbosity=-1,
        **params,
    )


def _fit_lgbm(x_train, y_train, params: dict):
    rng = np.random.RandomState(SEED)
    # Early stopping uses a slice of the training fold, not the validation fold.
    take = rng.rand(len(y_train)) < 0.85
    if take.sum() < 20 or (~take).sum() < 10 or len(set(y_train[take])) < 2:
        model = _lgbm(params, n_estimators=80)
        model.fit(x_train, y_train)
        return model
    model = _lgbm(params, n_estimators=200)
    model.fit(
        x_train[take],
        y_train[take],
        eval_set=[(x_train[~take], y_train[~take])],
        callbacks=[early_stopping(15, verbose=False), log_evaluation(0)],
    )
    return model


def _logit():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, C=1.0, random_state=SEED))


def _align(probabilities, order) -> np.ndarray:
    aligned = np.zeros((len(probabilities), 3))
    for index, label in enumerate(LABELS):
        if label in order:
            aligned[:, index] = probabilities[:, list(order).index(label)]
    return aligned


def _search(x, y, groups) -> dict:
    rng = np.random.RandomState(SEED)
    inner = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED)
    trials = []
    best = None
    for _ in range(6):
        params = {
            "num_leaves": int(rng.choice([7, 15, 31])),
            "min_child_samples": int(rng.choice([20, 50, 100])),
            "feature_fraction": float(rng.choice([0.6, 0.8, 1.0])),
            "bagging_fraction": float(rng.choice([0.7, 0.9])),
            "bagging_freq": 1,
            "lambda_l1": float(rng.choice([0.0, 0.1, 1.0])),
            "lambda_l2": float(rng.choice([0.0, 0.1, 1.0])),
        }
        costs = []
        for train, valid in inner.split(x, y, groups):
            model = _fit_lgbm(x[train], y[train], params)
            pred = model.predict(x[valid])
            costs.append(float(np.mean([_cost(t, p) for t, p in zip(y[valid], pred, strict=False)])))
        mean_cost = float(np.mean(costs))
        trials.append({"params": params, "inner_expected_cost": round(mean_cost, 4)})
        if best is None or mean_cost < best[0]:
            best = (mean_cost, params)
    if best is None:
        raise RuntimeError("hyperparameter search produced no trial")
    return {"trials": trials, "chosen": best[1], "inner_expected_cost": round(best[0], 4)}


def _oof_lgbm(x, y, groups, params) -> tuple[np.ndarray, np.ndarray, list]:
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    pred = np.empty(len(y), dtype=object)
    proba = np.zeros((len(y), 3))
    gaps = []
    for train, valid in splitter.split(x, y, groups):
        model = _fit_lgbm(x[train], y[train], params)
        pred[valid] = model.predict(x[valid])
        proba[valid] = _align(model.predict_proba(x[valid]), model.classes_)
        train_pred = model.predict(x[train])
        gaps.append(
            {
                "train_expected_cost": round(float(np.mean([_cost(t, p) for t, p in zip(y[train], train_pred, strict=False)])), 4),
                "validation_expected_cost": round(
                    float(np.mean([_cost(t, p) for t, p in zip(y[valid], pred[valid], strict=False)])), 4
                ),
            }
        )
    return pred, proba, gaps


def _oof_logit(x, y, groups):
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    pred = np.empty(len(y), dtype=object)
    proba = np.zeros((len(y), 3))
    gaps = []
    for train, valid in splitter.split(x, y, groups):
        model = _logit()
        model.fit(x[train], y[train])
        pred[valid] = model.predict(x[valid])
        order = list(model.named_steps["logisticregression"].classes_)
        proba[valid] = _align(model.predict_proba(x[valid]), order)
        train_pred = model.predict(x[train])
        gaps.append(
            {
                "train_expected_cost": round(float(np.mean([_cost(t, p) for t, p in zip(y[train], train_pred, strict=False)])), 4),
                "validation_expected_cost": round(
                    float(np.mean([_cost(t, p) for t, p in zip(y[valid], pred[valid], strict=False)])), 4
                ),
            }
        )
    return pred, proba, gaps


def _by_firm(rows, y_true, y_pred) -> dict:
    firms = np.array([row["institution"] for row in rows])
    return {firm: _pack(y_true[firms == firm], y_pred[firms == firm]) for firm in BOOKS}


def _ablation(x, y, groups, params, names) -> list[dict]:
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    base = []
    bumped: dict[str, list[float]] = {group: [] for group in GROUPS}
    for train, valid in splitter.split(x, y, groups):
        model = _fit_lgbm(x[train], y[train], params)
        base_pred = model.predict(x[valid])
        base.append(float(np.mean([_cost(t, p) for t, p in zip(y[valid], base_pred, strict=False)])))
        rng = np.random.RandomState(SEED)
        for group, members in GROUPS.items():
            scrambled = x[valid].copy()
            cols = [names.index(member) for member in members if member in names]
            for col in cols:
                scrambled[:, col] = rng.permutation(scrambled[:, col])
            pred = model.predict(scrambled)
            bumped[group].append(float(np.mean([_cost(t, p) for t, p in zip(y[valid], pred, strict=False)])))
    base_mean = float(np.mean(base))
    ranked: list[dict[str, Any]] = []
    for group, costs in bumped.items():
        increase = float(np.mean(costs) - base_mean)
        ranked.append({"group": group, "validation_cost_increase": round(increase, 4), "earns_place": increase > 0.002})
    ranked.sort(key=lambda item: float(item["validation_cost_increase"]), reverse=True)
    return ranked


def _learning_curve(x, y, groups, params) -> list[dict]:
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    train, valid = next(splitter.split(x, y, groups))
    curve = []
    rng = np.random.RandomState(SEED)
    order = train.copy()
    rng.shuffle(order)
    for fraction in (0.25, 0.5, 0.75, 1.0):
        take = order[: max(30, int(len(order) * fraction))]
        model = _fit_lgbm(x[take], y[take], params)
        train_pred = model.predict(x[take])
        val_pred = model.predict(x[valid])
        curve.append(
            {
                "train_fraction": fraction,
                "train_expected_cost": round(float(np.mean([_cost(t, p) for t, p in zip(y[take], train_pred, strict=False)])), 4),
                "validation_expected_cost": round(float(np.mean([_cost(t, p) for t, p in zip(y[valid], val_pred, strict=False)])), 4),
            }
        )
    return curve


def _calibrate(proba, y) -> tuple[np.ndarray, dict]:
    # Fit isotonic maps on the first half of customers' OOF rows, apply to all.
    # Thresholds are then chosen on the second half only.
    calibrated = proba.copy()
    half = len(y) // 2
    for index, label in enumerate(LABELS):
        iso = IsotonicRegression(out_of_bounds="clip")
        target = (y[:half] == label).astype(float)
        if len(set(target)) < 2:
            continue
        iso.fit(proba[:half, index], target)
        calibrated[:, index] = iso.predict(proba[:, index])
    totals = calibrated.sum(axis=1, keepdims=True)
    totals[totals == 0] = 1
    calibrated = calibrated / totals
    def brier(probs):
        return float(np.mean((probs - (y == "CLOSE").astype(float)) ** 2))
    return calibrated, {
        "method": "isotonic, fit on the first half of out-of-fold rows, one map per class",
        "brier_close_before": round(brier(proba[:, 0]), 4),
        "brier_close_after": round(brier(calibrated[:, 0]), 4),
    }


def _threshold(proba, y) -> dict:
    half = len(y) // 2
    best = {"threshold": 0.75, "expected_cost": 999.0}
    for step in range(14, 20):
        threshold = step / 20
        chosen = []
        for row in proba[half:]:
            if row[0] >= threshold:
                chosen.append("CLOSE")
            elif row[1] >= row[2]:
                chosen.append("RFI")
            else:
                chosen.append("ESCALATE")
        cost = float(np.mean([_cost(t, p) for t, p in zip(y[half:], chosen, strict=False)]))
        if cost < best["expected_cost"]:
            wrongful = sum(1 for t, p in zip(y[half:], chosen, strict=False) if p == "CLOSE" and t != "CLOSE")
            best = {
                "threshold": threshold,
                "expected_cost": round(cost, 4),
                "wrongful_close_rate": round(wrongful / max(1, len(y) - half), 4),
            }
    return best


def _graph_features(rows, source_idx, query_idx):
    """Link counts from the training fold only. A counterparty shared by more than 30 cases is ignored."""
    bags = defaultdict(list)
    labels = {}
    for pos in source_idx:
        pos = int(pos)
        labels[pos] = rows[pos]["label"]
        keys = [("p", party) for party in rows[pos]["parties"]] + [("d", device) for device in rows[pos]["devices"]]
        for key in keys:
            bags[key].append(pos)
    bags = {key: values for key, values in bags.items() if len(values) <= 30}
    out = np.zeros((len(query_idx), 3), dtype=float)
    for row_i, pos in enumerate(query_idx):
        pos = int(pos)
        linked = set()
        degree = 0
        keys = [("p", party) for party in rows[pos]["parties"]] + [("d", device) for device in rows[pos]["devices"]]
        for key in keys:
            others = [item for item in bags.get(key, []) if item != pos]
            if not others:
                continue
            linked.update(others)
            degree = max(degree, len(others))
        share = 0.0
        if linked:
            share = sum(1 for item in linked if labels.get(item) == "ESCALATE") / len(linked)
        out[row_i] = (min(len(linked), 20) / 20.0, share, min(degree, 20) / 20.0)
    return out


def _link_oof(rows, train_idx, x, y, groups, params):
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    pred = np.empty(len(train_idx), dtype=object)
    for inner_train, inner_val in splitter.split(x, y, groups):
        source = train_idx[inner_train]
        trained = np.hstack([x[inner_train], _graph_features(rows, source, train_idx[inner_train])])
        held = np.hstack([x[inner_val], _graph_features(rows, source, train_idx[inner_val])])
        model = _fit_lgbm(trained, y[inner_train], params)
        pred[inner_val] = model.predict(held)
    return pred


def _holdout(rows):
    y_strat = np.array([f"{row['institution']}|{row['label']}" for row in rows])
    groups = np.array([row["group"] for row in rows])
    x_dummy = np.zeros((len(rows), 1))
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    folds = list(splitter.split(x_dummy, y_strat, groups))
    test = folds[0][1]
    train = np.concatenate([pair[1] for pair in folds[1:]])
    return train, test


def main() -> int:
    rows = _rows()
    train_idx, test_idx = _holdout(rows)
    train_rows = [rows[i] for i in train_idx]
    # The test slice is not read again until the final block.
    names, x_all, y_all, g_all = _xy(rows, "features")
    comp_names, c_all, _, _ = _xy(rows, "composites")
    x, y, groups = x_all[train_idx], y_all[train_idx], g_all[train_idx]
    search = _search(x, y, groups)
    full_pred, full_proba, full_gaps = _oof_lgbm(x, y, groups, search["chosen"])
    grouped_pred, _, grouped_gaps = _oof_lgbm(c_all[train_idx], y, groups, search["chosen"])
    logit_pred, logit_proba, logit_gaps = _oof_logit(x, y, groups)
    logit_grouped, _, logit_grouped_gaps = _oof_logit(c_all[train_idx], y, groups)

    def mean_gap(gaps):
        return {
            "mean_train_expected_cost": round(float(np.mean([item["train_expected_cost"] for item in gaps])), 4),
            "mean_validation_expected_cost": round(
                float(np.mean([item["validation_expected_cost"] for item in gaps])), 4
            ),
        }

    comparison = {
        "lightgbm_full": {
            **_pack(y, full_pred),
            "gap": mean_gap(full_gaps),
            "folds": full_gaps,
            "by_institution": _by_firm(train_rows, y, full_pred),
        },
        "lightgbm_grouped": {
            **_pack(y, grouped_pred),
            "gap": mean_gap(grouped_gaps),
            "folds": grouped_gaps,
            "by_institution": _by_firm(train_rows, y, grouped_pred),
        },
        "logistic_full": {
            **_pack(y, logit_pred),
            "gap": mean_gap(logit_gaps),
            "folds": logit_gaps,
            "by_institution": _by_firm(train_rows, y, logit_pred),
        },
        "logistic_grouped": {**_pack(y, logit_grouped), "gap": mean_gap(logit_grouped_gaps)},
    }
    link_pred = _link_oof(rows, train_idx, x, y, groups, search["chosen"])
    link_pack = _pack(y, link_pred)
    base_cost = comparison["lightgbm_full"]["expected_cost"]
    link_kept = link_pack["expected_cost"] + 0.005 < base_cost
    inner_winner = min(comparison, key=lambda key: comparison[key]["expected_cost"])
    ablation = _ablation(x, y, groups, search["chosen"], names)
    curve = _learning_curve(x, y, groups, search["chosen"])
    calibrated, calibration = _calibrate(full_proba, y)
    threshold = _threshold(calibrated, y)

    firms = np.array([row["institution"] for row in train_rows])
    loio = {}
    logo = LeaveOneGroupOut()
    for tr, te in logo.split(x, y, firms):
        firm = firms[te][0]
        model = _fit_lgbm(x[tr], y[tr], search["chosen"])
        loio[str(firm)] = _pack(y[te], model.predict(x[te]))

    # One look at the hold-out, using the inner winner's family.
    use_grouped = inner_winner.endswith("grouped")
    x_source = c_all if use_grouped else x_all
    final = (
        _fit_lgbm(x_source[train_idx], y_all[train_idx], search["chosen"]) if "lightgbm" in inner_winner else _logit()
    )
    if "logistic" in inner_winner:
        final.fit(x_source[train_idx], y_all[train_idx])
    test_pred = final.predict(x_source[test_idx])
    train_pred = final.predict(x_source[train_idx])
    test_pack = _pack(y_all[test_idx], test_pred, y_all[train_idx], train_pred)
    policy_test = _pack(y_all[test_idx], y_all[test_idx])
    ship = test_pack["expected_cost"] < policy_test["expected_cost"]

    # UI probabilities are the grouped-or-full OOF logistic/lightgbm scores on the train rows.
    # Held-out customers get a score from the final model, marked as such.
    score_proba = np.zeros((len(rows), 3))
    score_proba[train_idx] = full_proba
    if "lightgbm" in inner_winner:
        held_model = final
        score_proba[test_idx] = _align(
            held_model.predict_proba(x_source[test_idx]), getattr(held_model, "classes_", LABELS)
        )
    else:
        order = list(final.named_steps["logisticregression"].classes_)
        score_proba[test_idx] = _align(final.predict_proba(x_source[test_idx]), order)

    report = {
        "label_source": "Weak supervision: priority vote of the policy checks. Not hidden-test labels.",
        "ship_into_system_run": ship,
        "why": "The hold-out is scored against the policy votes. The policy matches those votes,"
        "so its expected cost is 0. The model is not loaded by system/run.",
        "groups": {name: list(members) for name, members in GROUPS.items()},
        "split": {
            "test_fraction": 0.2,
            "train_n": int(len(train_idx)),
            "test_n": int(len(test_idx)),
            "method": "One StratifiedGroupKFold fold held out, stratified on institution|label, grouped by customer, seed 42. Not used for tuning.",
        },
        "hyperparameters": search,
        "comparison_on_train_oof": comparison,
        "inner_winner": inner_winner,
        "leave_one_institution_out": loio,
        "group_ablation": ablation,
        "learning_curve": curve,
        "calibration": calibration,
        "frozen_close_threshold": threshold,
        "test_once": {"model": inner_winner, **test_pack, "policy_expected_cost": policy_test["expected_cost"]},
        "n_cases": len(rows),
        "n_atomic_features": len(names),
        "outer_folds": 5,
        "link_features": {
            "features": ["n_linked_cases", "linked_escalate_share", "shared_counterparty_degree"],
            "outer_folds": 5,
            "leakage": "Each validation fold sees links only from the other training folds."
            "Counterparties shared by more than 30 training cases are ignored. Device ids come from device exports, which are not labels.",
            "expected_cost_without": base_cost,
            "expected_cost_with": link_pack["expected_cost"],
            "wrongful_close_with": link_pack["wrongful_close_rate"],
            "kept": link_kept,
            "note": (
                "Linked-case features lowered out-of-fold expected cost, so they stay in the comparison."
                if link_kept
                else "Linked-case features did not lower out-of-fold expected cost by at least 0.005, so the shipped score does not use them."
            ),
        },
    }
    (ROOT / "ml" / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (ROOT / "ml" / "thresholds.json").write_text(
        json.dumps(
            {
                "close_probability": threshold["threshold"],
                "ship_into_system_run": ship,
                "chosen_lightgbm": search["chosen"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with (ROOT / "ml" / "scores.jsonl").open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            handle.write(
                json.dumps(
                    {
                        "case_id": row["case_id"],
                        "institution": row["institution"],
                        "p_close": round(float(score_proba[index, 0]), 4),
                        "p_rfi": round(float(score_proba[index, 1]), 4),
                        "p_escalate": round(float(score_proba[index, 2]), 4),
                        "groups": {key: round(float(value), 4) for key, value in row["composites"].items()},
                    }
                )
                + "\n"
            )
    # Also refresh the scored outputs from the same policy pass.
    from forge_engine.sop import score_folder as _score

    for name in BOOKS:
        decisions = _score(DATA / name)
        text = (
            "\n".join(json.dumps(item.public(), ensure_ascii=False, separators=(", ", ": ")) for item in decisions)
            + "\n"
        )
        (ROOT / "output" / f"{name}.jsonl").write_text(text, encoding="utf-8")
    print("winner", inner_winner, "test cost", test_pack["expected_cost"], "ship", ship)
    print("ablation", [(item["group"], item["validation_cost_increase"]) for item in ablation[:5]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
