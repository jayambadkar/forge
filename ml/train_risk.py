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
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from lightgbm import LGBMClassifier, early_stopping, log_evaluation
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import LeaveOneGroupOut, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "system"))

from forge_engine.sop import (  # noqa: E402
    Book,
    _baseline,
    _cover_own_transfers,
    _near,
    _own_multiple,
    norm,
    score_folder,
)

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
        "n_doc_types",
        "log_doc_chars",
    ),
    "amount_match": ("best_amount_ratio", "n_amount_matches", "largest_unmatched"),
    "identity_match": ("party_in_doc_share", "own_name_share", "name_on_statement"),
    "profile_deviation": ("income_multiple", "amount_over_baseline", "one_way_multiple"),
    "flow_pattern": (
        "pass_through",
        "n_counterparties",
        "structuring_flag",
        "n_in",
        "n_out",
        "n_tx",
        "log_sum_in",
        "log_sum_out",
        "log_max",
        "cash_share",
        "round_share",
        "card_share",
        "n_person_out",
        "company_in_share",
        "equal_split",
        "n_alerts",
        "span_days",
    ),
    "geography_risk": ("high_risk_corridor", "n_countries"),
    "list_agreement": ("list_alert",),
    "prior_review": ("prior_same_rule", "n_prior_reviews", "review_mentions_amount"),
    "account_history": ("dormant_flag", "dormant_days_scaled"),
    "held_payment": ("held_flag", "held_without_invoice"),
    "customer": ("is_business", "log_baseline", "n_expected_countries"),
}
# Dropped under the smaller model. They did not earn a place once the other groups were present.
DROPPED_GROUPS = ("customer", "account_history", "list_agreement")


# Facts that read the same at every firm. Document types are folded into kinds,
# so a firm with its own paperwork still lands on known columns.
RULES = ("TM01", "TM02", "TM03", "TM04", "TM05", "TM06", "TM07", "TM08", "TM10", "TM22")
DOC_KINDS: dict[str, frozenset[str]] = {
    "statement": frozenset({"bank_statement"}),
    "invoice": frozenset(
        {
            "invoice",
            "supplier_invoice",
            "supplier_invoices",
            "consulting_contract",
            "supply_contract",
            "contract_schedule",
            "purchase_order",
            "payment_file",
            "dealer_invoice",
            "hospital_invoice",
            "carrier_invoice",
            "freight_invoices",
        }
    ),
    "books": frozenset(
        {
            "cash_collection_reports",
            "cash_reconciliation",
            "takings_book",
            "ticket_report",
            "management_accounts",
            "cash_handling_procedure",
        }
    ),
    "relation": frozenset({"gift_letter", "factoring_agreement", "remittance_advice", "group_structure", "loan_agreement"}),
    "refund": frozenset({"credit_note", "cancellation_confirmation", "deposit_return_letter"}),
    "register": frozenset({"company_register_extract", "significant_control_register"}),
    "fraud": frozenset({"sending_bank_fraud_report"}),
    "device": frozenset({"device_export"}),
}
NOT_SUPPORT = frozenset({"staff_note", "reverification_record", "advert"})
SUPPORT_KINDS = ("statement", "invoice", "books", "relation", "refund", "event")
# Counts and sizes move with each firm's book. The desk model leaves them out.
SCALE_FEATURES = frozenset(
    {
        "n_docs",
        "log_doc_chars",
        "n_doc_types",
        "log_sum_in",
        "log_sum_out",
        "log_max",
        "n_prior_reviews",
        "n_tx",
        "n_in",
        "n_out",
        "n_counterparties",
        "n_person_out",
        "n_alerts",
    }
)


def _kind(doc_type: str) -> str:
    for kind, members in DOC_KINDS.items():
        if doc_type in members:
            return kind
    return "other" if doc_type in NOT_SUPPORT else "event"


def _names_party(doc: dict, tx: dict, customer_name: str) -> bool:
    party = norm(tx.get("counterparty_name"))
    return bool(party and party in doc["norm"]) or (len(customer_name) >= 4 and customer_name in doc["norm"])


