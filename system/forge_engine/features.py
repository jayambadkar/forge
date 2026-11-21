"""Case features for the risk model.

Policy flags and behavioural counts are separate so a model can be trained
without the facts the labelling functions already use. Neither set is a verdict.
"""

from __future__ import annotations

from .decide import _alerts, _case_evidence, _review_covers, _txns_for, decide_case
from .facts import classify_match, is_own_account, is_round_pounds, norm_name
from .model import Case, Institution

BEHAVIOURAL = (
    "n_alerts",
    "n_txns",
    "amount_total",
    "amount_max",
    "amount_to_expected",
    "own_account_ratio",
    "crypto_txn_ratio",
    "round_txn_ratio",
    "cash_txn_ratio",
    "n_counterparties",
    "n_countries",
    "shared_device",
)

POLICY = (
    "list_confirmed",
    "list_refuted",
    "list_weak",
    "prior_review_count",
    "prior_review_covers",
    "above_doc_threshold",
    "has_matching_doc",
    "max_own_account_multiple",
)

FEATURE_NAMES = BEHAVIOURAL + POLICY


def _list_flags(inst: Institution, case: Case) -> dict[str, float]:
    flags = {"list_confirmed": 0.0, "list_refuted": 0.0, "list_weak": 0.0}
    customer = inst.customers.get(case.customer_id)
    if customer is None:
        return flags
    for entry in inst.list_entries:
        kind = classify_match(
            customer.name,
            customer.dob,
            customer.country,
            entry.name,
            entry.dob,
            entry.country,
        )
        if kind == "confirmed":
            flags["list_confirmed"] = 1.0
        elif kind == "refuted":
            flags["list_refuted"] = 1.0
        elif kind == "weak":
            flags["list_weak"] = 1.0
    return flags


def feature_row(inst: Institution, case: Case) -> dict[str, float]:
    alerts = _alerts(inst, case)
    txns = []
    for alert in alerts:
        txns.extend(_txns_for(inst, alert))
    # Stable unique order.
    seen = set()
    unique = []
    for txn in txns:
        if txn.id not in seen:
            seen.add(txn.id)
            unique.append(txn)
    txns = unique
    amounts = [txn.amount_gbp for txn in txns if txn.amount_gbp is not None]
    customer = inst.customers.get(case.customer_id)
    expected = customer.expected_monthly if customer and customer.expected_monthly else None
    total = float(sum(amounts)) if amounts else 0.0
    peak = float(max(amounts)) if amounts else 0.0
    n = len(txns) or 1
    own = [txn for txn in txns if customer and is_own_account(txn, customer)]
    multiples = []
    if expected and expected > 0:
        multiples = [((txn.amount_gbp or 0.0) / expected) for txn in own]
    reviews = inst.reviews_by_customer.get(case.customer_id, ())
    covers = 0
    for alert in alerts:
        alert_txns = _txns_for(inst, alert)
        amount = sum(txn.amount_gbp or 0 for txn in alert_txns) or alert.amount_gbp
        if any(_review_covers(review.text, alert, alert_txns, amount) for review in reviews):
            covers = 1
    above = 0.0
    matched = 0.0
    evidence = _case_evidence(inst, case)
    for requirement in inst.policy.requirements:
        for txn in txns:
            amount = txn.amount_gbp
            if amount is None or amount < requirement.threshold_gbp:
                continue
            if requirement.direction and txn.direction and txn.direction != requirement.direction:
                continue
            above = 1.0
            for item in evidence:
                blob = f"{item.kind} {item.title} {item.text}".lower()
                if requirement.keyword in blob:
                    matched = 1.0
    row = {
        "n_alerts": float(len(alerts)),
        "n_txns": float(len(txns)),
        "amount_total": total,
        "amount_max": peak,
        "amount_to_expected": (total / expected) if expected else 0.0,
        "own_account_ratio": len(own) / n if txns else 0.0,
        "crypto_txn_ratio": sum(1 for txn in txns if txn.is_crypto) / n if txns else 0.0,
        "round_txn_ratio": sum(1 for txn in txns if is_round_pounds(txn.amount_gbp)) / n if txns else 0.0,
        "cash_txn_ratio": sum(1 for txn in txns if txn.is_cash) / n if txns else 0.0,
        "n_counterparties": float(len({norm_name(txn.counterparty_name) for txn in txns if txn.counterparty_name})),
        "n_countries": float(len({txn.counterparty_country for txn in txns if txn.counterparty_country})),
        "shared_device": 1.0 if any(txn.device_id in inst.shared_devices for txn in txns) else 0.0,
        "prior_review_count": float(len(reviews)),
        "prior_review_covers": float(covers),
        "above_doc_threshold": above,
        "has_matching_doc": matched,
        "max_own_account_multiple": max(multiples) if multiples else 0.0,
    }
    row.update(_list_flags(inst, case))
    return {name: float(row[name]) for name in FEATURE_NAMES}


def labelled_rows(inst: Institution) -> list[dict]:
    rows = []
    for case in inst.cases:
        decision = decide_case(inst, case)
        features = feature_row(inst, case)
        rows.append(
            {
                "institution": inst.name,
                "case_id": case.id,
                "customer_id": case.customer_id,
                "group": f"{inst.name}::{case.customer_id}",
                "verdict": decision.verdict,
                "reason_code": decision.reason_code,
                "features": features,
            }
        )
    return rows
