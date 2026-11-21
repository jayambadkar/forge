"""Small predicates shared by labelling functions and the feature builder."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .model import Customer, Transaction

_SUFFIX = re.compile(
    r"\b(ltd|limited|plc|llc|inc|incorporated|company|co|the)\b",
    re.I,
)
_MONEY = re.compile(r"£\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)")
_CRYPTO = re.compile(
    r"\b(crypto|bitcoin|btc|ethereum|ether|usdt|tether|mixer|monero)\b",
    re.I,
)
_CASH = re.compile(r"\b(cash|branch deposit|notes deposited)\b", re.I)
_SCREEN = re.compile(
    r"(sanction|screening|watchlist|pep\b|internal list|name match|list match)",
    re.I,
)

# Used only when the file states a non-GBP currency. Unknown currencies
# are left unconverted so a foreign amount is never treated as pounds.
TO_GBP = {
    "GBP": 1.0,
    "GBX": 0.01,
    "USD": 0.79,
    "EUR": 0.86,
    "CHF": 0.90,
}


def norm_name(value: str | None) -> str:
    text = (value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = _SUFFIX.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_amount(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("gbp", "amount", "value", "amount_gbp"):
            if key in value:
                parsed = parse_amount(value[key])
                if parsed is not None:
                    return parsed
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace("£", "").replace(",", "")
        cleaned = re.sub(r"\b(gbp|usd|eur)\b", "", cleaned, flags=re.I).strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def to_gbp(amount: float | None, currency: str | None) -> float | None:
    if amount is None:
        return None
    code = (currency or "GBP").strip().upper()
    if code in {"", "£"}:
        code = "GBP"
    rate = TO_GBP.get(code)
    if rate is None:
        return None
    return round(amount * rate, 2)


def money(amount: float | None) -> str:
    if amount is None:
        return "an unstated amount"
    return f"£{amount:,.2f}"


def extract_pounds(text: str) -> list[float]:
    found = []
    for match in _MONEY.finditer(text or ""):
        found.append(float(match.group(1).replace(",", "")))
    return found


def norm_dob(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    iso = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", raw)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
    uk = re.match(r"(\d{2})[-/](\d{2})[-/](\d{4})", raw)
    if uk:
        return f"{uk.group(3)}-{uk.group(2)}-{uk.group(1)}"
    return raw


def norm_country(value: str | None) -> str:
    text = (value or "").strip().lower()
    aliases = {
        "uk": "gb",
        "u.k.": "gb",
        "united kingdom": "gb",
        "great britain": "gb",
        "britain": "gb",
        "england": "gb",
        "scotland": "gb",
        "wales": "gb",
    }
    return aliases.get(text, text)


def names_match(left: str, right: str) -> bool:
    a = norm_name(left)
    b = norm_name(right)
    if len(a) < 4 or len(b) < 4:
        return False
    if a == b:
        return True
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if len(a_tokens) >= 2 and a_tokens == b_tokens:
        return True
    # Tight fuzzy band for a missing hyphen or a single-character typo.
    # Token-set equality already covered reorderings. Ratio stays high
    # so "John Smith" does not match "John Smythe".
    return bool(min(len(a), len(b)) >= 8 and SequenceMatcher(None, a, b).ratio() >= 0.94)


def exact_name(left: str, right: str) -> bool:
    a = norm_name(left)
    b = norm_name(right)
    return len(a) >= 4 and a == b


def classify_match(
    person_name: str,
    person_dob: str,
    person_country: str,
    entry_name: str,
    entry_dob: str,
    entry_country: str,
) -> str:
    """Return confirmed, refuted, weak, or none.

    A contradicted date of birth is a refutation even when the country matches.
    Country corroborates only an exact (same-order) name, not a token shuffle.
    """
    if not names_match(person_name, entry_name):
        return "none"
    dob_a = norm_dob(person_dob)
    dob_b = norm_dob(entry_dob)
    if dob_a and dob_b and dob_a != dob_b:
        return "refuted"
    if dob_a and dob_b and dob_a == dob_b:
        return "confirmed"
    country_a = norm_country(person_country)
    country_b = norm_country(entry_country)
    if exact_name(person_name, entry_name) and country_a and country_a == country_b:
        return "confirmed"
    return "weak"


def looks_like_crypto(*texts: str) -> bool:
    return any(_CRYPTO.search(text or "") for text in texts)


def looks_like_cash(*texts: str) -> bool:
    return any(_CASH.search(text or "") for text in texts)


def looks_like_screening(*texts: str) -> bool:
    return any(_SCREEN.search(text or "") for text in texts)


def is_round_pounds(amount: float | None) -> bool:
    if amount is None or amount < 1000:
        return False
    whole = round(amount)
    return abs(amount - whole) < 0.001 and int(whole) % 100 == 0


def is_own_account(txn: Transaction, customer: Customer | None) -> bool:
    if txn.own_account is True:
        return True
    if customer is None:
        return False
    account = (txn.counterparty_account or "").strip()
    if account and account in customer.accounts:
        return True
    return bool(txn.counterparty_name and customer.name and exact_name(txn.counterparty_name, customer.name))


def direction_of(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text in {"in", "inbound", "credit", "cr", "deposit", "load", "incoming"}:
        return "in"
    if text in {"out", "outbound", "debit", "dr", "payment", "withdrawal", "send", "outgoing"}:
        return "out"
    return ""
