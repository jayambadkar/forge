"""Load one institution folder. Paths are absolute. Nothing is read outside root."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .facts import (
    direction_of,
    looks_like_cash,
    looks_like_crypto,
    norm_country,
    norm_dob,
    norm_name,
    parse_amount,
    to_gbp,
)
from .model import (
    Alert,
    Case,
    Customer,
    Evidence,
    Institution,
    ListEntry,
    Review,
    Transaction,
)
from .policy_text import parse_policy

_ID_KEY = re.compile(r"(^id$|_id$|_ids$)", re.I)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _first(row: dict, keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (str, int)):
            return str(value)
    return default


def _strings(value: object) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        if "," in value and not value.strip().startswith("{"):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return (value,)
    if isinstance(value, list):
        found = []
        for item in value:
            if isinstance(item, str):
                found.append(item)
            elif isinstance(item, dict):
                ident = _first(item, ("id", "transaction_id", "txn_id", "alert_id", "evidence_id"))
                if ident:
                    found.append(ident)
        return tuple(found)
    return ()


def _truthy(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _harvest(value: object, into: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and _ID_KEY.search(key):
                if isinstance(item, str) and item:
                    into.add(item)
                elif isinstance(item, list):
                    for part in item:
                        if isinstance(part, str) and part:
                            into.add(part)
                        else:
                            _harvest(part, into)
                else:
                    _harvest(item, into)
            else:
                _harvest(item, into)
    elif isinstance(value, list):
        for item in value:
            _harvest(item, into)


def _customer(row: dict) -> Customer | None:
    ident = _first(row, ("customer_id", "cust_id", "party_id", "client_id", "id"))
    if not ident:
        return None
    expected = None
    for key in (
        "expected_monthly_amount",
        "expected_monthly_turnover",
        "expected_monthly",
        "expected_turnover",
        "profile_monthly_amount",
        "declared_monthly_amount",
    ):
        expected = parse_amount(row.get(key))
        if expected is not None:
            break
    accounts = _strings(row.get("accounts") or row.get("account_ids") or row.get("own_accounts"))
    return Customer(
        id=ident,
        name=_first(row, ("name", "full_name", "customer_name", "legal_name")),
        dob=norm_dob(_first(row, ("dob", "date_of_birth", "birth_date"))),
        country=norm_country(_first(row, ("country", "residence_country", "nationality"))),
        expected_monthly=expected,
        accounts=accounts,
        raw=row,
    )


def _transaction(row: dict) -> Transaction | None:
    ident = _first(row, ("transaction_id", "txn_id", "id"))
    if not ident:
        return None
    currency = _first(row, ("currency", "ccy"), "GBP") or "GBP"
    amount = parse_amount(
        row.get("amount")
        if row.get("amount") is not None
        else row.get("amount_gbp")
        if row.get("amount_gbp") is not None
        else row.get("value")
    )
    reference = _first(row, ("reference", "payment_reference", "narrative", "description", "memo"))
    crypto_flag = _truthy(row.get("is_crypto") if "is_crypto" in row else row.get("crypto"))
    cash_flag = _truthy(row.get("is_cash") if "is_cash" in row else row.get("cash"))
    return Transaction(
        id=ident,
        customer_id=_first(row, ("customer_id", "party_id", "cust_id")),
        timestamp=_first(row, ("timestamp", "datetime", "date", "posted_at", "value_date")),
        amount=amount or 0.0,
        currency=currency.upper(),
        amount_gbp=to_gbp(amount, currency),
        direction=direction_of(_first(row, ("direction", "credit_debit", "dc_flag", "flow"))),
        counterparty_name=_first(
            row,
            ("counterparty_name", "counterparty", "beneficiary_name", "merchant_name", "payee_name", "originator_name"),
        ),
        counterparty_account=_first(
            row, ("counterparty_account", "beneficiary_account", "cp_account", "payee_account")
        ),
        counterparty_country=norm_country(_first(row, ("counterparty_country", "destination_country", "country"))),
        own_account=_truthy(row.get("own_account") if "own_account" in row else row.get("is_own_account")),
        device_id=_first(row, ("device_id", "device", "device_fingerprint")),
        reference=reference,
        is_crypto=bool(crypto_flag) or looks_like_crypto(reference, _first(row, ("channel", "rail", "type"))),
        is_cash=bool(cash_flag) or looks_like_cash(reference, _first(row, ("channel", "rail", "type"))),
        raw=row,
    )


def _alert(row: dict) -> Alert | None:
    ident = _first(row, ("alert_id", "id"))
    if not ident:
        return None
    currency = _first(row, ("currency", "ccy"), "GBP") or "GBP"
    amount = parse_amount(row.get("amount"))
    typology = _first(row, ("typology", "scenario", "rule", "rule_name", "alert_type", "category", "type"))
    narrative = _first(row, ("narrative", "description", "details", "summary", "reason"))
    tx_ids = _strings(
        row.get("transaction_ids")
        if "transaction_ids" in row
        else row.get("transactions")
        if "transactions" in row
        else row.get("txn_ids")
    )
    return Alert(
        id=ident,
        case_id=_first(row, ("case_id",)),
        customer_id=_first(row, ("customer_id", "party_id", "cust_id")),
        typology=typology,
        narrative=narrative,
        transaction_ids=tx_ids,
        amount=amount,
        currency=currency.upper(),
        amount_gbp=to_gbp(amount, currency),
        matched_list_id=_first(row, ("matched_list_id", "list_id", "list_entry_id")),
        matched_name=_first(row, ("matched_name", "screened_name", "hit_name")),
        raw=row,
    )


def _evidence_from_row(row: dict) -> Evidence | None:
    ident = _first(row, ("evidence_id", "doc_id", "document_id", "id"))
    title = _first(row, ("title", "name", "filename"))
    if not ident:
        ident = Path(title).stem if title else ""
    if not ident:
        return None
    text = _first(row, ("text", "body", "content", "summary"))
    return Evidence(
        id=ident,
        case_id=_first(row, ("case_id",)),
        customer_id=_first(row, ("customer_id", "party_id")),
        kind=_first(row, ("kind", "doc_type", "type", "category")),
        title=title,
        text=text,
        amount=parse_amount(row.get("amount")),
        path=_first(row, ("path", "file", "uri")),
    )


def _review(row: dict) -> Review | None:
    ident = _first(row, ("review_id", "id"))
    if not ident:
        return None
    text = _first(row, ("text", "summary", "narrative", "description", "outcome_notes", "notes"))
    typology = _first(row, ("typology", "typologies", "scope"))
    if typology and typology.lower() not in text.lower():
        text = f"{text} Typology: {typology}."
    return Review(
        id=ident,
        customer_id=_first(row, ("customer_id", "party_id", "cust_id")),
        date=_first(row, ("date", "reviewed_at", "timestamp")),
        text=text.strip(),
        raw=row,
    )


def _list_entry(row: dict) -> ListEntry | None:
    ident = _first(row, ("list_id", "entry_id", "id"))
    name = _first(row, ("name", "full_name", "matched_name", "entity_name"))
    if not ident or not name:
        return None
    return ListEntry(
        id=ident,
        name=name,
        kind=_first(row, ("kind", "type", "list_type", "category")),
        dob=norm_dob(_first(row, ("dob", "date_of_birth", "birth_date"))),
        country=norm_country(_first(row, ("country", "nationality"))),
        raw=row,
    )


def _attach_markdown(root: Path, evidence: dict[str, Evidence], ids: set[str]) -> None:
    folder = root / "evidence"
    if not folder.is_dir():
        return
    files = sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".txt"})
    for path in files:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        stem = path.stem
        target = None
        for item in evidence.values():
            if item.path == rel or item.path.endswith(path.name) or item.id == stem:
                target = item
                break
        if target is None:
            evidence[stem] = Evidence(
                id=stem,
                case_id="",
                customer_id="",
                kind="",
                title=path.name,
                text=text,
                amount=None,
                path=rel,
            )
            ids.add(stem)
        else:
            if text and text not in target.text:
                target.text = f"{target.text}\n{text}".strip()
            target.path = target.path or rel
            ids.add(target.id)


def load_institution(folder: Path) -> Institution:
    root = folder.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"institution folder not found: {folder}")
    policy_path = root / "POLICY.md"
    policy_text = policy_path.read_text(encoding="utf-8") if policy_path.is_file() else ""

    ids: set[str] = set()
    customers: dict[str, Customer] = {}
    for row in _read_jsonl(root / "customers.jsonl"):
        _harvest(row, ids)
        customer = _customer(row)
        if customer:
            customers[customer.id] = customer
            ids.add(customer.id)

    transactions: dict[str, Transaction] = {}
    by_customer: dict[str, list[Transaction]] = {}
    for row in _read_jsonl(root / "transactions.jsonl"):
        _harvest(row, ids)
        txn = _transaction(row)
        if not txn:
            continue
        transactions[txn.id] = txn
        ids.add(txn.id)
        by_customer.setdefault(txn.customer_id, []).append(txn)

    alerts: dict[str, Alert] = {}
    for row in _read_jsonl(root / "alerts.jsonl"):
        _harvest(row, ids)
        alert = _alert(row)
        if not alert:
            continue
        alerts[alert.id] = alert
        ids.add(alert.id)

    evidence: dict[str, Evidence] = {}
    for row in _read_jsonl(root / "evidence.jsonl"):
        _harvest(row, ids)
        item = _evidence_from_row(row)
        if not item:
            continue
        evidence[item.id] = item
        ids.add(item.id)
    _attach_markdown(root, evidence, ids)

    reviews_by_customer: dict[str, list[Review]] = {}
    for row in _read_jsonl(root / "previous_reviews.jsonl"):
        _harvest(row, ids)
        review = _review(row)
        if not review:
            continue
        ids.add(review.id)
        reviews_by_customer.setdefault(review.customer_id, []).append(review)

    list_entries = []
    list_by_id = {}
    list_by_name: dict[str, list[ListEntry]] = {}
    for row in _read_jsonl(root / "internal_list.jsonl"):
        _harvest(row, ids)
        entry = _list_entry(row)
        if not entry:
            continue
        list_entries.append(entry)
        list_by_id[entry.id] = entry
        ids.add(entry.id)
        list_by_name.setdefault(norm_name(entry.name), []).append(entry)

    cases: list[Case] = []
    seen_cases: set[str] = set()
    for row in _read_jsonl(root / "cases.jsonl"):
        _harvest(row, ids)
        ident = _first(row, ("case_id", "id"))
        if not ident or ident in seen_cases:
            continue
        seen_cases.add(ident)
        ids.add(ident)
        alert_ids = _strings(row.get("alert_ids") if "alert_ids" in row else row.get("alerts"))
        if not alert_ids:
            alert_ids = tuple(alert.id for alert in alerts.values() if alert.case_id == ident)
        customer_id = _first(row, ("customer_id", "party_id", "cust_id"))
        if not customer_id:
            for alert_id in alert_ids:
                alert = alerts.get(alert_id)
                if alert and alert.customer_id:
                    customer_id = alert.customer_id
                    break
        evidence_ids = _strings(row.get("evidence_ids") if "evidence_ids" in row else row.get("evidence"))
        cases.append(
            Case(
                id=ident,
                customer_id=customer_id,
                alert_ids=alert_ids,
                evidence_ids=evidence_ids,
                raw=row,
            )
        )

    if not cases:
        grouped: dict[str, list[str]] = {}
        for alert in alerts.values():
            grouped.setdefault(alert.case_id or alert.id, []).append(alert.id)
        for ident in sorted(grouped):
            alert_ids = tuple(grouped[ident])
            customer_id = ""
            for alert_id in alert_ids:
                if alerts[alert_id].customer_id:
                    customer_id = alerts[alert_id].customer_id
                    break
            cases.append(Case(id=ident, customer_id=customer_id, alert_ids=alert_ids, evidence_ids=(), raw={}))
            ids.add(ident)

    device_customers: dict[str, set[str]] = {}
    for txn in transactions.values():
        if txn.device_id and txn.customer_id:
            device_customers.setdefault(txn.device_id, set()).add(txn.customer_id)
    shared = frozenset(device for device, owners in device_customers.items() if len(owners) >= 2)

    return Institution(
        root=root,
        name=root.name,
        policy=parse_policy(policy_text),
        customers=customers,
        transactions=transactions,
        transactions_by_customer={key: tuple(value) for key, value in by_customer.items()},
        alerts=alerts,
        evidence=evidence,
        reviews_by_customer={key: tuple(value) for key, value in reviews_by_customer.items()},
        list_entries=tuple(list_entries),
        list_by_id=list_by_id,
        list_by_name={key: tuple(value) for key, value in list_by_name.items()},
        cases=tuple(cases),
        all_ids=frozenset(ids),
        shared_devices=shared,
    )