def _evidence(book, case: dict, customer: dict, alerts: list[dict], txs: list[dict], docs: list[dict]) -> dict[str, float]:
    cname = norm(customer.get("name"))
    rules = {alert.get("rule_id") for alert in alerts}
    total = sum(float(tx.get("amount_gbp") or 0) for tx in txs) or 1.0
    found: dict[str, float] = {f"rule_{rule}": float(rule in rules) for rule in RULES}
    best_cover = 0.0
    for kind in (*DOC_KINDS, "event"):
        kind_docs = [doc for doc in docs if _kind(doc.get("type") or "") == kind]
        covered = 0.0
        for tx in txs:
            amount = float(tx.get("amount_gbp") or 0)
            if any(
                _names_party(doc, tx, cname) and any(_near(amount, value, 0.02) for value in doc["amounts"])
                for doc in kind_docs
            ):
                covered += amount
        found[f"has_{kind}"] = float(bool(kind_docs))
        found[f"{kind}_names_customer"] = float(any(len(cname) >= 4 and cname in doc["norm"] for doc in kind_docs))
        found[f"{kind}_value_covered"] = covered / total
        if kind in SUPPORT_KINDS:
            best_cover = max(best_cover, covered / total)
    support = [doc for doc in docs if _kind(doc.get("type") or "") in SUPPORT_KINDS]
    explained = 0
    for alert in alerts:
        alert_txs = [book.transactions[tid] for tid in alert.get("transaction_ids") or [] if tid in book.transactions]
        if any(
            _names_party(doc, tx, cname)
            and any(_near(float(tx.get("amount_gbp") or 0), value, 0.02) for value in doc["amounts"])
            for tx in alert_txs
            for doc in support
        ):
            explained += 1
    found["alerts_explained_share"] = explained / len(alerts) if alerts else 0.0
    found["all_alerts_explained"] = float(bool(alerts) and explained == len(alerts))
    found["n_rules"] = float(len(rules))
    # Each movement against its own line on one document.
    line_cover = 0.0
    for doc in support:
        if not any(_names_party(doc, tx, cname) for tx in txs):
            continue
        pool = list(doc["amounts"])
        got = 0.0
        for tx in txs:
            amount = float(tx.get("amount_gbp") or 0)
            index = next((i for i, value in enumerate(pool) if _near(amount, value, 0.01)), None)
            if index is not None:
                pool.pop(index)
                got += amount
        line_cover = max(line_cover, got / total)
    found["line_cover"] = line_cover
    own = [tx for tx in txs if len(cname) >= 4 and norm(tx.get("counterparty_name")) == cname]
    if own:
        covered_own, _ = _cover_own_transfers(customer, own, docs)
        own_total = sum(float(tx.get("amount_gbp") or 0) for tx in own) or 1.0
        found["own_mirror_share"] = sum(float(tx.get("amount_gbp") or 0) for tx, _ in covered_own) / own_total
        found["own_multiple"] = min(_own_multiple(customer, own, {}), 50.0) if _baseline(customer) else -1.0
    else:
        found["own_mirror_share"] = -1.0
        found["own_multiple"] = -1.0
    held = book.transactions.get(case.get("held_payment_id") or "")
    found["held_third_party_10k"] = float(
        bool(held) and float(held.get("amount_gbp") or 0) >= 10000 and norm(held.get("counterparty_name")) != cname
    )
    found["best_cover"] = best_cover
    found["any_named"] = max(found[f"{kind}_names_customer"] for kind in SUPPORT_KINDS)
    found["any_support"] = max(found[f"has_{kind}"] for kind in SUPPORT_KINDS)
    found["uncovered"] = 1.0 - max(best_cover, line_cover)
    return found


