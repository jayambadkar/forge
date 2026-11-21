"""Synthetic cases for every official close, request and escalation.

Nothing here is copied from the development book. Names, amounts and document
wording are made up so a pass still holds if the dev extract changes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from forge_engine.sop import score_folder

ROOT = Path(__file__).resolve().parents[1]


def _write(folder: Path, name: str, rows: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _customer(
    cid: str, name: str, *, kind: str = "individual", income: float = 2000, activity: str = "", occupation: str = ""
) -> dict:
    return {
        "customer_id": cid,
        "name": name,
        "kind": kind,
        "occupation": occupation or None,
        "business_activity": activity or None,
        "employer": None,
        "declared": {"monthly_income_gbp": income, "annual_turnover_gbp": income * 12 if kind == "business" else None},
    }


def _tx(
    tid: str, cid: str, amount: float, counterparty: str, *, direction: str = "in", country: str = "United Kingdom"
) -> dict:
    return {
        "transaction_id": tid,
        "customer_id": cid,
        "account_id": f"ACCT-{cid}",
        "booked_at": "2026-06-01T09:00:00Z",
        "direction": direction,
        "channel": "transfer",
        "amount_gbp": amount,
        "counterparty_name": counterparty,
        "counterparty_country": country,
        "reference": "PAYMENT",
        "currency": "GBP",
    }


def _alert(aid: str, rule: str, tids: list[str], measured: dict | None = None) -> dict:
    return {
        "alert_id": aid,
        "rule_id": rule,
        "rule_name": rule,
        "message": rule,
        "measured": measured or {},
        "transaction_ids": tids,
    }


def _case(case_id: str, cid: str, alerts: list[str]) -> dict:
    return {"case_id": case_id, "customer_id": cid, "opened_at": "2026-06-02T06:00:00Z", "alert_ids": alerts}


def _doc(folder: Path, doc_id: str, cid: str, kind: str, title: str, body: str) -> dict:
    relative = f"evidence/{doc_id}.md"
    path = folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n**Document ID:** {doc_id}\n\n{body}\n", encoding="utf-8")
    return {"doc_id": doc_id, "customer_id": cid, "type": kind, "title": title, "dated": "2026-06-01", "file": relative}


def _score(folder: Path) -> dict[str, object]:
    return {item.case_id: item for item in score_folder(folder)}


def test_engine_source_has_no_development_identifiers():
    text = (ROOT / "system" / "forge_engine" / "sop.py").read_text(encoding="utf-8")
    assert not re.search(r"\b(?:BK|EM|IV|PX)-(?:CS|AL|C|T|L)\d+", text)
    assert "Stanwick" not in text
    assert "Coinvale" not in text


def test_close_request_and_escalate_paths(tmp_path: Path):
    folder = tmp_path / "bank"
    customers, alerts, txs, cases, docs, listed = [], [], [], [], [], []

    def add(customer, alert, transactions, documents=(), list_rows=()):
        customers.append(customer)
        alerts.append(alert)
        txs.extend(transactions)
        cases.append(_case(customer["customer_id"].replace("C", "CASE"), customer["customer_id"], [alert["alert_id"]]))
        docs.extend(documents)
        listed.extend(list_rows)

    add(
        _customer("C-OWN", "Ada North"),
        _alert("A-OWN", "TM01", ["T-OWN"], {"received_gbp": 3000, "baseline_gbp": 2000, "multiple": 1.5}),
        [_tx("T-OWN", "C-OWN", 3000, "Ada North")],
        [_doc(folder, "STM-OWN", "C-OWN", "bank_statement", "Statement for Ada North", "Account held by Ada North.")],
    )
    add(
        _customer("C-FIVE", "Bea North", income=1000),
        _alert("A-FIVE", "TM01", ["T-FIVE"], {"received_gbp": 5000, "baseline_gbp": 1000, "multiple": 5}),
        [_tx("T-FIVE", "C-FIVE", 5000, "Bea North")],
        [_doc(folder, "STM-FIVE", "C-FIVE", "bank_statement", "Statement for Bea North", "Account held by Bea North.")],
    )
    add(
        _customer("C-NOST", "Cal North"),
        _alert("A-NOST", "TM02", ["T-NOST"]),
        [_tx("T-NOST", "C-NOST", 900, "Cal North")],
    )
    add(
        _customer("C-FEST", "Delta Events Ltd", kind="business", income=8000, activity="Runs music and food festivals"),
        _alert("A-FEST", "TM03", ["T-F1", "T-F2"], {"count": 2, "total_gbp": 1500}),
        [_tx("T-F1", "C-FEST", 700, ""), _tx("T-F2", "C-FEST", 800, "")],
        [
            _doc(
                folder,
                "REC-FEST",
                "C-FEST",
                "cash_reconciliation",
                "Sheets for the harbour festival",
                "North gate £700.00. South gate £800.00.",
            )
        ],
    )
    add(
        _customer("C-NURSE", "Eden Cole", occupation="Librarian"),
        _alert("A-NURSE", "TM03", ["T-N1", "T-N2"], {"count": 2, "total_gbp": 1500}),
        [_tx("T-N1", "C-NURSE", 700, ""), _tx("T-N2", "C-NURSE", 800, "")],
        [
            _doc(
                folder,
                "REC-NURSE",
                "C-NURSE",
                "cash_reconciliation",
                "Sheets for the harbour festival",
                "North gate £700.00. South gate £800.00.",
            )
        ],
    )
    add(
        _customer("C-PARK", "Fable Parking Ltd", kind="business", income=9000, activity="Car park operator"),
        _alert("A-PARK", "TM03", ["T-P1"], {"count": 1, "total_gbp": 9600}),
        [_tx("T-P1", "C-PARK", 9600, "")],
        [
            _doc(
                folder,
                "COL-PARK",
                "C-PARK",
                "cash_collection_reports",
                "Collections for Fable Parking Ltd",
                "Machine banked £9,600.00.",
            )
        ],
    )
    add(
        _customer("C-SALE", "Gale Orth"),
        _alert("A-SALE", "TM05", ["T-SALE"], {"amount_gbp": 1400}),
        [_tx("T-SALE", "C-SALE", 1400, "")],
        [
            _doc(
                folder,
                "SAL-1",
                "C-SALE",
                "sale_receipt",
                "Sale receipt for Gale Orth",
                "Gale Orth sold a bicycle for £1,400.00.",
            )
        ],
    )
    add(
        _customer("C-COR", "Hale Imports Ltd", kind="business", income=20000),
        _alert("A-COR", "TM06", ["T-COR"], {"countries": "Iraq", "total_gbp": 22000}),
        [_tx("T-COR", "C-COR", 22000, "Cedar Fruit Co", country="Iraq")],
        [
            _doc(
                folder,
                "INV-COR",
                "C-COR",
                "supplier_invoice",
                "Invoice from Cedar Fruit Co",
                "Cedar Fruit Co, Iraq. Amount £22,000.00.",
            )
        ],
    )
    add(
        _customer("C-GRP", "Ivy Supplies Ltd", kind="business", income=20000),
        _alert("A-GRP", "TM08", ["T-GRP"]),
        [_tx("T-GRP", "C-GRP", 18000, "Ivy Holdings Ltd")],
        [
            _doc(
                folder,
                "GRP-1",
                "C-GRP",
                "group_structure",
                "Group chart",
                "Ivy Supplies Ltd and Ivy Holdings Ltd share one owner.",
            )
        ],
    )
    add(
        _customer("C-GIFT", "Juniper Oak"),
        _alert("A-GIFT", "TM08", ["T-GIFT"]),
        [_tx("T-GIFT", "C-GIFT", 4000, "Kit Oak")],
        [_doc(folder, "GFT-1", "C-GIFT", "gift_letter", "Gift letter", "Kit Oak gives £4,000.00 to Juniper Oak.")],
    )
    add(
        _customer("C-REF", "Lane Orth"),
        _alert("A-REF", "TM02", ["T-REF-IN", "T-REF-OUT"]),
        [
            _tx("T-REF-IN", "C-REF", 2200, "Lane Orth"),
            _tx("T-REF-OUT", "C-REF", 2200, "Lane Orth", direction="out"),
        ],
        [
            _doc(
                folder,
                "CAN-1",
                "C-REF",
                "cancellation_confirmation",
                "Cancellation",
                "Subscription of £2,200.00 is being returned.",
            )
        ],
    )
    add(
        _customer("C-RET", "Moss Orth"),
        _alert("A-RET", "TM07", ["T-RET"], {"moved_gbp": 2500, "dormant_days": 200}),
        [_tx("T-RET", "C-RET", 2500, "Moss Orth")],
        [
            _doc(
                folder,
                "RVF-1",
                "C-RET",
                "reverification_record",
                "Reverification of Moss Orth",
                "Identity checked when the account was used again.",
            )
        ],
    )
    add(
        _customer("C-DIFF", "Nell Orth"),
        _alert("A-DIFF", "TM22", ["T-DIFF"], {"list_entry": "L-DIFF", "matched_party": "Nell Porter"}),
        [_tx("T-DIFF", "C-DIFF", 500, "Nell Porter")],
        [
            _doc(
                folder,
                "REG-DIFF",
                "C-DIFF",
                "company_register_extract",
                "Register",
                "Director Nell Porter, born March 1981.",
            )
        ],
        [{"entry_id": "L-DIFF", "name": "Nell Porter", "date_of_birth": "1974-03-01", "kind": "person"}],
    )
    add(
        _customer("C-SAME", "Ora Orth"),
        _alert("A-SAME", "TM22", ["T-SAME"], {"list_entry": "L-SAME", "matched_party": "Ora Quinn"}),
        [_tx("T-SAME", "C-SAME", 500, "Ora Quinn")],
        [
            _doc(
                folder,
                "REG-SAME",
                "C-SAME",
                "company_register_extract",
                "Register",
                "Director Ora Quinn, born March 1974. Resigned the post.",
            )
        ],
        [{"entry_id": "L-SAME", "name": "Ora Quinn", "date_of_birth": "1974-03-01", "kind": "person"}],
    )
    add(
        _customer("C-NAME", "Pip Orth"),
        _alert("A-NAME", "TM22", ["T-NAME"], {"list_entry": "L-NAME", "matched_party": "Pip Quinn"}),
        [_tx("T-NAME", "C-NAME", 500, "Pip Quinn")],
        [],
        [{"entry_id": "L-NAME", "name": "Pip Quinn", "date_of_birth": None, "kind": "person"}],
    )
    add(
        _customer("C-MULE", "Quin Orth"),
        _alert("A-MULE", "TM02", ["T-MULE-IN", "T-MULE-OUT"]),
        [
            _tx("T-MULE-IN", "C-MULE", 8000, "Other Payer Ltd"),
            _tx("T-MULE-OUT", "C-MULE", 7900, "Some Person", direction="out"),
        ],
        [
            _doc(
                folder,
                "RPT-1",
                "C-MULE",
                "sending_bank_fraud_report",
                "Fraud report",
                "Please freeze funds received by Quin Orth.",
            )
        ],
    )
    add(
        _customer("C-COR2", "Red Imports Ltd", kind="business", income=20000),
        _alert("A-COR2", "TM06", ["T-COR2"], {"countries": "Lebanon", "total_gbp": 9000}),
        [_tx("T-COR2", "C-COR2", 9000, "Some Trader Ltd", country="Lebanon")],
    )
    add(
        _customer("C-EARLY", "Sage Orth"),
        _alert("A-EARLY", "TM10", ["T-EARLY"]),
        [_tx("T-EARLY", "C-EARLY", 6000, "Sage Orth", direction="out")],
    )
    add(
        _customer("C-RED", "Tara Orth"),
        _alert("A-RED", "TM10", ["T-RED"]),
        [_tx("T-RED", "C-RED", 6000, "Tara Orth", direction="out")],
        [
            _doc(
                folder,
                "RED-1",
                "C-RED",
                "redundancy_letter",
                "Redundancy letter",
                "Tara Orth's role has been made redundant.",
            )
        ],
    )
    add(
        _customer("C-ASK", "Uma Orth"),
        _alert("A-ASK", "TM08", ["T-ASK"]),
        [_tx("T-ASK", "C-ASK", 3500, "Vale Trading Ltd")],
    )

    _write(folder, "customers.jsonl", customers)
    _write(folder, "alerts.jsonl", alerts)
    _write(folder, "transactions.jsonl", txs)
    _write(folder, "cases.jsonl", cases)
    _write(folder, "evidence.jsonl", docs)
    _write(folder, "previous_reviews.jsonl", [])
    _write(folder, "internal_list.jsonl", listed)
    decided = _score(folder)

    def expect(cid: str, verdict: str, code: str) -> None:
        item = decided[cid.replace("C", "CASE")]
        assert item.verdict == verdict, (cid, item.verdict, item.reason_code, item.reason)
        assert item.reason_code == code, (cid, item.reason)

    expect("C-OWN", "CLOSE", "OWN_ACCOUNT")
    expect("C-FIVE", "RFI", "RFI_UPDATED_PROFILE")
    expect("C-NOST", "RFI", "RFI_SOURCE_OF_FUNDS")
    expect("C-FEST", "CLOSE", "BUSINESS_RECORDS_RECONCILE")
    expect("C-NURSE", "ESCALATE", "ESC_STRUCTURING")
    expect("C-PARK", "CLOSE", "COLLECTION_DOCUMENTED")
    expect("C-SALE", "CLOSE", "DOCUMENTED_EVENT")
    expect("C-COR", "CLOSE", "INVOICE_MATCHES")
    expect("C-GRP", "CLOSE", "GROUP_COMPANY")
    expect("C-GIFT", "CLOSE", "THIRD_PARTY_DOCUMENTED")
    expect("C-REF", "CLOSE", "REFUND_OF_EARLIER_PAYMENT")
    expect("C-RET", "CLOSE", "RETURNING_CUSTOMER")
    expect("C-DIFF", "CLOSE", "LIST_MATCH_DIFFERENT_PARTY")
    expect("C-SAME", "ESCALATE", "ESC_LISTED_PARTY")
    expect("C-NAME", "RFI", "RFI_COUNTERPARTY_DETAILS")
    expect("C-MULE", "ESCALATE", "ESC_MULE_ACTIVITY")
    expect("C-COR2", "ESCALATE", "ESC_HIGH_RISK_CORRIDOR")
    expect("C-EARLY", "ESCALATE", "ESC_EARLY_REDEMPTION")
    expect("C-RED", "CLOSE", "DOCUMENTED_EVENT")
    expect("C-ASK", "RFI", "RFI_COUNTERPARTY_DETAILS")


def test_invoice_mismatch_needs_the_payments_firm(tmp_path: Path):
    folder = tmp_path / "payments_fx"
    customer = _customer("C-MIS", "Wren Imports Ltd", kind="business", income=40000)
    alert = _alert("A-MIS", "TM08", ["T-MIS"])
    tx = _tx("T-MIS", "C-MIS", 30000, "Xenon Manufacturing Co", direction="out")
    doc = _doc(
        folder,
        "INV-MIS",
        "C-MIS",
        "supplier_invoice",
        "Invoice from Xenon Manufacturing Co",
        "Xenon Manufacturing Co. Amount £18,000.00.",
    )
    case = _case("CASE-MIS", "C-MIS", ["A-MIS"])
    _write(folder, "customers.jsonl", [customer])
    _write(folder, "alerts.jsonl", [alert])
    _write(folder, "transactions.jsonl", [tx])
    _write(folder, "cases.jsonl", [case])
    _write(folder, "evidence.jsonl", [doc])
    _write(folder, "previous_reviews.jsonl", [])
    _write(folder, "internal_list.jsonl", [])
    decided = _score(folder)["CASE-MIS"]
    assert decided.verdict == "ESCALATE"
    assert decided.reason_code == "ESC_INVOICE_MISMATCH"
