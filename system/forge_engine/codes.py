"""Verdicts and the reason codes that belong to each one.

One registry. Labelling functions emit these strings and nothing else.
When an official BRIEF.html can be parsed with a code list for every verdict,
that list replaces this one for the duration of the process.
"""

from __future__ import annotations

VERDICTS = ("CLOSE", "RFI", "ESCALATE")

# Order inside each tuple is display order, not decision priority.
REASON_CODES: dict[str, tuple[str, ...]] = {
    "CLOSE": (
        "COLLECTION_DOCUMENTED",
        "BUSINESS_RECORDS_RECONCILE",
        "DOCUMENTED_EVENT",
        "INVOICE_MATCHES",
        "OWN_ACCOUNT",
        "GROUP_COMPANY",
        "THIRD_PARTY_DOCUMENTED",
        "REFUND_OF_EARLIER_PAYMENT",
        "RETURNING_CUSTOMER",
        "LIST_MATCH_DIFFERENT_PARTY",
        "WITHIN_PROFILE",
        "OWN_ACCOUNT_WITHIN_LIMIT",
        "COVERED_BY_PRIOR_REVIEW",
        "LIST_MATCH_REFUTED",
        "INVOICE_SUPPORTS_PAYMENT",
        "SOURCE_OF_FUNDS_ON_FILE",
        "SUBSCRIPTION_AGREEMENT_ON_FILE",
        "EXPECTED_ACTIVITY",
    ),
    "RFI": (
        "RFI_PURPOSE_DOCUMENTS",
        "RFI_BUSINESS_RECORDS",
        "RFI_SOURCE_OF_FUNDS",
        "RFI_COUNTERPARTY_DETAILS",
        "RFI_UPDATED_PROFILE",
        "INVOICE_REQUIRED",
        "SOURCE_OF_FUNDS_REQUIRED",
        "SUBSCRIPTION_AGREEMENT_REQUIRED",
        "IDENTITY_CONFIRMATION",
    ),
    "ESCALATE": (
        "ESC_MULE_ACTIVITY",
        "ESC_STRUCTURING",
        "ESC_UNEXPLAINED_FUNDS",
        "ESC_PASS_THROUGH",
        "ESC_INVOICE_MISMATCH",
        "ESC_HIGH_RISK_CORRIDOR",
        "ESC_ACCOUNT_MISUSE",
        "ESC_THIRD_PARTY_FUNDING",
        "ESC_EARLY_REDEMPTION",
        "ESC_LISTED_PARTY",
        "INTERNAL_LIST_MATCH",
        "OWN_ACCOUNT_EXCEEDS_MULTIPLE",
        "INVOICE_MISMATCH",
        "SOURCE_OF_FUNDS_MISMATCH",
        "SUBSCRIPTION_AGREEMENT_MISMATCH",
        "CASH_ABOVE_THRESHOLD",
        "ACTIVITY_UNEXPLAINED",
    ),
}

# Aggregation preference. Earlier means "this finding speaks first"
# when several findings of the same verdict apply.
ESCALATE_PRIORITY = REASON_CODES["ESCALATE"]
RFI_PRIORITY = REASON_CODES["RFI"]
CLOSE_PRIORITY = (
    "INVOICE_SUPPORTS_PAYMENT",
    "SOURCE_OF_FUNDS_ON_FILE",
    "SUBSCRIPTION_AGREEMENT_ON_FILE",
    "LIST_MATCH_REFUTED",
    "OWN_ACCOUNT_WITHIN_LIMIT",
    "COVERED_BY_PRIOR_REVIEW",
    "EXPECTED_ACTIVITY",
)


def codes_for(verdict: str) -> tuple[str, ...]:
    return REASON_CODES[verdict]


def verdict_for(code: str) -> str | None:
    for verdict, codes in REASON_CODES.items():
        if code in codes:
            return verdict
    return None


def replace_registry(official: dict[str, tuple[str, ...]]) -> None:
    """Swap in an official list. Every verdict must be present and non-empty."""
    for verdict in VERDICTS:
        codes = official.get(verdict) or ()
        if len(codes) < 1:
            raise ValueError(f"official list has no codes for {verdict}")
    REASON_CODES.clear()
    REASON_CODES.update({v: tuple(official[v]) for v in VERDICTS})