def _can_close(evidence: dict[str, float]) -> bool:
    """The second check may not close a case with no supporting document of any kind."""
    if evidence["any_support"] or evidence["best_cover"] > 0 or evidence["line_cover"] > 0:
        return True
    return bool(evidence["rule_TM22"] and evidence["register_names_customer"])


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
            cash_n = sum(1 for tx in txs if tx.get("channel") == "cash")
            card_n = sum(1 for tx in txs if tx.get("channel") == "card")
            round_n = sum(1 for tx in txs if float(tx.get("amount_gbp") or 0) >= 100 and float(tx.get("amount_gbp") or 0) % 100 == 0)
            person_out = 0
            company_in = 0.0
            out_amounts: list[float] = []
            for tx in txs:
                amount = float(tx.get("amount_gbp") or 0)
                party = tx.get("counterparty_name") or ""
                company = bool(re.search(r"\b(ltd|limited|plc|llp)\b", party, re.I))
                if tx.get("direction") == "out" and party and not company and norm(party) != cname:
                    person_out += 1
                    out_amounts.append(amount)
                if tx.get("direction") == "in" and company:
                    company_in += amount
            peak_out = max(out_amounts) if out_amounts else 0.0
            dates = []
            for tx in txs:
                stamp = str(tx.get("booked_at") or "")
                if len(stamp) >= 10:
                    dates.append(stamp[:10])
            span = 0.0
            if len(dates) >= 2:
                start = date.fromisoformat(min(dates))
                end = date.fromisoformat(max(dates))
                span = min((end - start).days / 30.0, 4.0)
            own_in = 0.0
            own_out = 0.0
            for tx in txs:
                if not cname or norm(tx.get("counterparty_name")) != cname:
                    continue
                amount = float(tx.get("amount_gbp") or 0)
                if tx.get("direction") == "out":
                    own_out += amount
                else:
                    own_in += amount
            one_way = max(own_in, own_out)
            unmatched = 0.0
            if txs:
                largest = max(txs, key=lambda tx: float(tx.get("amount_gbp") or 0))
                largest_amount = float(largest.get("amount_gbp") or 0)
                unmatched = 0.0 if best_ratio >= 0.98 else min(largest_amount / 10000.0, 5.0)
            review_amount = 0.0
            for review in reviews:
                if re.search(r"£\s*[0-9]", review.get("note") or ""):
                    review_amount = 1.0
                    break
            statement_named = 0.0
            for doc in docs:
                if doc.get("type") == "bank_statement" and cname and cname in doc.get("norm", ""):
                    statement_named = 1.0
                    break
            doc_chars = sum(len(doc.get("text") or "") for doc in docs)
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
                "n_doc_types": float(len(kinds)),
                "log_doc_chars": float(np.log1p(doc_chars)),
                "largest_unmatched": unmatched,
                "name_on_statement": statement_named,
                "one_way_multiple": (one_way / baseline) if baseline else 0.0,
                "n_tx": float(len(txs)),
                "log_sum_in": float(np.log1p(sum_in)),
                "log_sum_out": float(np.log1p(sum_out)),
                "log_max": float(np.log1p(max((float(tx.get("amount_gbp") or 0) for tx in txs), default=0.0))),
                "cash_share": cash_n / len(txs) if txs else 0.0,
                "round_share": round_n / len(txs) if txs else 0.0,
                "card_share": card_n / len(txs) if txs else 0.0,
                "n_person_out": float(person_out),
                "company_in_share": (company_in / sum_in) if sum_in else 0.0,
                "equal_split": (peak_out / sum(out_amounts)) if out_amounts else 0.0,
                "n_alerts": float(len(alerts)),
                "span_days": span,
                "review_mentions_amount": review_amount,
                "is_business": 1.0 if customer.get("kind") == "business" else 0.0,
                "log_baseline": float(np.log1p(baseline)),
                "n_expected_countries": float(len(declared.get("expected_countries") or [])),
                "n_countries": float(len({tx.get("counterparty_country") for tx in txs if tx.get("counterparty_country")})),
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
                    "evidence": _evidence(book, case, customer, alerts, txs, docs),
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
    if len(y_true):
        per_class = f1_score(y_true, y_pred, labels=list(LABELS), average=None, zero_division=0)
        block["macro_f1"] = round(float(np.mean(per_class)), 4)
        block["per_class_f1"] = {label: round(float(value), 4) for label, value in zip(LABELS, per_class, strict=True)}
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


