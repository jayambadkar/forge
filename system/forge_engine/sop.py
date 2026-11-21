"""Decisions for the official institution folders.

Reads the real jsonl layout and the documents on file. Closes only when a
document, an own-account record, or a refuted list match explains every alert.
Suspicion (fraud reports, structuring without records, an unexplained high-risk
corridor, a confirmed list match) escalates and is never turned into an RFI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .model import Decision, Finding

ENGINE_VERSION = "forge-sop-4"

_MONEY = re.compile(r"£\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)")
_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_BIRTH = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(19\d{2}|20\d{2})\b",
    re.I,
)
_SKIP_DOCS = {"due_diligence_summary", "proof_of_address", "contact_note", "support_chat"}
_INVOICE_TYPES = {
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
_EVENT_TYPES = {
    "solicitor_letter",
    "vehicle_sale_receipt",
    "sale_receipt",
    "insurer_letter",
    "completion_statement",
    "loan_agreement",
    "settlement_letter",
    "redundancy_letter",
    "customer_email",
    "insurance_schedule",
}
_BOOK_TYPES = {
    "cash_collection_reports",
    "cash_reconciliation",
    "takings_book",
    "ticket_report",
    "management_accounts",
    "cash_handling_procedure",
}
# A facility or a gift names a third party. A one-off sale does not.
_RELATION_TYPES = {"gift_letter", "factoring_agreement", "remittance_advice"}
# Words that appear on almost any cash sheet. They do not show the sheet is about this customer.
_SHEET_NOISE = frozenset(
    {
        "cash",
        "reconciliation",
        "sheet",
        "sheets",
        "report",
        "reports",
        "daily",
        "takings",
        "book",
        "ticket",
        "tickets",
        "sales",
        "sale",
        "counted",
        "banked",
        "point",
        "north",
        "south",
        "east",
        "west",
        "main",
        "gate",
        "bar",
        "court",
        "with",
        "from",
        "customer",
        "account",
        "payment",
        "amount",
        "total",
        "date",
        "dated",
        "document",
        "dear",
        "staff",
        "after",
        "closed",
        "next",
        "days",
        "page",
        "table",
    }
)
_ESC_RANK = (
    "ESC_MULE_ACTIVITY",
    "ESC_LISTED_PARTY",
    "ESC_STRUCTURING",
    "ESC_HIGH_RISK_CORRIDOR",
    "ESC_INVOICE_MISMATCH",
    "ESC_EARLY_REDEMPTION",
    "ESC_THIRD_PARTY_FUNDING",
    "ESC_PASS_THROUGH",
    "ESC_ACCOUNT_MISUSE",
    "ESC_UNEXPLAINED_FUNDS",
)
_RFI_RANK = (
    "RFI_UPDATED_PROFILE",
    "RFI_PURPOSE_DOCUMENTS",
    "RFI_BUSINESS_RECORDS",
    "RFI_SOURCE_OF_FUNDS",
    "RFI_COUNTERPARTY_DETAILS",
)


def is_official_folder(folder: Path) -> bool:
    path = folder / "alerts.jsonl"
    if not path.is_file():
        return False
    with path.open(encoding="utf-8") as handle:
        line = handle.readline()
    return '"rule_id"' in line


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def norm(value: str | None) -> str:
    text = (value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\b(ltd|limited|plc|llp|inc|co|the)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def same(left: str | None, right: str | None) -> bool:
    a, b = norm(left), norm(right)
    if len(a) < 4 or len(b) < 4:
        return False
    return a == b or a in b or b in a


def money(amount: float | None) -> str:
    if amount is None:
        return "an unstated amount"
    return f"£{amount:,.2f}"


def _amounts(text: str) -> list[float]:
    return [float(match.group(1).replace(",", "")) for match in _MONEY.finditer(text or "")]


def _near(left: float, right: float, ratio: float = 0.02) -> bool:
    return abs(left - right) <= max(1.0, max(left, right) * ratio)


class Book:
    def __init__(self, folder: Path):
        self.folder = folder
        self.customers = {row["customer_id"]: row for row in _read_jsonl(folder / "customers.jsonl")}
        self.alerts = {row["alert_id"]: row for row in _read_jsonl(folder / "alerts.jsonl")}
        self.transactions = {row["transaction_id"]: row for row in _read_jsonl(folder / "transactions.jsonl")}
        self.cases = _read_jsonl(folder / "cases.jsonl")
        self.reviews: dict[str, list[dict]] = {}
        for row in _read_jsonl(folder / "previous_reviews.jsonl"):
            self.reviews.setdefault(row["customer_id"], []).append(row)
        self.listed = {row["entry_id"]: row for row in _read_jsonl(folder / "internal_list.jsonl")}
        self.docs: dict[str, list[dict]] = {}
        for row in _read_jsonl(folder / "evidence.jsonl"):
            if row.get("type") in _SKIP_DOCS:
                continue
            path = folder / row["file"]
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            row = dict(row)
            row["text"] = text
            row["amounts"] = _amounts(text)
            row["norm"] = norm(f"{row.get('title', '')} {text}")
            self.docs.setdefault(row["customer_id"], []).append(row)
        self.ids = set(self.customers) | set(self.alerts) | set(self.transactions) | set(self.listed)
        for rows in self.docs.values():
            self.ids.update(row["doc_id"] for row in rows)
        for rows in self.reviews.values():
            self.ids.update(row["review_id"] for row in rows)
        for case in self.cases:
            self.ids.add(case["case_id"])


def _baseline(customer: dict) -> float:
    declared = customer.get("declared") or {}
    if customer.get("kind") == "business":
        annual = declared.get("annual_turnover_gbp") or 0
        if annual:
            return float(annual) / 12.0
    return float(declared.get("monthly_income_gbp") or 0)


def _txs(book: Book, alert: dict) -> list[dict]:
    return [book.transactions[tid] for tid in alert.get("transaction_ids") or [] if tid in book.transactions]


def _docs_of(book: Book, customer_id: str, types: set[str] | None = None) -> list[dict]:
    rows = book.docs.get(customer_id, [])
    if types is None:
        return rows
    return [row for row in rows if row.get("type") in types]


def _match_amount(docs: list[dict], amount: float, names: list[str], ratio: float = 0.02) -> list[dict]:
    """Amount match counts only when a named party in the document is the customer or the counterparty.

    A figure on its own is not a ground for closure. Cash lines often have no counterparty name;
    the customer's own name still has to appear on the document.
    """
    hits = []
    wanted = [name for name in (norm(item) for item in names) if name]
    if not wanted:
        return []
    for doc in docs:
        if not any(_near(amount, candidate, ratio) for candidate in doc["amounts"]):
            continue
        if not any(name in doc["norm"] for name in wanted):
            continue
        hits.append(doc)
    return hits


def _content_tokens(text: str) -> set[str]:
    found = set()
    for word in norm(text).split():
        if len(word) < 4 or word in _SHEET_NOISE:
            continue
        if len(word) > 4 and word.endswith("s"):
            word = word[:-1]
        if len(word) >= 4 and word not in _SHEET_NOISE:
            found.add(word)
    return found


def _sheet_about_customer(customer: dict, doc: dict) -> bool:
    """A till sheet closes only when it is this customer's and about their trade.

    Filing alone is not enough, and a matching figure alone is not enough. The
    sheet either names the customer, or it shares a word with their occupation,
    business or employer.
    """
    customer_name = norm(customer.get("name"))
    if len(customer_name) >= 4 and customer_name in doc["norm"]:
        return True
    declared = customer.get("declared") or {}
    profile = " ".join(str(customer.get(key) or "") for key in ("occupation", "business_activity", "employer"))
    profile = f"{profile} {declared.get('account_purpose') or ''}"
    return bool(_content_tokens(profile) & _content_tokens(f"{doc.get('title', '')} {doc.get('text', '')}"))


def _finding(verdict: str, code: str, alert_id: str, evidence: list[str], sentences: tuple[str, str]) -> Finding:
    return Finding(verdict, code, (alert_id,), tuple(evidence), sentences)


def _statement_moves(text: str) -> list[tuple[float, str]]:
    """Amounts on the other account's statement, and the direction they cover here.

    The statement is not this institution's ledger. Money received on that
    statement left here. Money sent from that statement to the customer arrived here.
    """
    chunks = re.split(r"(?<=\.)\s+|(?=\b\d{1,2} [A-Z][a-z]+ \d{4}:)", text or "")
    moves: list[tuple[float, str]] = []
    for chunk in chunks:
        amounts = _amounts(chunk)
        if not amounts:
            continue
        if re.search(r"\breceived\b|\bcredited\b", chunk, re.I):
            direction = "out"
        elif re.search(r"to the customer|transfer of .{0,48}\bout\b|\bpaid out\b", chunk, re.I):
            direction = "in"
        else:
            continue
        moves.extend((amount, direction) for amount in amounts)
    return moves


def _cover_own_transfers(
    customer: dict, txs: list[dict], docs: list[dict]
) -> tuple[list[tuple[dict, dict]], list[dict]]:
    name = norm(customer.get("name") or "")
    pool: list[tuple[dict, float, str]] = []
    if len(name) >= 4:
        for doc in docs:
            if doc.get("type") != "bank_statement" or name not in doc["norm"]:
                continue
            for amount, direction in _statement_moves(doc.get("text") or ""):
                pool.append((doc, amount, direction))
    covered: list[tuple[dict, dict]] = []
    missing: list[dict] = []
    used: set[int] = set()
    ordered = sorted(txs, key=lambda tx: float(tx.get("amount_gbp") or 0), reverse=True)
    for tx in ordered:
        amount = float(tx.get("amount_gbp") or 0)
        direction = tx.get("direction") or ""
        match: tuple[dict, float, str] | None = None
        match_at = -1
        for index, item in enumerate(pool):
            if index in used:
                continue
            if item[2] == direction and _near(amount, item[1], 0.02):
                match = item
                match_at = index
                break
        if match is None:
            missing.append(tx)
            continue
        used.add(match_at)
        covered.append((tx, match[0]))
    return covered, missing


def _one_way(own_txs: list[dict]) -> float:
    """In and out of the same money is one movement, not two.

    Two inbound transfers still add. A round trip does not.
    """
    inbound = sum(float(tx.get("amount_gbp") or 0) for tx in own_txs if tx.get("direction") != "out")
    outbound = sum(float(tx.get("amount_gbp") or 0) for tx in own_txs if tx.get("direction") == "out")
    return max(inbound, outbound)


def _material(own_txs: list[dict], one_way: float) -> list[dict]:
    """Small residuals are not the transfer a close is allowed to rest on."""
    floor = min(500.0, one_way * 0.1) if one_way else 500.0
    return [tx for tx in own_txs if float(tx.get("amount_gbp") or 0) + 0.01 >= floor]


def _own_multiple(customer: dict, own_txs: list[dict], measured: dict) -> float:
    monthly = _baseline(customer)
    from_sum = _one_way(own_txs) / monthly if monthly else 0.0
    raw = measured.get("multiple")
    try:
        measured_multiple = float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        measured_multiple = 0.0
    return max(from_sum, measured_multiple)


def _own_transfers(customer: dict, own_txs: list[dict], docs: list[dict], measured: dict) -> Finding | None:
    """Own-account rule. The five-times test uses the whole movement, not the largest transfer.

    A statement on the customer's other account proves they hold it. Money leaving
    that account is the mirror of money arriving here, so the statement does not
    have to repeat each transfer. At or above five times the declared monthly
    amount, ask for an updated profile.
    """
    if not own_txs:
        return None
    monthly = _baseline(customer)
    one_way = _one_way(own_txs)
    multiple = _own_multiple(customer, own_txs, measured)
    who = customer.get("name") or "the customer"
    tx_ids = [tx["transaction_id"] for tx in own_txs[:6]]
    named_statements = [
        doc for doc in docs if doc.get("type") == "bank_statement" and norm(who) in doc["norm"] and len(norm(who)) >= 4
    ]
    material = _material(own_txs, one_way) or list(own_txs)
    refund_hits: list[tuple[dict, dict]] = []
    refund_gap = 0.0
    for tx in material:
        amount = float(tx.get("amount_gbp") or 0)
        match = next(
            (
                doc
                for doc in docs
                if doc.get("type") in {"cancellation_confirmation", "credit_note"}
                and any(_near(amount, candidate, 0.02) for candidate in doc["amounts"])
            ),
            None,
        )
        if match is None:
            refund_gap += amount
        else:
            refund_hits.append((tx, match))
    if refund_hits and refund_gap <= 0.15 * max(one_way, 1.0):
        doc = refund_hits[0][1]
        return _finding(
            "CLOSE",
            "REFUND_OF_EARLIER_PAYMENT",
            "",
            [*(tx["transaction_id"] for tx, _ in refund_hits), doc["doc_id"]],
            (
                f"{who} moved {money(one_way)} back to an account in their own name.",
                f"Document {doc['doc_id']} ({doc['title']}) confirms that {money(one_way)} is the return of"
                f" an earlier payment, so a fresh source-of-funds statement is not required.",
            ),
        )
    if monthly and multiple >= 5 - 1e-9:
        return _finding(
            "RFI",
            "RFI_UPDATED_PROFILE",
            "",
            [*tx_ids, customer.get("customer_id") or "", *[doc["doc_id"] for doc in named_statements[:2]]],
            (
                f"{who} moved {money(one_way)} between accounts in their own name, {multiple:.2f} times"
                f" the declared monthly amount of {money(monthly)}.",
                "Ask the customer for an updated expected income or turnover before this can be closed.",
            ),
        )
    if named_statements:
        doc = named_statements[0]
        return _finding(
            "CLOSE",
            "OWN_ACCOUNT",
            "",
            [*tx_ids, doc["doc_id"]],
            (
                f"{who} moved {money(one_way)} between accounts in their own name.",
                f"Statement {doc['doc_id']} ({doc['title']}) shows the other account is held in their name."
                + (
                    f" The total is below five times the declared monthly amount of {money(monthly)}."
                    if monthly
                    else " The institution's own-account rule explains the movement."
                ),
            ),
        )
    top = max(own_txs, key=lambda tx: float(tx.get("amount_gbp") or 0))
    amount = float(top.get("amount_gbp") or 0)
    return _finding(
        "RFI",
        "RFI_SOURCE_OF_FUNDS",
        "",
        [top["transaction_id"]],
        (
            f"{who} is named on a transfer of {money(amount)}, but no statement on file shows they hold the other account.",
            f"Ask the customer for a statement in their name covering the account the {money(amount)} moved to or from.",
        ),
    )


def _dissolved_funder(book: Book, customer: dict, txs: list[dict]) -> tuple[dict, str] | None:
    registers = _docs_of(book, customer["customer_id"], {"company_register_extract"})
    for tx in txs:
        if tx.get("direction") != "in":
            continue
        party = tx.get("counterparty_name") or ""
        party_norm = norm(party)
        if not party_norm or same(party, customer.get("name")) or not _COMPANY.search(party):
            continue
        for doc in registers:
            if party_norm in doc["norm"] and re.search(r"\bdissolved\b", doc.get("text") or "", re.I):
                return doc, party
    return None


def _list_decision(book: Book, alert: dict, customer: dict, docs: list[dict], txs: list[dict]) -> Finding:
    measured = alert.get("measured") or {}
    entry = book.listed.get(measured.get("list_entry") or "")
    party = measured.get("matched_party") or (entry or {}).get("name") or "the listed party"
    surname = norm(party).split(",")[0].split()[0] if False else ""
    # Surname from the matched party before the comma.
    head = party.split(",")[0]
    parts = norm(head).split()
    surname = parts[-1] if parts else ""
    list_year = ""
    if entry and entry.get("date_of_birth"):
        list_year = str(entry["date_of_birth"])[:4]
    registers = _docs_of(book, customer["customer_id"], {"company_register_extract", "significant_control_register"})
    years = []
    ceased = False
    for doc in registers:
        for match in _BIRTH.finditer(doc["text"]):
            year = int(match.group(2))
            # Document dates are 2024-2026. A birth year has to be a plausible age.
            if year < 1920 or year > 2005:
                continue
            window = doc["text"][max(0, match.start() - 80) : match.end() + 40].lower()
            if surname and surname in window:
                years.append(match.group(2))
        if surname and surname in doc["norm"] and re.search(r"resign|ceased", doc["text"], re.I):
            ceased = True
    evidence = [alert["alert_id"], measured.get("list_entry") or "", *[tx["transaction_id"] for tx in txs[:3]]]
    evidence.extend(doc["doc_id"] for doc in registers[:2])
    who = customer.get("name") or "the customer"
    amount = txs[0]["amount_gbp"] if txs else None
    payee = txs[0].get("counterparty_name") if txs else "the counterparty"
    if years and list_year and list_year not in years:
        cited = registers[0]["doc_id"] if registers else "the register"
        return _finding(
            "CLOSE",
            "LIST_MATCH_DIFFERENT_PARTY",
            alert["alert_id"],
            evidence,
            (
                f"Alert {alert['alert_id']} matched {party} to list entry {measured.get('list_entry')} on a shared name.",
                f"Document {cited} gives a birth year of {years[0]} for that name, not {list_year}, so"
                f" {payee} on the {money(amount)} payment is a different party.",
            ),
        )
    if years and list_year and list_year in years:
        ceased_note = (
            " A resignation or ceased-control note does not make this a different person while the birth year still matches."
            if ceased
            else ""
        )
        return _finding(
            "ESCALATE",
            "ESC_LISTED_PARTY",
            alert["alert_id"],
            evidence,
            (
                f"Alert {alert['alert_id']} matched {party} to list entry {measured.get('list_entry')}, and the birth year {list_year} agrees.",
                f"The register on file ties that year to the name. {who}'s payment of {money(amount)} to {payee} is escalated.{ceased_note}",
            ),
        )
    return _finding(
        "RFI",
        "RFI_COUNTERPARTY_DETAILS",
        alert["alert_id"],
        evidence,
        (
            f"Alert {alert['alert_id']} matched {party} to list entry {measured.get('list_entry')} on"
            f" {measured.get('matched_on') or 'a listed detail'}, which is not enough to say it is the same party.",
            f"Ask {who} who {payee} is, and for the date of birth or company role of {head}, before the {money(amount)} payment can be closed.",
        ),
    )


_SUSPICIOUS = re.compile(r"\b(exchange|crypto|bitcoin|gambling|casino|mixer|usdt)\b", re.I)
_COMPANY = re.compile(r"\b(ltd|limited|plc|llp|inc|gmbh|llc|co)\b", re.I)


def _review_covers(note: str, counterparty: str, amount: float) -> bool:
    party = norm(counterparty)
    if not party or party not in norm(note):
        return False
    stated = _amounts(note)
    if not stated:
        return False
    return amount <= max(stated) * 1.25 + 0.01


def _code_for_doc(doc: dict) -> str:
    kind = doc.get("type") or ""
    if kind == "group_structure":
        return "GROUP_COMPANY"
    if kind in _RELATION_TYPES:
        return "THIRD_PARTY_DOCUMENTED"
    if kind == "credit_note":
        return "REFUND_OF_EARLIER_PAYMENT"
    if kind in _INVOICE_TYPES or kind == "payment_file":
        return "INVOICE_MATCHES"
    if kind in _BOOK_TYPES:
        return "BUSINESS_RECORDS_RECONCILE"
    return "DOCUMENTED_EVENT"


def _explain_flow(book: Book, alert: dict, customer: dict, txs: list[dict]) -> Finding | None:
    """Explain a set of movements from documents, group charts, or a review that describes them.

    A close needs most of the value tied to a named party. A pass-through to several
    undocumented people, or to a crypto desk, stays an escalation. Otherwise ask.
    """
    movements = [tx for tx in txs if tx.get("channel") != "card"] or list(txs)
    if not movements:
        return None
    docs = book.docs.get(customer["customer_id"], [])
    reviews = book.reviews.get(customer["customer_id"], [])
    explained: list[tuple[dict, str, str]] = []
    unexplained: list[dict] = []
    for tx in movements:
        amount = float(tx.get("amount_gbp") or 0)
        party = tx.get("counterparty_name") or ""
        matched = None
        code = ""
        party_norm = norm(party)
        customer_norm = norm(customer.get("name"))
        # A named third party is explained only by a document that names that party.
        # The customer's own name on a file does not explain someone else's payment.
        for doc in docs:
            if party_norm and party_norm in doc["norm"] and not same(party, customer.get("name")):
                if doc.get("type") == "group_structure":
                    matched, code = doc["doc_id"], "GROUP_COMPANY"
                    break
                if any(_near(amount, candidate, 0.02) for candidate in doc["amounts"]):
                    matched, code = doc["doc_id"], _code_for_doc(doc)
                    break
            elif (not party_norm or same(party, customer.get("name"))) and customer_norm and customer_norm in doc["norm"]:
                if doc.get("type") == "bank_statement":
                    direction = tx.get("direction") or ""
                    covered_line = any(
                        stated_direction == direction and _near(amount, stated, 0.02)
                        for stated, stated_direction in _statement_moves(doc.get("text") or "")
                    )
                    if not covered_line:
                        continue
                    matched, code = doc["doc_id"], "OWN_ACCOUNT"
                    break
                if any(_near(amount, candidate, 0.02) for candidate in doc["amounts"]):
                    matched, code = doc["doc_id"], _code_for_doc(doc)
                    break
        if matched is None:
            for review in reviews:
                if _review_covers(review.get("note") or "", party, amount):
                    matched, code = review["review_id"], "WITHIN_PROFILE"
                    break
        if matched:
            explained.append((tx, matched, code))
        else:
            unexplained.append(tx)
    total = sum(float(tx.get("amount_gbp") or 0) for tx in movements) or 1.0
    covered = sum(float(tx.get("amount_gbp") or 0) for tx, _, _ in explained)
    who = customer.get("name") or "the customer"
    if covered / total >= 0.75 and explained:
        tx, doc_id, code = max(explained, key=lambda item: float(item[0].get("amount_gbp") or 0))
        cited = []
        for _, item_id, _ in explained:
            if item_id not in cited:
                cited.append(item_id)
        party_norm = norm(tx.get("counterparty_name"))
        for doc in docs:
            if doc["doc_id"] in cited or doc["doc_id"] == doc_id:
                continue
            if doc.get("type") == "factoring_agreement" and party_norm and party_norm in doc["norm"]:
                cited.append(doc["doc_id"])
        cited_ids = [alert["alert_id"], doc_id, tx["transaction_id"], *cited]
        shown = ", ".join(cited[:3])
        lead = "Document" if len(cited) == 1 else "Documents"
        verb = "names" if len(cited) == 1 else "name"
        cover = "covers" if len(cited) == 1 else "cover"
        return _finding(
            "CLOSE",
            code,
            alert["alert_id"],
            cited_ids,
            (
                f"Alert {alert['alert_id']} for {who} moves {money(float(tx.get('amount_gbp') or 0))} with {tx.get('counterparty_name') or who}.",
                f"{lead} {shown} {verb} the parties and {cover} {money(covered)} of the {money(total)} on the alert, so the activity is explained.",
            ),
        )
    suspicious_people = []
    for tx in movements:
        name = tx.get("counterparty_name") or ""
        if _SUSPICIOUS.search(name) or _SUSPICIOUS.search(tx.get("reference") or ""):
            suspicious_people.append(name)
    people = []
    person_out = 0.0
    arrived = sum(float(tx.get("amount_gbp") or 0) for tx in movements if tx.get("direction") == "in")
    for tx in unexplained:
        if tx.get("direction") != "out" or same(tx.get("counterparty_name"), customer.get("name")):
            continue
        if _COMPANY.search(tx.get("counterparty_name") or ""):
            continue
        person_out += float(tx.get("amount_gbp") or 0)
        party = norm(tx.get("counterparty_name"))
        if party:
            people.append(party)
    # Onward payment is compared with what arrived. A crypto desk, most of the money paid to one
    # person, or half of it split across three people, is a pass-through. A payment to a company
    # with no invoice is a document request. Three small unexplained names do not escalate the case.
    basis = arrived if arrived > 0 else total
    if suspicious_people or person_out / basis >= 0.8 or (len(set(people)) >= 3 and person_out / basis >= 0.5):
        return None
    if unexplained:
        top = max(unexplained, key=lambda tx: float(tx.get("amount_gbp") or 0))
        payee = top.get("counterparty_name") or top.get("reference") or top.get("channel") or "that payment"
        amount = float(top.get("amount_gbp") or 0)
        return _finding(
            "RFI",
            "RFI_PURPOSE_DOCUMENTS",
            alert["alert_id"],
            [alert["alert_id"], top["transaction_id"]],
            (
                f"Alert {alert['alert_id']} includes {money(amount)} with {payee}, and the documents on file do not explain that payment.",
                f"Ask {who} for the invoice, contract, or payment instruction for {money(amount)} to {payee}, including the payee name and the amount.",
            ),
        )
    return None


def _explain(book: Book, alert: dict, customer: dict) -> Finding:
    docs = book.docs.get(customer["customer_id"], [])
    txs = _txs(book, alert)
    rule = alert.get("rule_id")
    measured = alert.get("measured") or {}
    names = [tx.get("counterparty_name") or "" for tx in txs]
    names.append(customer.get("name") or "")
    [tx for tx in txs if tx.get("direction") == "in"]
    [tx for tx in txs if tx.get("direction") == "out"]

    if rule == "TM22":
        return _list_decision(book, alert, customer, docs, txs)

    frauds = _docs_of(book, customer["customer_id"], {"sending_bank_fraud_report"})
    if frauds and rule in {"TM02", "TM04", "TM08"}:
        return _finding(
            "ESCALATE",
            "ESC_MULE_ACTIVITY",
            alert["alert_id"],
            [alert["alert_id"], frauds[0]["doc_id"], *[tx["transaction_id"] for tx in txs[:4]]],
            (
                f"Alert {alert['alert_id']} ({alert.get('rule_name')}) sits next to fraud report {frauds[0]['doc_id']}.",
                f"{frauds[0]['title']} asks for funds received by {customer.get('name')} to be frozen. The"
                f" activity is escalated rather than put to the customer.",
            ),
        )

    if rule == "TM03":
        books = _docs_of(book, customer["customer_id"], _BOOK_TYPES | {"ticket_report"})
        deposits = [tx.get("amount_gbp") or 0 for tx in txs]
        matched_docs = []
        matched = 0
        for amount in deposits:
            hits = _match_amount(books, amount, [customer.get("name") or ""], ratio=0.01)
            if not hits:
                # Amounts on a sheet filed for this customer count only when the sheet
                # is also about their trade. A matching figure on an unrelated book does not close.
                hits = [
                    doc
                    for doc in books
                    if any(_near(amount, candidate, 0.01) for candidate in doc["amounts"])
                    and _sheet_about_customer(customer, doc)
                ]
            if hits:
                matched += 1
                matched_docs.append(hits[0])
        if deposits and matched >= max(1, len(deposits) - 0) and matched == len(deposits):
            doc = matched_docs[0]
            code = (
                "COLLECTION_DOCUMENTED"
                if doc.get("type") in {"cash_collection_reports", "ticket_report"}
                else "BUSINESS_RECORDS_RECONCILE"
            )
            return _finding(
                "CLOSE",
                code,
                alert["alert_id"],
                [alert["alert_id"], doc["doc_id"], *[tx["transaction_id"] for tx in txs]],
                (
                    f"Alert {alert['alert_id']} counted {len(deposits)} cash amounts totalling {money(sum(deposits))}.",
                    f"Document {doc['doc_id']} ({doc['title']}) records those same amounts, so the deposits reconcile to the business records.",
                ),
            )
        return _finding(
            "ESCALATE",
            "ESC_STRUCTURING",
            alert["alert_id"],
            [alert["alert_id"], *[tx["transaction_id"] for tx in txs]],
            (
                f"Alert {alert['alert_id']} shows {measured.get('count', len(txs))} cash deposits just"
                f" under the reporting line, totalling {money(measured.get('total_gbp'))}.",
                "No collection report or takings record on file reconciles those deposits. Splitting cash under the threshold is escalated.",
            ),
        )

    if rule == "TM06":
        country = str(measured.get("countries") or "")
        total = float(measured.get("total_gbp") or 0)
        candidates = _docs_of(book, customer["customer_id"], _INVOICE_TYPES | {"supply_contract"})
        named = [name for name in (norm(item) for item in names) if name]
        amount_hits = []
        for doc in candidates:
            if not country or country.lower() not in doc["text"].lower():
                continue
            amounts_ok = any(
                _near(total, amount, 0.05) or any(_near(tx.get("amount_gbp") or 0, amount, 0.02) for tx in txs)
                for amount in doc["amounts"]
            )
            if amounts_ok and any(name in doc["norm"] for name in named):
                amount_hits.append(doc)
        if amount_hits:
            doc = amount_hits[0]
            return _finding(
                "CLOSE",
                "INVOICE_MATCHES",
                alert["alert_id"],
                [alert["alert_id"], doc["doc_id"], *[tx["transaction_id"] for tx in txs[:4]]],
                (
                    f"Alert {alert['alert_id']} is {money(total)} to or from {country}, which {customer.get('name')} had not declared.",
                    f"Document {doc['doc_id']} ({doc['title']}) matches both the amount and a named party, so the corridor payment is explained.",
                ),
            )
        return _finding(
            "ESCALATE",
            "ESC_HIGH_RISK_CORRIDOR",
            alert["alert_id"],
            [alert["alert_id"], *[tx["transaction_id"] for tx in txs[:4]]],
            (
                f"Alert {alert['alert_id']} is {money(total)} moving to or from {country}, a higher-risk country {customer.get('name')} did not declare.",
                "No invoice or contract on file explains that corridor, so the payments are escalated.",
            ),
        )

    if rule == "TM10":
        if _docs_of(book, customer["customer_id"], {"cancellation_confirmation"}):
            doc = _docs_of(book, customer["customer_id"], {"cancellation_confirmation"})[0]
            return _finding(
                "CLOSE",
                "REFUND_OF_EARLIER_PAYMENT",
                alert["alert_id"],
                [alert["alert_id"], doc["doc_id"], *[tx["transaction_id"] for tx in txs[:3]]],
                (
                    f"Alert {alert['alert_id']} is an early redemption for {customer.get('name')}.",
                    f"Document {doc['doc_id']} confirms the subscription is being returned inside the cancellation window.",
                ),
            )
        purpose = []
        for kind in ("redundancy_letter", "completion_statement", "customer_letter", "customer_email"):
            purpose.extend(_docs_of(book, customer["customer_id"], {kind}))
        if purpose:
            doc = purpose[0]
            why = (
                "confirms the redundancy"
                if doc.get("type") == "redundancy_letter"
                else "records why the money was needed back"
            )
            return _finding(
                "CLOSE",
                "DOCUMENTED_EVENT",
                alert["alert_id"],
                [alert["alert_id"], doc["doc_id"], *[tx["transaction_id"] for tx in txs[:3]]],
                (
                    f"Alert {alert['alert_id']} sold fund units soon after they were bought.",
                    f"Document {doc['doc_id']} ({doc['title']}) {why} for {customer.get('name')}.",
                ),
            )
        return _finding(
            "ESCALATE",
            "ESC_EARLY_REDEMPTION",
            alert["alert_id"],
            [alert["alert_id"], *[tx["transaction_id"] for tx in txs[:4]]],
            (
                f"Alert {alert['alert_id']} bought fund units and sold them back inside 90 days.",
                f"Nothing on file gives {customer.get('name')} a reason for round-tripping the investment, so it is escalated.",
            ),
        )

    if rule == "TM05":
        amount = float(measured.get("amount_gbp") or (txs[0]["amount_gbp"] if txs else 0))
        hits = _match_amount(docs, amount, names, 0.02)
        if hits:
            doc = hits[0]
            code = "BUSINESS_RECORDS_RECONCILE" if doc.get("type") in _BOOK_TYPES else "DOCUMENTED_EVENT"
            return _finding(
                "CLOSE",
                code,
                alert["alert_id"],
                [alert["alert_id"], doc["doc_id"], *[tx["transaction_id"] for tx in txs[:2]]],
                (
                    f"Alert {alert['alert_id']} is a cash amount of {money(amount)} for {customer.get('name')}.",
                    f"Document {doc['doc_id']} ({doc['title']}) records the same amount, so the cash is explained.",
                ),
            )
        return _finding(
            "RFI",
            "RFI_SOURCE_OF_FUNDS",
            alert["alert_id"],
            [alert["alert_id"], *[tx["transaction_id"] for tx in txs[:2]]],
            (
                f"Alert {alert['alert_id']} is cash of {money(amount)} and nothing on file explains it.",
                f"Ask {customer.get('name')} for proof of where the {money(amount)} cash came from, such as a sale receipt or takings record.",
            ),
        )

    if rule == "TM07":
        checks = _docs_of(book, customer["customer_id"], {"reverification_record"})
        if checks:
            doc = checks[0]
            return _finding(
                "CLOSE",
                "RETURNING_CUSTOMER",
                alert["alert_id"],
                [alert["alert_id"], doc["doc_id"], *[tx["transaction_id"] for tx in txs[:3]]],
                (
                    f"Alert {alert['alert_id']} is {money(measured.get('moved_gbp'))} moving after {measured.get('dormant_days')} dormant days.",
                    f"Document {doc['doc_id']} re-verified {customer.get('name')} when the account was used again.",
                ),
            )

    # Own-account only when those transfers are most of the alert. A small top-up
    # must not hide a pass-through, and the five-times test uses the sum.
    own_txs = [
        tx for tx in txs if same(tx.get("counterparty_name"), customer.get("name")) and tx.get("channel") != "card"
    ]
    if own_txs and rule in {"TM01", "TM02", "TM07", "TM08"}:
        others = [
            tx
            for tx in txs
            if tx.get("channel") != "card" and not same(tx.get("counterparty_name"), customer.get("name"))
        ]
        other_sum = sum(float(tx.get("amount_gbp") or 0) for tx in others)
        movement = sum(float(tx.get("amount_gbp") or 0) for tx in txs if tx.get("channel") != "card") or other_sum
        # A third-party payment that is a real part of the alert is not an own-account story.
        # A dormant-account alert still uses the own-account rule when the customer is named:
        # waking an account and moving the customer's own money is not, by itself, unexplained.
        if rule == "TM07" or movement <= 0 or other_sum <= 0.2 * movement:
            found = _own_transfers(customer, own_txs, docs, measured)
            if found:
                return Finding(found.verdict, found.code, (alert["alert_id"],), found.evidence_ids, found.sentences)

    if rule == "TM08":
        groups = _docs_of(book, customer["customer_id"], {"group_structure"})
        for doc in groups:
            for name in names:
                if norm(name) and norm(name) in doc["norm"] and not same(name, customer.get("name")):
                    return _finding(
                        "CLOSE",
                        "GROUP_COMPANY",
                        alert["alert_id"],
                        [alert["alert_id"], doc["doc_id"], *[tx["transaction_id"] for tx in txs[:2]]],
                        (
                            f"Alert {alert['alert_id']} paid or received money from {name}, which is not {customer.get('name')}.",
                            f"Group structure {doc['doc_id']} shows {name} in the same group.",
                        ),
                    )
        gifts = _docs_of(book, customer["customer_id"], {"gift_letter"})
        for doc in gifts:
            for name in names:
                if norm(name) and norm(name) in doc["norm"]:
                    return _finding(
                        "CLOSE",
                        "THIRD_PARTY_DOCUMENTED",
                        alert["alert_id"],
                        [alert["alert_id"], doc["doc_id"], *[tx["transaction_id"] for tx in txs[:2]]],
                        (
                            f"Alert {alert['alert_id']} involves {name}, a third party.",
                            f"Gift letter {doc['doc_id']} documents that relationship and the funds for {customer.get('name')}.",
                        ),
                    )

    # Several payments can be explained together: invoices, a payment file,
    # a group chart, or a review that names the same party and is not for a smaller amount.
    flow = _explain_flow(book, alert, customer, txs) if rule in {"TM01", "TM02", "TM04", "TM08"} else None
    if flow is not None and flow.verdict == "CLOSE":
        return flow

    # Invoice or event covering the largest alert transaction.
    focus = max(txs, key=lambda tx: tx.get("amount_gbp") or 0) if txs else None
    if focus:
        amount = float(focus.get("amount_gbp") or 0)
        hits = _match_amount(docs, amount, [focus.get("counterparty_name") or "", customer.get("name") or ""])
        if hits:
            doc = hits[0]
            if doc.get("type") in _INVOICE_TYPES:
                code = "INVOICE_MATCHES"
            elif doc.get("type") in _BOOK_TYPES:
                code = "BUSINESS_RECORDS_RECONCILE"
            elif doc.get("type") in _RELATION_TYPES:
                code = "THIRD_PARTY_DOCUMENTED"
            elif doc.get("type") == "credit_note":
                code = "REFUND_OF_EARLIER_PAYMENT"
            else:
                code = "DOCUMENTED_EVENT"
            party = focus.get("counterparty_name") or customer.get("name") or ""
            related = []
            if doc.get("type") in {"factoring_agreement", "remittance_advice"}:
                for item in docs:
                    if item["doc_id"] == doc["doc_id"]:
                        continue
                    if item.get("type") in {"factoring_agreement", "remittance_advice"} and norm(party) in item["norm"]:
                        related.append(item)
            if related:
                other = related[0]
                second = (
                    f"Document {doc['doc_id']} ({doc['title']}) matches {money(amount)}, and {other['doc_id']}"
                    f" ({other['title']}) records the relationship with {party}."
                )
            else:
                second = f"Document {doc['doc_id']} ({doc['title']}) matches that amount and is the ground for closing it."
            return _finding(
                "CLOSE",
                code,
                alert["alert_id"],
                [alert["alert_id"], doc["doc_id"], *[item["doc_id"] for item in related[:2]], focus["transaction_id"]],
                (
                    f"Alert {alert['alert_id']} includes {money(amount)} with {party}.",
                    second,
                ),
            )
        if rule == "TM01":
            source = focus.get("counterparty_name") or focus.get("reference") or focus.get("channel") or "that credit"
            return _finding(
                "RFI",
                "RFI_SOURCE_OF_FUNDS",
                alert["alert_id"],
                [alert["alert_id"], focus["transaction_id"]],
                (
                    f"Alert {alert['alert_id']} says {customer.get('name')} received"
                    f" {money(measured.get('received_gbp'))}, {measured.get('multiple')} times the declared baseline of {money(measured.get('baseline_gbp'))}.",
                    f"Ask {customer.get('name')} where the {money(amount)} from {source} came from, and for a document that names the payer and the amount.",
                ),
            )
        if rule == "TM02":
            if flow is not None:
                return flow
            dissolved = _dissolved_funder(book, customer, txs)
            if dissolved:
                register, party = dissolved
                return _finding(
                    "ESCALATE",
                    "ESC_MULE_ACTIVITY",
                    alert["alert_id"],
                    [alert["alert_id"], register["doc_id"], *[tx["transaction_id"] for tx in txs[:6]]],
                    (
                        f"Alert {alert['alert_id']} received {money(measured.get('received_gbp'))} and paid out"
                        f" {money(measured.get('paid_out_gbp'))} within 48 hours, {measured.get('share')} of what arrived.",
                        f"Register {register['doc_id']} shows {party} was dissolved, so this is not"
                        f" {customer.get('name')}'s own business. The money was passed on and is escalated.",
                    ),
                )
            return _finding(
                "ESCALATE",
                "ESC_PASS_THROUGH",
                alert["alert_id"],
                [alert["alert_id"], *[tx["transaction_id"] for tx in txs[:4]]],
                (
                    f"Alert {alert['alert_id']} received {money(measured.get('received_gbp'))} and paid out"
                    f" {money(measured.get('paid_out_gbp'))} within 48 hours, {measured.get('share')} of what arrived.",
                    f"Nothing on file gives {customer.get('name')} a purpose for passing the money through, so it is escalated.",
                ),
            )
        if rule == "TM04":
            bookings = _docs_of(book, customer["customer_id"], {"booking_confirmation", "venue_email"})
            payers = []
            for tx in txs:
                party = norm(tx.get("counterparty_name"))
                if party and party not in payers:
                    payers.append(party)
            for doc in bookings:
                named = [party for party in payers if party in doc["norm"]]
                if payers and len(named) >= max(2, (len(payers) + 1) // 2):
                    shown = ", ".join(named[:4])
                    return _finding(
                        "CLOSE",
                        "COLLECTION_DOCUMENTED",
                        alert["alert_id"],
                        [alert["alert_id"], doc["doc_id"], *[tx["transaction_id"] for tx in txs[:6]]],
                        (
                            f"Alert {alert['alert_id']} is payments from {len(payers)} named people, totalling {money(measured.get('total_gbp'))}.",
                            f"Document {doc['doc_id']} ({doc['title']}) names {shown}, which covers the payers on the alert.",
                        ),
                    )
            if flow is not None:
                return flow
            return _finding(
                "RFI",
                "RFI_PURPOSE_DOCUMENTS",
                alert["alert_id"],
                [alert["alert_id"], *[tx["transaction_id"] for tx in txs[:4]]],
                (
                    f"Alert {alert['alert_id']} is {measured.get('distinct_counterparties', len(txs))} counterparties and {money(measured.get('total_gbp'))}.",
                    f"Ask {customer.get('name')} for the document that shows what those payments were for, naming the payees and the amounts.",
                ),
            )
        if rule == "TM08":
            return _finding(
                "RFI",
                "RFI_COUNTERPARTY_DETAILS",
                alert["alert_id"],
                [alert["alert_id"], focus["transaction_id"]],
                (
                    f"Alert {alert['alert_id']} moves {money(amount)} with"
                    f" {focus.get('counterparty_name') or 'an unnamed party'}, who is not {customer.get('name')}.",
                    f"Ask {customer.get('name')} who {focus.get('counterparty_name') or 'that party'} is and"
                    f" for the document that shows the relationship and the {money(amount)}.",
                ),
            )

    return _finding(
        "ESCALATE",
        "ESC_UNEXPLAINED_FUNDS",
        alert["alert_id"],
        [alert["alert_id"], *[tx["transaction_id"] for tx in txs[:3]]],
        (
            f"Alert {alert['alert_id']} ({alert.get('rule_name')}) is not explained by the documents on file for {customer.get('name')}.",
            "The funds are escalated because there is no credible account of them.",
        ),
    )


def _pick(findings: list[Finding], rank: tuple[str, ...]) -> Finding:
    def key(finding: Finding) -> tuple[int, str]:
        try:
            return (rank.index(finding.code), finding.code)
        except ValueError:
            return (len(rank), finding.code)

    return sorted(findings, key=key)[0]


def _sentences(finding: Finding, extra: str = "") -> str:
    parts = [sentence if sentence.endswith(".") else sentence + "." for sentence in finding.sentences if sentence]
    if extra and len(parts) < 4:
        parts.append(extra if extra.endswith(".") else extra + ".")
    if len(parts) < 2:
        parts.append("The records cited with this decision are the ones listed as evidence.")
    return " ".join(parts[:4])


def _fx_invoice_block(book: Book, case: dict, customer: dict, findings: list[Finding]) -> Finding | None:
    if book.folder.name != "payments_fx":
        return None
    book.docs.get(customer["customer_id"], [])
    held = case.get("held_payment_id")
    watched = []
    for alert_id in case.get("alert_ids") or []:
        alert = book.alerts.get(alert_id)
        if not alert:
            continue
        for tx in _txs(book, alert):
            if (
                tx.get("direction") == "out"
                and (tx.get("amount_gbp") or 0) >= 10000
                and not same(tx.get("counterparty_name"), customer.get("name"))
            ):
                watched.append(tx)
    if held and held in book.transactions:
        tx = book.transactions[held]
        if tx not in watched and (tx.get("amount_gbp") or 0) >= 10000:
            watched.append(tx)
    if not watched:
        return None
    for tx in watched:
        amount = float(tx.get("amount_gbp") or 0)
        hits = _match_amount(
            _docs_of(book, customer["customer_id"], _INVOICE_TYPES), amount, [tx.get("counterparty_name") or ""], 0.02
        )
        if hits:
            continue
        near = _match_amount(
            _docs_of(book, customer["customer_id"], _INVOICE_TYPES), amount, [tx.get("counterparty_name") or ""], 0.5
        )
        if near and not hits:
            doc = near[0]
            return _finding(
                "ESCALATE",
                "ESC_INVOICE_MISMATCH",
                case["alert_ids"][0],
                [doc["doc_id"], tx["transaction_id"]],
                (
                    f"The held or outbound payment of {money(amount)} to {tx.get('counterparty_name')} is at or above £10,000.",
                    f"Document {doc['doc_id']} names that payee but its amount does not match {money(amount)}, so the invoice does not support the payment.",
                ),
            )
        return _finding(
            "RFI",
            "RFI_PURPOSE_DOCUMENTS",
            case["alert_ids"][0],
            [tx["transaction_id"]],
            (
                f"The payment of {money(amount)} to {tx.get('counterparty_name')} is at or above £10,000 and is not a transfer to {customer.get('name')}.",
                f"Ask {customer.get('name')} for the invoice or contract for {money(amount)} to"
                f" {tx.get('counterparty_name')}, including the payee and the amount, before it can be released.",
            ),
        )
    return None


def decide_official(book: Book, case: dict) -> Decision:
    customer = book.customers.get(
        case["customer_id"],
        {"customer_id": case.get("customer_id"), "name": case.get("customer_id"), "kind": "individual", "declared": {}},
    )
    findings = []
    for alert_id in case.get("alert_ids") or []:
        alert = book.alerts.get(alert_id)
        if alert is None:
            continue
        findings.append(_explain(book, alert, customer))
    fx = _fx_invoice_block(book, case, customer, findings)
    # A missing invoice blocks a close. A mismatch escalates.
    if (
        fx
        and not any(item.verdict == "ESCALATE" for item in findings)
        and (fx.verdict == "ESCALATE" or any(item.verdict == "CLOSE" for item in findings))
    ):
        findings.append(fx)

    if not findings:
        findings.append(
            _finding(
                "ESCALATE",
                "ESC_UNEXPLAINED_FUNDS",
                "",
                [case["case_id"]],
                (
                    f"Case {case['case_id']} has no alert that could be read.",
                    "It is escalated because a missing alert is not a ground for closure.",
                ),
            )
        )

    # Priority vote: an escalation on any alert beats a request, which beats a close.
    # A case closes only when every alert has its own strong close. One weak alert
    # drops the case to the RFI that alert already carries, or to a purpose request.
    escalations = [item for item in findings if item.verdict == "ESCALATE"]
    requests = [item for item in findings if item.verdict == "RFI"]
    closes = [item for item in findings if item.verdict == "CLOSE"]
    alert_ids = [alert_id for alert_id in (case.get("alert_ids") or []) if alert_id]
    closed_ids = {alert_id for item in closes for alert_id in item.alert_ids if alert_id}
    if escalations:
        winner = _pick(escalations, _ESC_RANK)
        verdict = "ESCALATE"
    elif alert_ids and closed_ids >= set(alert_ids) and not requests:
        winner = closes[0]
        verdict = "CLOSE"
    elif requests:
        winner = _pick(requests, _RFI_RANK)
        verdict = "RFI"
    else:
        winner = _finding(
            "RFI",
            "RFI_PURPOSE_DOCUMENTS",
            alert_ids[0] if alert_ids else "",
            [case["case_id"]],
            (
                f"Case {case['case_id']} for {customer.get('name')} is not strongly explained on every alert.",
                "Ask the customer for the document that shows what the unexplained payments were for. The case is not closed.",
            ),
        )
        verdict = "RFI"

    collected: list[str] = []
    for item in findings if verdict != "CLOSE" else [winner]:
        collected.extend(item.evidence_ids)
    if verdict == "CLOSE":
        for item in closes:
            collected.extend(item.evidence_ids)
    evidence = tuple(sorted({item for item in collected if item and item in book.ids}))
    extra = ""
    if verdict == "CLOSE" and len(closes) > 1 and closes[1].sentences:
        candidate = closes[1].sentences[0]
        if candidate not in winner.sentences:
            extra = candidate
    return Decision(
        case_id=case["case_id"],
        alert_ids=tuple(case.get("alert_ids") or []),
        verdict=verdict,
        reason_code=winner.code,
        reason=_sentences(winner, extra),
        evidence=evidence,
        findings=tuple(findings),
    )


def score_folder(folder: Path) -> list[Decision]:
    book = Book(folder)
    return [decide_official(book, case) for case in book.cases]
