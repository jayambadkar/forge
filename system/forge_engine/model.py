"""Normalised records. Raw dicts are kept so a new field does not require a new type."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Customer:
    id: str
    name: str
    dob: str
    country: str
    expected_monthly: float | None
    accounts: tuple[str, ...]
    raw: dict


@dataclass
class Transaction:
    id: str
    customer_id: str
    timestamp: str
    amount: float
    currency: str
    amount_gbp: float | None
    direction: str
    counterparty_name: str
    counterparty_account: str
    counterparty_country: str
    own_account: bool | None
    device_id: str
    reference: str
    is_crypto: bool
    is_cash: bool
    raw: dict


@dataclass
class Alert:
    id: str
    case_id: str
    customer_id: str
    typology: str
    narrative: str
    transaction_ids: tuple[str, ...]
    amount: float | None
    currency: str
    amount_gbp: float | None
    matched_list_id: str
    matched_name: str
    raw: dict


@dataclass
class Evidence:
    id: str
    case_id: str
    customer_id: str
    kind: str
    title: str
    text: str
    amount: float | None
    path: str


@dataclass
class Review:
    id: str
    customer_id: str
    date: str
    text: str
    raw: dict


@dataclass
class ListEntry:
    id: str
    name: str
    kind: str
    dob: str
    country: str
    raw: dict


@dataclass
class Case:
    id: str
    customer_id: str
    alert_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    raw: dict


@dataclass
class DocRequirement:
    keyword: str
    threshold_gbp: float
    direction: str | None
    close_code: str
    rfi_code: str
    mismatch_code: str


@dataclass
class Policy:
    text: str
    own_account_multiple: float | None
    requirements: tuple[DocRequirement, ...]
    cash_escalate_gbp: float | None
    allows_expected_activity: bool
    refuted_screening_may_close: bool
    weak_screening_asks_identity: bool
    context_is_not_decisive: bool


@dataclass
class Institution:
    root: Path
    name: str
    policy: Policy
    customers: dict[str, Customer]
    transactions: dict[str, Transaction]
    transactions_by_customer: dict[str, tuple[Transaction, ...]]
    alerts: dict[str, Alert]
    evidence: dict[str, Evidence]
    reviews_by_customer: dict[str, tuple[Review, ...]]
    list_entries: tuple[ListEntry, ...]
    list_by_id: dict[str, ListEntry]
    list_by_name: dict[str, tuple[ListEntry, ...]]
    cases: tuple[Case, ...]
    all_ids: frozenset[str]
    shared_devices: frozenset[str]


@dataclass
class Finding:
    verdict: str
    code: str
    alert_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    sentences: tuple[str, ...]
    hard: bool = False


@dataclass
class Decision:
    case_id: str
    alert_ids: tuple[str, ...]
    verdict: str
    reason_code: str
    reason: str
    evidence: tuple[str, ...]
    findings: tuple[Finding, ...] = field(default_factory=tuple)
    context: tuple[str, ...] = field(default_factory=tuple)

    def public(self) -> dict:
        return {
            "case_id": self.case_id,
            "alert_ids": list(self.alert_ids),
            "verdict": self.verdict,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "evidence": list(self.evidence),
        }