def _kept_index(names: list[str]) -> list[int]:
    dropped = [member for group in DROPPED_GROUPS for member in GROUPS[group]]
    return [index for index, name in enumerate(names) if name not in dropped]


def _from_proba(proba: np.ndarray) -> np.ndarray:
    pred = np.empty(len(proba), dtype=object)
    pred[:] = [LABELS[int(np.argmax(row))] for row in proba]
    return pred


def _fold_stats(y: np.ndarray, pred: np.ndarray, groups: np.ndarray) -> dict[str, float]:
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    costs = []
    agreements = []
    for _, valid in splitter.split(np.zeros((len(y), 1)), y, groups):
        costs.append(float(np.mean([_cost(t, p) for t, p in zip(y[valid], pred[valid], strict=False)])))
        agreements.append(float(np.mean(y[valid] == pred[valid])))
    return {
        "cost_mean": round(float(np.mean(costs)), 4),
        "cost_std": round(float(np.std(costs)), 4),
        "agreement_mean": round(float(np.mean(agreements)), 4),
        "agreement_std": round(float(np.std(agreements)), 4),
    }


def _oof_encoded(make_model, x: np.ndarray, y: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    encoded = {label: index for index, label in enumerate(LABELS)}
    y_num = np.array([encoded[label] for label in y])
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    pred = np.empty(len(y), dtype=object)
    proba = np.zeros((len(y), 3))
    for train, valid in splitter.split(x, y, groups):
        model = make_model()
        model.fit(x[train], y_num[train])
        pred[valid] = np.array([LABELS[int(item)] for item in model.predict(x[valid])])
        raw_proba = model.predict_proba(x[valid])
        aligned = np.zeros((len(valid), 3))
        for column, label in enumerate(model.classes_):
            aligned[:, int(label)] = raw_proba[:, column]
        proba[valid] = aligned
    return pred, proba


def _xgb() -> XGBClassifier:
    return XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        n_estimators=120,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=SEED,
        n_jobs=1,
        verbosity=0,
    )


def _trees() -> ExtraTreesClassifier:
    return ExtraTreesClassifier(n_estimators=300, min_samples_leaf=2, random_state=SEED, n_jobs=1)


def _reason_agreement(x: np.ndarray, y: np.ndarray, reasons: np.ndarray, groups: np.ndarray) -> dict[str, float]:
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    scores = []
    for train, valid in splitter.split(x, y, groups):
        model = ExtraTreesClassifier(n_estimators=300, min_samples_leaf=2, random_state=SEED, n_jobs=1)
        model.fit(x[train], reasons[train])
        scores.append(float(np.mean(model.predict(x[valid]) == reasons[valid])))
    return {"agreement_mean": round(float(np.mean(scores)), 4), "agreement_std": round(float(np.std(scores)), 4)}


def _noise_cost(x: np.ndarray, y: np.ndarray, groups: np.ndarray, params: dict, rate: float) -> float:
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    rng = np.random.RandomState(SEED)
    costs = []
    for train, valid in splitter.split(x, y, groups):
        noisy = y[train].copy()
        flip = rng.rand(len(noisy)) < rate
        noisy[flip] = rng.choice(list(LABELS), size=int(flip.sum()))
        model = _fit_lgbm(x[train], noisy, params)
        pred = model.predict(x[valid])
        costs.append(float(np.mean([_cost(t, p) for t, p in zip(y[valid], pred, strict=False)])))
    return round(float(np.mean(costs)), 4)


DESK_GRID = (
    {"num_leaves": 7, "min_child_samples": 20},
    {"num_leaves": 15, "min_child_samples": 20},
    {"num_leaves": 31, "min_child_samples": 20},
    {"num_leaves": 15, "min_child_samples": 50},
)
COST = np.array([[_cost(true, pred) for pred in LABELS] for true in LABELS], dtype=float)


def _binary(params: dict) -> LGBMClassifier:
    return LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        deterministic=True,
        force_row_wise=True,
        n_jobs=1,
        random_state=SEED,
        verbosity=-1,
        **params,
    )


