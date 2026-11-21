"""Build the demo institution books from the SOP scenarios.

The expected verdicts are the labelling function applied by hand to each
scenario. They are not development-set labels, and the engine does not import
this file.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "fixtures" / "demo" / "institutions"

COMMON = """
Own-account transfers may be closed when the amount is within 5x the customer's expected monthly amount.

Internal list: escalate a confirmed match (the same name and the same date of birth,
or the same exact name and the same country). A name-only match is not confirmed;
ask the customer to confirm identity. A match whose date of birth contradicts the
customer is not a match and the screening alert may be closed.

Previous reviews cover only the activity they describe.

Round amounts, a shared device, and crypto are context only. They are not a ground for a decision.

Activity within the customer's expected monthly amount may be
closed as expected activity when it is in the customer's country
and is not cash, crypto, or a screening alert.
""".strip()

POLICIES = {
    "bank": COMMON + "\n\nCash deposits of £8,000 or more are escalated.\n",
    "payments_fx": COMMON + "\n\nAn invoice is required for outbound payments of £10,000 or more.\n",
    "emoney": COMMON + "\n\nA source of funds is required for inbound loads of £5,000 or more.\n",
    "investment": COMMON + "\n\nA subscription agreement is required for subscriptions of £25,000 or more.\n",
}


def _dump(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def _customer(cid, name, dob, country, expected, accounts):
    return {
        "customer_id": cid,
        "name": name,
        "dob": dob,
        "country": country,
        "expected_monthly_amount": expected,
        "accounts": accounts,
    }


def _txn(tid, cid, amount, direction, counterparty, **extra):
    row = {
        "transaction_id": tid,
        "customer_id": cid,
        "timestamp": extra.pop("timestamp", "2026-03-04T10:15:00Z"),
        "amount": amount,
        "currency": "GBP",
        "direction": direction,
        "counterparty_name": counterparty,
        "counterparty_account": extra.pop("account", ""),
        "counterparty_country": extra.pop("country", "GB"),
        "own_account": extra.pop("own_account", False),
        "device_id": extra.pop("device_id", ""),
        "reference": extra.pop("reference", ""),
        "is_crypto": extra.pop("is_crypto", False),
        "is_cash": extra.pop("is_cash", False),
    }
    row.update(extra)
    return row


def _alert(aid, case_id, cid, typology, txn_ids, narrative=""):
    return {
        "alert_id": aid,
        "case_id": case_id,
        "customer_id": cid,
        "typology": typology,
        "narrative": narrative,
        "transaction_ids": txn_ids,
    }


def _case(case_id, cid, alert_ids):
    return {"case_id": case_id, "customer_id": cid, "alert_ids": alert_ids}


def _evidence(eid, cid, kind, title, body, amount=None):
    return {
        "evidence_id": eid,
        "customer_id": cid,
        "case_id": "",
        "kind": kind,
        "title": title,
        "text": body,
        "amount": amount,
        "path": f"evidence/{eid}.md",
    }


def _review(rid, cid, text):
    return {"review_id": rid, "customer_id": cid, "date": "2025-11-02", "summary": text}


def _list(lid, name, dob="", country=""):
    return {"list_id": lid, "name": name, "type": "internal", "dob": dob, "country": country}


def build() -> dict:
    expected: dict[str, dict[str, dict[str, str]]] = {}

    def bank():
        customers, txns, alerts, cases, evidence, reviews, listed = [], [], [], [], [], [], []
        # 1 own account inside 5x
        customers.append(_customer("cus-helen", "Helen Ward", "1988-02-02", "GB", 2000, ["102938", "102939"]))
        txns.append(
            _txn(
                "txn-helen",
                "cus-helen",
                4200,
                "out",
                "Helen Ward",
                account="102939",
                own_account=True,
                reference="Move to savings",
            )
        )
        alerts.append(_alert("al-helen", "b-own-ok", "cus-helen", "own account transfer", ["txn-helen"]))
        cases.append(_case("b-own-ok", "cus-helen", ["al-helen"]))
        # 2 own account over 5x
        customers.append(_customer("cus-marcus", "Marcus Hale", "1979-07-19", "GB", 2000, ["440011", "440012"]))
        txns.append(
            _txn(
                "txn-marcus",
                "cus-marcus",
                18000,
                "out",
                "Marcus Hale",
                account="440012",
                own_account=True,
                reference="Own account sweep",
                timestamp="2026-03-05T09:00:00Z",
            )
        )
        alerts.append(_alert("al-marcus", "b-own-over", "cus-marcus", "own account transfer", ["txn-marcus"]))
        cases.append(_case("b-own-over", "cus-marcus", ["al-marcus"]))
        # 3 confirmed list
        customers.append(_customer("cus-priya", "Priya Shah", "1984-03-12", "GB", 3000, ["551100"]))
        txns.append(
            _txn(
                "txn-priya",
                "cus-priya",
                640,
                "out",
                "City Grocer",
                reference="Weekly shop",
                timestamp="2026-03-01T18:02:00Z",
            )
        )
        alerts.append(
            _alert(
                "al-priya",
                "b-list-hit",
                "cus-priya",
                "sanctions screening",
                ["txn-priya"],
                "Potential internal list match",
            )
        )
        cases.append(_case("b-list-hit", "cus-priya", ["al-priya"]))
        listed.append(_list("lst-priya", "Priya Shah", "1984-03-12", "GB"))
        # 4 refuted list
        customers.append(_customer("cus-owen", "Owen Blake", "1990-01-01", "GB", 2500, ["661200"]))
        txns.append(
            _txn(
                "txn-owen",
                "cus-owen",
                90,
                "out",
                "Thames Water",
                reference="Utilities",
                timestamp="2026-02-11T08:00:00Z",
            )
        )
        alerts.append(_alert("al-owen", "b-list-refute", "cus-owen", "sanctions screening", ["txn-owen"]))
        cases.append(_case("b-list-refute", "cus-owen", ["al-owen"]))
        listed.append(_list("lst-owen", "Owen Blake", "1971-06-06", "GB"))
        # 5 weak list
        customers.append(_customer("cus-nora", "Nora Ellis", "", "", 2200, ["771300"]))
        txns.append(
            _txn(
                "txn-nora",
                "cus-nora",
                410,
                "out",
                "Corner Chemist",
                reference="Pharmacy",
                country="",
                timestamp="2026-02-20T12:30:00Z",
            )
        )
        alerts.append(_alert("al-nora", "b-list-weak", "cus-nora", "sanctions screening", ["txn-nora"]))
        cases.append(_case("b-list-weak", "cus-nora", ["al-nora"]))
        listed.append(_list("lst-nora", "Nora Ellis"))
        # 6 review covers salary
        customers.append(_customer("cus-leah", "Leah Okonkwo", "1992-09-09", "GB", 1000, ["881400"]))
        txns.append(
            _txn("txn-leah", "cus-leah", 2400, "in", "Acme Ltd", reference="Salary", timestamp="2026-02-28T07:00:00Z")
        )
        alerts.append(_alert("al-leah", "b-review-ok", "cus-leah", "salary", ["txn-leah"]))
        cases.append(_case("b-review-ok", "cus-leah", ["al-leah"]))
        reviews.append(
            _review(
                "rev-leah",
                "cus-leah",
                "Reviewed monthly salary from Acme Ltd of £2,400. The typology is salary. No other activity was reviewed.",
            )
        )
        # 7 review does not cover crypto
        customers.append(_customer("cus-tom", "Tom Adler", "1986-12-12", "GB", 5000, ["991500"]))
        txns.append(
            _txn(
                "txn-tom",
                "cus-tom",
                2400,
                "out",
                "Mixer Pool",
                reference="BTC transfer",
                is_crypto=True,
                country="",
                timestamp="2026-03-06T23:11:00Z",
            )
        )
        alerts.append(_alert("al-tom", "b-review-miss", "cus-tom", "crypto transfer", ["txn-tom"]))
        cases.append(_case("b-review-miss", "cus-tom", ["al-tom"]))
        reviews.append(
            _review(
                "rev-tom",
                "cus-tom",
                "Reviewed monthly salary from Acme Ltd of £2,400. The typology is salary. No other activity was reviewed.",
            )
        )
        # 8 expected salary, shared device must not block the close
        customers.append(_customer("cus-ruth", "Ruth Begum", "1995-05-05", "GB", 3000, ["101600"]))
        txns.append(
            _txn(
                "txn-ruth",
                "cus-ruth",
                1800,
                "in",
                "Civic Council",
                reference="Salary",
                device_id="dev-shared",
                timestamp="2026-02-27T07:05:00Z",
            )
        )
        alerts.append(_alert("al-ruth", "b-expected", "cus-ruth", "salary", ["txn-ruth"]))
        cases.append(_case("b-expected", "cus-ruth", ["al-ruth"]))
        # 9 context only
        customers.append(_customer("cus-ivan", "Ivan Petrov", "1981-01-21", "GB", 1000, ["111700"]))
        txns.append(
            _txn(
                "txn-ivan",
                "cus-ivan",
                5000,
                "out",
                "Unknown Desk",
                reference="Transfer",
                device_id="dev-shared",
                timestamp="2026-03-08T15:45:00Z",
            )
        )
        alerts.append(_alert("al-ivan", "b-context", "cus-ivan", "unusual amount", ["txn-ivan"]))
        cases.append(_case("b-context", "cus-ivan", ["al-ivan"]))
        # 10 cash above the line, expectation would otherwise look comfortable
        customers.append(_customer("cus-ada", "Ada Brennan", "1974-04-14", "GB", 20000, ["121800"]))
        txns.append(
            _txn(
                "txn-ada",
                "cus-ada",
                9000,
                "in",
                "Cash desk",
                reference="Branch deposit",
                is_cash=True,
                timestamp="2026-03-02T11:20:00Z",
            )
        )
        alerts.append(_alert("al-ada", "b-cash", "cus-ada", "cash deposit", ["txn-ada"]))
        cases.append(_case("b-cash", "cus-ada", ["al-ada"]))
        # 11 one explained alert and one that is not
        customers.append(_customer("cus-ned", "Ned Cartwright", "1991-08-08", "GB", 4000, ["131900", "131901"]))
        txns.append(
            _txn(
                "txn-ned-own",
                "cus-ned",
                1000,
                "out",
                "Ned Cartwright",
                account="131901",
                own_account=True,
                timestamp="2026-03-03T10:00:00Z",
            )
        )
        txns.append(
            _txn(
                "txn-ned-out",
                "cus-ned",
                7000,
                "out",
                "Harbour Broker",
                reference="Third party",
                timestamp="2026-03-03T10:05:00Z",
            )
        )
        alerts.append(_alert("al-ned-own", "b-mixed", "cus-ned", "own account transfer", ["txn-ned-own"]))
        alerts.append(_alert("al-ned-out", "b-mixed", "cus-ned", "third party payment", ["txn-ned-out"]))
        cases.append(_case("b-mixed", "cus-ned", ["al-ned-own", "al-ned-out"]))

        expected["bank"] = {
            "b-own-ok": {"verdict": "CLOSE", "reason_code": "OWN_ACCOUNT_WITHIN_LIMIT"},
            "b-own-over": {"verdict": "ESCALATE", "reason_code": "OWN_ACCOUNT_EXCEEDS_MULTIPLE"},
            "b-list-hit": {"verdict": "ESCALATE", "reason_code": "INTERNAL_LIST_MATCH"},
            "b-list-refute": {"verdict": "CLOSE", "reason_code": "LIST_MATCH_REFUTED"},
            "b-list-weak": {"verdict": "RFI", "reason_code": "IDENTITY_CONFIRMATION"},
            "b-review-ok": {"verdict": "CLOSE", "reason_code": "COVERED_BY_PRIOR_REVIEW"},
            "b-review-miss": {"verdict": "ESCALATE", "reason_code": "ACTIVITY_UNEXPLAINED"},
            "b-expected": {"verdict": "CLOSE", "reason_code": "EXPECTED_ACTIVITY"},
            "b-context": {"verdict": "ESCALATE", "reason_code": "ACTIVITY_UNEXPLAINED"},
            "b-cash": {"verdict": "ESCALATE", "reason_code": "CASH_ABOVE_THRESHOLD"},
            "b-mixed": {"verdict": "ESCALATE", "reason_code": "ACTIVITY_UNEXPLAINED"},
        }
        return customers, txns, alerts, cases, evidence, reviews, listed

    def payments():
        customers, txns, alerts, cases, evidence, reviews, listed = [], [], [], [], [], [], []
        customers.append(_customer("cus-north", "Northwind Ltd", "1980-01-01", "GB", 2000, ["200100"]))
        txns.append(
            _txn(
                "txn-north",
                "cus-north",
                15000,
                "out",
                "Baltic Timber",
                reference="Timber invoice pending",
                timestamp="2026-03-12T09:30:00Z",
            )
        )
        alerts.append(_alert("al-north", "p-inv-miss", "cus-north", "high value payment", ["txn-north"]))
        cases.append(_case("p-inv-miss", "cus-north", ["al-north"]))

        customers.append(_customer("cus-harbour", "Harbour Goods Ltd", "1982-02-02", "GB", 2000, ["200200"]))
        txns.append(
            _txn(
                "txn-harbour",
                "cus-harbour",
                15000,
                "out",
                "Kelp and Co",
                reference="Oak shipment",
                timestamp="2026-03-12T11:00:00Z",
            )
        )
        alerts.append(_alert("al-harbour", "p-inv-ok", "cus-harbour", "high value payment", ["txn-harbour"]))
        cases.append(_case("p-inv-ok", "cus-harbour", ["al-harbour"]))
        evidence.append(
            _evidence(
                "ev-harbour",
                "cus-harbour",
                "invoice",
                "Invoice KC-19",
                "Invoice KC-19\nSupplier: Kelp and Co\nCustomer: Harbour Goods Ltd\nAmount: £15,000.00\nGoods: kiln-dried oak.",
                15000,
            )
        )

        customers.append(_customer("cus-lumen", "Lumen Freight Ltd", "1977-03-03", "GB", 2000, ["200300"]))
        txns.append(
            _txn(
                "txn-lumen",
                "cus-lumen",
                15000,
                "out",
                "Quay Motors",
                reference="Vehicle",
                timestamp="2026-03-13T14:10:00Z",
            )
        )
        alerts.append(_alert("al-lumen", "p-inv-bad", "cus-lumen", "high value payment", ["txn-lumen"]))
        cases.append(_case("p-inv-bad", "cus-lumen", ["al-lumen"]))
        evidence.append(
            _evidence(
                "ev-lumen",
                "cus-lumen",
                "invoice",
                "Invoice QM-4",
                "Invoice QM-4\nSupplier: Quay Motors\nAmount: £4,000.00\nGoods: spare parts.",
                4000,
            )
        )

        customers.append(_customer("cus-piper", "Piper Studio", "1993-06-06", "GB", 500, ["200400"]))
        txns.append(
            _txn(
                "txn-piper",
                "cus-piper",
                2000,
                "out",
                "Paper Mill",
                reference="Stock",
                device_id="dev-fx",
                timestamp="2026-03-09T16:00:00Z",
            )
        )
        alerts.append(_alert("al-piper", "p-small", "cus-piper", "round amount", ["txn-piper"]))
        cases.append(_case("p-small", "cus-piper", ["al-piper"]))

        customers.append(_customer("cus-idris", "Idris Cole", "1979-04-04", "GB", 4000, ["200500"]))
        txns.append(
            _txn(
                "txn-idris",
                "cus-idris",
                15000,
                "out",
                "North Sea Parts",
                reference="Engines",
                timestamp="2026-03-14T10:40:00Z",
            )
        )
        alerts.append(_alert("al-idris", "p-list-inv", "cus-idris", "high value payment", ["txn-idris"]))
        cases.append(_case("p-list-inv", "cus-idris", ["al-idris"]))
        listed.append(_list("lst-idris", "Idris Cole", "1979-04-04", "GB"))

        customers.append(_customer("cus-willa", "Willa Grant", "1990-10-10", "GB", 2000, ["200600", "200601"]))
        txns.append(
            _txn(
                "txn-willa",
                "cus-willa",
                3000,
                "out",
                "Willa Grant",
                account="200601",
                own_account=True,
                timestamp="2026-03-01T09:00:00Z",
            )
        )
        alerts.append(_alert("al-willa", "p-own-ok", "cus-willa", "own account transfer", ["txn-willa"]))
        cases.append(_case("p-own-ok", "cus-willa", ["al-willa"]))

        customers.append(_customer("cus-soren", "Soren Blake", "1987-11-11", "GB", 2000, ["200700"]))
        txns.append(
            _txn(
                "txn-soren",
                "cus-soren",
                800,
                "out",
                "Domestic Paper",
                reference="Stationery",
                timestamp="2026-02-18T13:13:00Z",
            )
        )
        alerts.append(_alert("al-soren", "p-under-expected", "cus-soren", "low value payment", ["txn-soren"]))
        cases.append(_case("p-under-expected", "cus-soren", ["al-soren"]))

        expected["payments_fx"] = {
            "p-inv-miss": {"verdict": "RFI", "reason_code": "INVOICE_REQUIRED"},
            "p-inv-ok": {"verdict": "CLOSE", "reason_code": "INVOICE_SUPPORTS_PAYMENT"},
            "p-inv-bad": {"verdict": "ESCALATE", "reason_code": "INVOICE_MISMATCH"},
            "p-small": {"verdict": "ESCALATE", "reason_code": "ACTIVITY_UNEXPLAINED"},
            "p-list-inv": {"verdict": "ESCALATE", "reason_code": "INTERNAL_LIST_MATCH"},
            "p-own-ok": {"verdict": "CLOSE", "reason_code": "OWN_ACCOUNT_WITHIN_LIMIT"},
            "p-under-expected": {"verdict": "CLOSE", "reason_code": "EXPECTED_ACTIVITY"},
        }
        return customers, txns, alerts, cases, evidence, reviews, listed

    def emoney():
        customers, txns, alerts, cases, evidence, reviews, listed = [], [], [], [], [], [], []
        customers.append(_customer("cus-kira", "Kira Novak", "1994-04-18", "GB", 1000, ["300100"]))
        txns.append(
            _txn(
                "txn-kira",
                "cus-kira",
                7000,
                "in",
                "Cash Converter",
                reference="Wallet load",
                timestamp="2026-03-07T19:00:00Z",
            )
        )
        alerts.append(_alert("al-kira", "e-sof-miss", "cus-kira", "large load", ["txn-kira"]))
        cases.append(_case("e-sof-miss", "cus-kira", ["al-kira"]))

        customers.append(_customer("cus-joel", "Joel Mensah", "1989-09-01", "GB", 1000, ["300200"]))
        txns.append(
            _txn(
                "txn-joel",
                "cus-joel",
                7000,
                "in",
                "Joel Mensah Current",
                reference="Load from own bank",
                timestamp="2026-03-07T19:20:00Z",
            )
        )
        alerts.append(_alert("al-joel", "e-sof-ok", "cus-joel", "large load", ["txn-joel"]))
        cases.append(_case("e-sof-ok", "cus-joel", ["al-joel"]))
        evidence.append(
            _evidence(
                "ev-joel",
                "cus-joel",
                "source of funds",
                "Source of funds note",
                "Source of funds for the inbound load. Amount: £7,000.00 from Joel Mensah's current account, payroll savings.",
                7000,
            )
        )

        customers.append(_customer("cus-mina", "Mina Shah", "1998-08-08", "GB", 1500, ["300300"]))
        txns.append(
            _txn(
                "txn-mina", "cus-mina", 400, "in", "Corner Kiosk", reference="Top up", timestamp="2026-02-02T08:08:00Z"
            )
        )
        alerts.append(_alert("al-mina", "e-expected", "cus-mina", "wallet top up", ["txn-mina"]))
        cases.append(_case("e-expected", "cus-mina", ["al-mina"]))

        customers.append(_customer("cus-farid", "Farid Osman", "1976-06-16", "GB", 2000, ["300400"]))
        txns.append(
            _txn(
                "txn-farid", "cus-farid", 220, "out", "Bus Ticket", reference="Travel", timestamp="2026-02-14T07:40:00Z"
            )
        )
        alerts.append(_alert("al-farid", "e-list", "cus-farid", "sanctions screening", ["txn-farid"]))
        cases.append(_case("e-list", "cus-farid", ["al-farid"]))
        listed.append(_list("lst-farid", "Farid Osman", "1976-06-16", "GB"))

        customers.append(_customer("cus-elena", "Elena Voss", "1991-01-30", "GB", 1000, ["300500", "300501"]))
        txns.append(
            _txn(
                "txn-elena",
                "cus-elena",
                12000,
                "out",
                "Elena Voss",
                account="300501",
                own_account=True,
                timestamp="2026-03-10T21:00:00Z",
            )
        )
        alerts.append(_alert("al-elena", "e-own-over", "cus-elena", "own account transfer", ["txn-elena"]))
        cases.append(_case("e-own-over", "cus-elena", ["al-elena"]))

        customers.append(_customer("cus-hassan", "Hassan Iqbal", "1985-05-15", "GB", 800, ["300600"]))
        txns.append(
            _txn(
                "txn-hassan",
                "cus-hassan",
                600,
                "in",
                "North Market",
                reference="Merchant refund",
                timestamp="2026-01-19T15:00:00Z",
            )
        )
        alerts.append(_alert("al-hassan", "e-review-ok", "cus-hassan", "merchant refund", ["txn-hassan"]))
        cases.append(_case("e-review-ok", "cus-hassan", ["al-hassan"]))
        reviews.append(
            _review(
                "rev-hassan",
                "cus-hassan",
                "Reviewed a merchant refund from North Market of £600. The typology is merchant refund.",
            )
        )

        expected["emoney"] = {
            "e-sof-miss": {"verdict": "RFI", "reason_code": "SOURCE_OF_FUNDS_REQUIRED"},
            "e-sof-ok": {"verdict": "CLOSE", "reason_code": "SOURCE_OF_FUNDS_ON_FILE"},
            "e-expected": {"verdict": "CLOSE", "reason_code": "EXPECTED_ACTIVITY"},
            "e-list": {"verdict": "ESCALATE", "reason_code": "INTERNAL_LIST_MATCH"},
            "e-own-over": {"verdict": "ESCALATE", "reason_code": "OWN_ACCOUNT_EXCEEDS_MULTIPLE"},
            "e-review-ok": {"verdict": "CLOSE", "reason_code": "COVERED_BY_PRIOR_REVIEW"},
        }
        return customers, txns, alerts, cases, evidence, reviews, listed

    def investment():
        customers, txns, alerts, cases, evidence, reviews, listed = [], [], [], [], [], [], []
        customers.append(_customer("cus-bram", "Bram Holdings", "1970-01-01", "GB", 4000, ["400100"]))
        txns.append(
            _txn(
                "txn-bram",
                "cus-bram",
                30000,
                "out",
                "Forge Capital Fund",
                reference="Subscription",
                timestamp="2026-03-16T10:00:00Z",
            )
        )
        alerts.append(_alert("al-bram", "i-sub-miss", "cus-bram", "subscription", ["txn-bram"]))
        cases.append(_case("i-sub-miss", "cus-bram", ["al-bram"]))

        customers.append(_customer("cus-cleo", "Cleo Ward", "1983-03-03", "GB", 4000, ["400200"]))
        txns.append(
            _txn(
                "txn-cleo",
                "cus-cleo",
                30000,
                "out",
                "Forge Capital Fund",
                reference="Subscription",
                timestamp="2026-03-16T10:05:00Z",
            )
        )
        alerts.append(_alert("al-cleo", "i-sub-ok", "cus-cleo", "subscription", ["txn-cleo"]))
        cases.append(_case("i-sub-ok", "cus-cleo", ["al-cleo"]))
        evidence.append(
            _evidence(
                "ev-cleo",
                "cus-cleo",
                "subscription agreement",
                "Subscription agreement CF-30",
                "Subscription agreement for Forge Capital Fund. Investor: Cleo Ward. Amount: £30,000.00.",
                30000,
            )
        )

        customers.append(_customer("cus-yusuf", "Yusuf Rahman", "1972-12-01", "GB", 6000, ["400300"]))
        txns.append(
            _txn(
                "txn-yusuf",
                "cus-yusuf",
                1500,
                "out",
                "Custodian Fee",
                reference="Quarterly fee",
                timestamp="2026-01-02T00:00:00Z",
            )
        )
        alerts.append(_alert("al-yusuf", "i-list", "cus-yusuf", "sanctions screening", ["txn-yusuf"]))
        cases.append(_case("i-list", "cus-yusuf", ["al-yusuf"]))
        listed.append(_list("lst-yusuf", "Yusuf Rahman", "1972-12-01", "GB"))

        customers.append(_customer("cus-pia", "Pia Lorenz", "1996-06-21", "GB", 2000, ["400400"]))
        txns.append(
            _txn(
                "txn-pia",
                "cus-pia",
                5000,
                "out",
                "Exchange Desk",
                reference="ETH purchase",
                is_crypto=True,
                country="",
                timestamp="2026-03-18T22:10:00Z",
            )
        )
        alerts.append(_alert("al-pia", "i-context", "cus-pia", "crypto transfer", ["txn-pia"]))
        cases.append(_case("i-context", "cus-pia", ["al-pia"]))

        customers.append(_customer("cus-glen", "Glen Porter", "1980-08-30", "GB", 10000, ["400500"]))
        txns.append(
            _txn(
                "txn-glen",
                "cus-glen",
                4000,
                "in",
                "Dividend Agent",
                reference="Distribution",
                timestamp="2026-02-25T09:00:00Z",
            )
        )
        alerts.append(_alert("al-glen", "i-expected", "cus-glen", "distribution", ["txn-glen"]))
        cases.append(_case("i-expected", "cus-glen", ["al-glen"]))

        customers.append(_customer("cus-noor", "Noor Aziz", "1988-02-28", "GB", 2000, ["400600"]))
        txns.append(
            _txn(
                "txn-noor",
                "cus-noor",
                1200,
                "out",
                "Ledger Custodian",
                reference="Quarterly fee",
                timestamp="2026-01-15T09:30:00Z",
            )
        )
        alerts.append(_alert("al-noor", "i-review-ok", "cus-noor", "custody fee", ["txn-noor"]))
        cases.append(_case("i-review-ok", "cus-noor", ["al-noor"]))
        reviews.append(
            _review(
                "rev-noor",
                "cus-noor",
                "Reviewed the quarterly fee to Ledger Custodian of £1,200. The typology is custody fee.",
            )
        )

        expected["investment"] = {
            "i-sub-miss": {"verdict": "RFI", "reason_code": "SUBSCRIPTION_AGREEMENT_REQUIRED"},
            "i-sub-ok": {"verdict": "CLOSE", "reason_code": "SUBSCRIPTION_AGREEMENT_ON_FILE"},
            "i-list": {"verdict": "ESCALATE", "reason_code": "INTERNAL_LIST_MATCH"},
            "i-context": {"verdict": "ESCALATE", "reason_code": "ACTIVITY_UNEXPLAINED"},
            "i-expected": {"verdict": "CLOSE", "reason_code": "EXPECTED_ACTIVITY"},
            "i-review-ok": {"verdict": "CLOSE", "reason_code": "COVERED_BY_PRIOR_REVIEW"},
        }
        return customers, txns, alerts, cases, evidence, reviews, listed

    builders = {"bank": bank, "payments_fx": payments, "emoney": emoney, "investment": investment}
    for name, builder in builders.items():
        customers, txns, alerts, cases, evidence, reviews, listed = builder()
        folder = DEST / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "POLICY.md").write_text(f"# {name} policy\n\n{POLICIES[name]}\n", encoding="utf-8")
        _dump(folder / "customers.jsonl", customers)
        _dump(folder / "transactions.jsonl", txns)
        _dump(folder / "alerts.jsonl", alerts)
        _dump(folder / "cases.jsonl", cases)
        _dump(folder / "evidence.jsonl", evidence)
        _dump(folder / "previous_reviews.jsonl", reviews)
        _dump(folder / "internal_list.jsonl", listed)
        evidence_dir = folder / "evidence"
        evidence_dir.mkdir(exist_ok=True)
        for item in evidence:
            body = item["text"]
            (evidence_dir / f"{item['evidence_id']}.md").write_text(body + "\n", encoding="utf-8")
        # empty files the brief lists, so a folder listing looks complete
        for _extra in ("system",):
            pass
        (folder / "output").mkdir(exist_ok=True)

    (DEST.parent / "expected.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    return expected


if __name__ == "__main__":
    built = build()
    total = sum(len(cases) for cases in built.values())
    print(f"wrote {total} cases under {DEST}")
