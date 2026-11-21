"""Read thresholds out of POLICY.md. The file wins over any generic figure."""

from __future__ import annotations

import re

from .model import DocRequirement, Policy

_CHUNKS = re.compile(r"\n+|(?<=\.)\s+")
_POUNDS = re.compile(r"£\s*([0-9][0-9,]*(?:\.[0-9]+)?)")

# Longer phrases first so "source of funds" is not missed.
_DOCUMENTS = (
    (
        "subscription agreement",
        "SUBSCRIPTION_AGREEMENT_ON_FILE",
        "SUBSCRIPTION_AGREEMENT_REQUIRED",
        "SUBSCRIPTION_AGREEMENT_MISMATCH",
    ),
    (
        "source of funds",
        "SOURCE_OF_FUNDS_ON_FILE",
        "SOURCE_OF_FUNDS_REQUIRED",
        "SOURCE_OF_FUNDS_MISMATCH",
    ),
    (
        "invoice",
        "INVOICE_SUPPORTS_PAYMENT",
        "INVOICE_REQUIRED",
        "INVOICE_MISMATCH",
    ),
)


def _chunks(text: str) -> list[str]:
    return [chunk.strip() for chunk in _CHUNKS.split(text or "") if chunk.strip()]


def _pounds(chunk: str) -> float | None:
    match = _POUNDS.search(chunk)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _direction(chunk: str, keyword: str) -> str | None:
    low = chunk.lower()
    if any(word in low for word in ("inbound", "inward", "load", "deposit")):
        return "in"
    if "outbound" in low or (keyword == "invoice" and "payment" in low):
        return "out"
    return None


def parse_requirements(text: str) -> tuple[DocRequirement, ...]:
    found: list[DocRequirement] = []
    seen: set[str] = set()
    for chunk in _chunks(text):
        amount = _pounds(chunk)
        if amount is None:
            continue
        low = chunk.lower()
        for keyword, close_code, rfi_code, mismatch_code in _DOCUMENTS:
            if keyword not in low or keyword in seen:
                continue
            # The sentence has to be a requirement, not a passing mention.
            if not re.search(r"requir|must|needed|or more|above|at least", low):
                continue
            found.append(
                DocRequirement(
                    keyword=keyword,
                    threshold_gbp=amount,
                    direction=_direction(chunk, keyword),
                    close_code=close_code,
                    rfi_code=rfi_code,
                    mismatch_code=mismatch_code,
                )
            )
            seen.add(keyword)
            break
    return tuple(found)


def parse_own_account_multiple(text: str) -> float | None:
    low = text.lower()
    if "own account" not in low and "own-account" not in low:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*x\b", low)
    if match:
        return float(match.group(1))
    if re.search(r"\bfive times\b", low):
        return 5.0
    return None


def parse_cash_threshold(text: str) -> float | None:
    for chunk in _chunks(text):
        low = chunk.lower()
        if "cash" not in low or not re.search(r"escalat", low):
            continue
        amount = _pounds(chunk)
        if amount is not None:
            return amount
    return None


def parse_policy(text: str) -> Policy:
    low = text.lower()
    return Policy(
        text=text or "",
        own_account_multiple=parse_own_account_multiple(text or ""),
        requirements=parse_requirements(text or ""),
        cash_escalate_gbp=parse_cash_threshold(text or ""),
        allows_expected_activity="closed as expected activity" in low,
        refuted_screening_may_close=bool(
            re.search(r"contradict[\s\S]{0,160}closed", low) or re.search(r"not a match[\s\S]{0,120}closed", low)
        ),
        weak_screening_asks_identity=bool(
            re.search(r"name[- ]only[\s\S]{0,160}(ask|confirm)", low)
            or re.search(r"(ask|confirm)[\s\S]{0,160}identit", low)
        ),
        # Context signals do not decide unless the SOP explicitly says to escalate them.
        context_is_not_decisive=not bool(
            re.search(r"escalat[\s\S]{0,40}(round amount|shared device|crypto)", low)
            or re.search(r"(round amount|shared device|crypto)[\s\S]{0,40}escalat", low)
        ),
    )