class TwoStage:
    """Close or not first, then request or escalate among the rest."""

    def __init__(self, params: dict):
        self.params = params

    def fit(self, x: np.ndarray, y: np.ndarray) -> TwoStage:
        self.close = _binary(self.params).fit(x, (y == "CLOSE").astype(int))
        rest = y != "CLOSE"
        self.escalate = _binary(self.params).fit(x[rest], (y[rest] == "ESCALATE").astype(int))
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        p_close = np.asarray(self.close.predict_proba(x))[:, 1]
        p_escalate = np.asarray(self.escalate.predict_proba(x))[:, 1]
        return np.column_stack([p_close, (1 - p_close) * (1 - p_escalate), (1 - p_close) * p_escalate])


def _decide(proba: np.ndarray, can_close: np.ndarray) -> np.ndarray:
    """Lowest expected cost under the scoring matrix, never a close without a document."""
    risk = proba @ COST
    risk[~can_close, 0] = np.inf
    pred = np.empty(len(proba), dtype=object)
    pred[:] = [LABELS[int(index)] for index in np.argmin(risk, axis=1)]
    return pred


def _desk_xy(rows: list[dict]) -> tuple[list[str], np.ndarray, np.ndarray]:
    dropped = {member for group in DROPPED_GROUPS for member in GROUPS[group]}
    raw = [name for name in rows[0]["features"] if name not in SCALE_FEATURES and name not in dropped]
    extra = list(rows[0]["evidence"])
    names = raw + [f"e_{name}" for name in extra]
    x = np.array([[row["features"][n] for n in raw] + [row["evidence"][n] for n in extra] for row in rows], dtype=float)
    can_close = np.array([_can_close(row["evidence"]) for row in rows])
    return names, x, can_close


def _desk_tune(x: np.ndarray, y: np.ndarray, groups: np.ndarray, can_close: np.ndarray) -> dict:
    inner = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED)
    best: tuple[float, dict] | None = None
    for params in DESK_GRID:
        costs = []
        for train, valid in inner.split(x, y, groups):
            proba = TwoStage(params).fit(x[train], y[train]).predict_proba(x[valid])
            pred = _decide(proba, can_close[valid])
            costs.append(float(np.mean([_cost(t, p) for t, p in zip(y[valid], pred, strict=True)])))
        if best is None or float(np.mean(costs)) < best[0]:
            best = (float(np.mean(costs)), params)
    if best is None:
        raise RuntimeError("desk grid is empty")
    return best[1]


def _desk_outer(x, y, groups, can_close, splits) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    pred = np.empty(len(y), dtype=object)
    proba = np.zeros((len(y), 3))
    chosen = []
    for train, valid in splits:
        params = _desk_tune(x[train], y[train], groups[train], can_close[train])
        proba[valid] = TwoStage(params).fit(x[train], y[train]).predict_proba(x[valid])
        pred[valid] = _decide(proba[valid], can_close[valid])
        chosen.append(params)
    return pred, proba, chosen


def main() -> int:
    rows = _rows()
    train_idx, test_idx = _holdout(rows)
    train_rows = [rows[i] for i in train_idx]
    # The test slice is not read again until the final block.
    names, x_all, y_all, g_all = _xy(rows, "features")
    if len(names) != 48:
        raise RuntimeError(f"expected 48 raw features, found {len(names)}: {names}")
    kept = _kept_index(names)
    if len(kept) != 42:
        raise RuntimeError(f"expected 42 features after dropping customer, history and list, found {len(kept)}")
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
    calibrated, _full_calibration = _calibrate(full_proba, y)
    threshold = _threshold(calibrated, y)

    ablated_x = x[:, kept]
    ablated_all = x_all[:, kept]
    ablated_pred, ablated_proba, _ = _oof_lgbm(ablated_x, y, groups, search["chosen"])
    xgb_pred, xgb_proba = _oof_encoded(_xgb, ablated_x, y, groups)
    tree_pred, tree_proba = _oof_encoded(_trees, ablated_x, y, groups)
    full_stats = _fold_stats(y, full_pred, groups)
    ablated_stats = _fold_stats(y, ablated_pred, groups)
    xgb_stats = _fold_stats(y, xgb_pred, groups)
    tree_stats = _fold_stats(y, tree_pred, groups)
    stack_proba = (ablated_proba + xgb_proba + tree_proba) / 3.0
    stack_pred = _from_proba(stack_proba)
    stack_stats = _fold_stats(y, stack_pred, groups)
    # The stack is not a better model when it sits inside the best single model's spread.
    best_single = min(ablated_stats["cost_mean"], xgb_stats["cost_mean"], tree_stats["cost_mean"], full_stats["cost_mean"])
    best_std = min(item["cost_std"] for item in (ablated_stats, xgb_stats, tree_stats, full_stats))
    stack_better = stack_stats["cost_mean"] + 1e-9 < best_single - best_std
    prefer_ablated = ablated_stats["cost_mean"] <= full_stats["cost_mean"] + full_stats["cost_std"]
    raw_pred = _from_proba(ablated_proba)
    calibrated_ablated, calibration_detail = _calibrate(ablated_proba, y)
    calibrated_pred = _from_proba(calibrated_ablated)
    raw_cost = _pack(y, raw_pred)["expected_cost"]
    calibrated_cost = _pack(y, calibrated_pred)["expected_cost"]
    # A small move inside the fold spread is not a reason to recalibrate.
    use_raw = calibrated_cost > raw_cost - ablated_stats["cost_std"]
    reasons = np.array([row["reason_code"] for row in train_rows])
    reason_stats = _reason_agreement(ablated_x, y, reasons, groups)
    noise_5 = _noise_cost(ablated_x, y, groups, search["chosen"], 0.05)
    noise_10 = _noise_cost(ablated_x, y, groups, search["chosen"], 0.10)

    firms = np.array([row["institution"] for row in train_rows])
    loio = {}
    logo = LeaveOneGroupOut()
    firm_splits = list(logo.split(ablated_x, y, firms))
    loio_pred = np.empty(len(y), dtype=object)
    for tr, te in firm_splits:
        firm = firms[te][0]
        model = _fit_lgbm(ablated_x[tr], y[tr], search["chosen"])
        loio_pred[te] = model.predict(ablated_x[te])
        loio[str(firm)] = _pack(y[te], loio_pred[te])

    # The desk model: facts that do not depend on a firm's size, two stages, and the
    # scoring matrix in the decision. Tuned inside every outer fold.
    desk_names, desk_all, can_all = _desk_xy(rows)
    desk_x, desk_can = desk_all[train_idx], can_all[train_idx]
    outer = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED).split(desk_x, y, groups))
    desk_pred, desk_proba, desk_params = _desk_outer(desk_x, y, groups, desk_can, outer)
    desk_firm_pred, _, desk_firm_params = _desk_outer(desk_x, y, groups, desk_can, firm_splits)
    desk_loio = {str(firms[te][0]): _pack(y[te], desk_firm_pred[te]) for _, te in firm_splits}
    desk_stats = _fold_stats(y, desk_pred, groups)
    old_unseen = _pack(y, loio_pred)
    desk_unseen = _pack(y, desk_firm_pred)
    # The desk model replaces the smaller model when it holds up better on an unseen firm
    # and is no worse inside the spread of the folds on known firms.
    use_desk = (
        desk_unseen["expected_cost"] < old_unseen["expected_cost"]
        and desk_stats["cost_mean"] <= ablated_stats["cost_mean"] + ablated_stats["cost_std"]
    )

    # The smaller model is the one the desk shows, unless the stack is clearly better.
    chosen_name = "stack" if stack_better else ("lightgbm_ablated" if prefer_ablated else "lightgbm_full")
    if use_desk:
        chosen_name = "two_stage"
    score_x = ablated_all if chosen_name != "lightgbm_full" else x_all
    score_train = score_x[train_idx]
    final = _fit_lgbm(score_train, y_all[train_idx], search["chosen"])
    test_pred = final.predict(score_x[test_idx])
    train_pred = final.predict(score_train)
    test_pack = _pack(y_all[test_idx], test_pred, y_all[train_idx], train_pred)
    policy_test = _pack(y_all[test_idx], y_all[test_idx])
    # Policy versus its own labels costs 0. The score stays off the scored path.
    ship = False
    agreement = float(np.mean(y_all[test_idx] == test_pred))
    score_proba = np.zeros((len(rows), 3))
    if chosen_name == "stack":
        score_proba[train_idx] = stack_proba
    elif chosen_name == "lightgbm_ablated":
        score_proba[train_idx] = ablated_proba if use_raw else calibrated_ablated
    else:
        score_proba[train_idx] = full_proba
    score_proba[test_idx] = _align(final.predict_proba(score_x[test_idx]), getattr(final, "classes_", LABELS))
    desk_final_params = _desk_tune(desk_x, y, groups, desk_can)
    desk_final = TwoStage(desk_final_params).fit(desk_x, y)
    desk_test_proba = desk_final.predict_proba(desk_all[test_idx])
    desk_test = _pack(
        y_all[test_idx],
        _decide(desk_test_proba, can_all[test_idx]),
        y,
        _decide(desk_final.predict_proba(desk_x), desk_can),
    )
    if use_desk:
        score_proba[train_idx] = desk_proba
        score_proba[test_idx] = desk_test_proba
        test_pack = desk_test
        agreement = float(np.mean(y_all[test_idx] == _decide(desk_test_proba, can_all[test_idx])))
    inner_winner = chosen_name

    report = {
        "label_source": "Weak supervision: priority vote of the policy checks. Not hidden-test labels.",
        "ship_into_system_run": ship,
        "why": "The hold-out is scored against the policy votes. The policy matches those votes, "
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
        "desk_model": {
            "used": use_desk,
            "features": len(desk_names),
            "left_out": sorted(SCALE_FEATURES | {m for g in DROPPED_GROUPS for m in GROUPS[g]}),
            "decision": "Lowest expected cost under the scoring matrix. No close without a supporting document on file.",
            "policy_closes_without_document": int(np.sum((y_all == "CLOSE") & ~can_all)),
            "cases_it_cannot_close": int(np.sum(~can_all)),
            "grid": list(DESK_GRID),
            "params_by_fold": desk_params,
            "params_by_firm": desk_firm_params,
            "final_params": desk_final_params,
            "out_of_fold": {**_pack(y, desk_pred), **desk_stats},
            "leave_one_institution_out": desk_loio,
            "unseen_firm_all": desk_unseen,
            "unseen_firm_all_previous": old_unseen,
            "test_once": desk_test,
        },
        "group_ablation": ablation,
        "learning_curve": curve,
        "calibration": {
            **calibration_detail,
            "raw_expected_cost": raw_cost,
            "isotonic_expected_cost": calibrated_cost,
            "used": "raw" if use_raw else "isotonic",
            "note": "Isotonic calibration does not beat the raw probabilities by more than the spread of the folds, so the desk uses the raw probabilities."
            if use_raw
            else "Isotonic calibration lowered the cost by more than the spread of the folds, so those probabilities are used.",
        },
        "review": {
            "raw_features": 48,
            "model_features": 42 if chosen_name != "lightgbm_full" else 48,
            "desk_features": len(desk_names),
            "dropped_groups": list(DROPPED_GROUPS),
            "folds": "5-fold StratifiedGroupKFold by customer, with a 20% grouped hold-out not used for tuning.",
            "models": {
                "lightgbm": full_stats,
                "lightgbm_ablated": ablated_stats,
                "two_stage": desk_stats,
                "xgboost": xgb_stats,
                "extra_trees": tree_stats,
                "stack": {**stack_stats, "better_than_best_single": stack_better},
                "logistic": _fold_stats(y, logit_pred, groups),
            },
            "preferred": chosen_name,
            "held_out": {
                "expected_cost": test_pack["expected_cost"],
                "agreement": round(agreement, 4),
                "wrongful_closes": test_pack["wrongful_closes"],
            },
            "leave_one_institution_out": {
                firm: block["expected_cost"] for firm, block in (desk_loio if use_desk else loio).items()
            },
            "reason_code": reason_stats,
            "label_noise": {"flip_5": noise_5, "flip_10": noise_10},
        },
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
