"""Labelling functions and the aggregation that turns them into one verdict.

A case is closed only when every alert has a close finding. One hard
escalation (a confirmed internal-list match) beats a request for documents.
Context signals are named later; they never produce a finding.
"""

from __future__ import annotations

from .codes import CLOSE_PRIORITY, ESCALATE_PRIORITY, RFI_PRIORITY
from .facts import (
    classify_match,
    extract_pounds,
    is_own_account,
    is_round_pounds,
    looks_like_cash,
    looks_like_crypto,
    looks_like_screening,
    money,
    names_match,
    norm_name,
)
from .model import Alert, Case, Customer, Decision, Evidence, Finding, Institution, Transaction

_LABELLING_FUNCTIONS = ()  # filled at the bottom so the functions can call each other via the tuple


def _customer(inst: Institution, case: Case) -> Customer | None:
    return inst.customers.get(case.customer_id)


def _alerts(inst: Institution, case: Case) -> list[Alert]:
    return [inst.alerts[alert_id] for alert_id in case.alert_ids if alert_id in inst.alerts]


def _txns_for(inst: Institution, alert: Alert) -> list[Transaction]:
    return [inst.transactions[txn_id] for txn_id in alert.transaction_ids if txn_id in inst.transactions]


def _case_evidence(inst: Institution, case: Case) -> list[Evidence]:
    picked = []
    for item in inst.evidence.values():
        if (
            item.id in case.evidence_ids
            or item.case_id == case.id
            or (item.customer_id and item.customer_id == case.customer_id)
        ):
            picked.append(item)
    picked.sort(key=lambda item: item.id)
    return picked


def _article(noun: str) -> str:
    return "an" if noun[:1].lower() in "aeiou" else "a"


def _policy_name(name: str) -> str:
    return {
        "bank": "bank",
        "emoney": "e-money",
        "investment": "investment",
        "payments_fx": "payments and FX",
    }.get(name, name.replace("_", " "))


def _who(inst: Institution, case: Case) -> str:
    customer = _customer(inst, case)
    if customer and customer.name:
        return customer.name
    return case.customer_id or "the customer"


def _alert_amount(inst: Institution, alert: Alert) -> float | None:
    txns = _txns_for(inst, alert)
    amounts = [txn.amount_gbp for txn in txns if txn.amount_gbp is not None]
    if amounts:
        return round(sum(amounts), 2)
    return alert.amount_gbp


def _best(findings: list[Finding], priority: tuple[str, ...]) -> Finding:
    def rank(finding: Finding) -> tuple[int, str]:
        try:
            position = priority.index(finding.code)
        except ValueError:
            position = len(priority)
        return (position, finding.code)

    return sorted(findings, key=rank)[0]


def _compose(sentences: list[str], context: list[str]) -> str:
    cleaned: list[str] = []
    for sentence in sentences:
        text = " ".join(sentence.split()).strip()
        if not text:
            continue
        if text[-1] not in ".!?":
            text += "."
        cleaned.append(text)
    if context and len(cleaned) < 4:
        if len(context) == 1:
            joined = context[0]
            verb = "was"
        else:
            joined = ", ".join(context[:-1]) + " and " + context[-1]
            verb = "were"
        cleaned.append(
            f"{joined[0].upper() + joined[1:]} {verb} recorded as context and {verb} not used as a ground to close or to escalate."
        )
    if len(cleaned) < 2:
        cleaned.append("The records cited on this decision are the ones listed as evidence.")
    return " ".join(cleaned[:4])


def _evidence(inst: Institution, ids: list[str]) -> tuple[str, ...]:
    return tuple(sorted({item for item in ids if item and item in inst.all_ids}))


def _unexplained(inst: Institution, case: Case, alerts: list[Alert], context: list[str]) -> Finding:
    who = _who(inst, case)
    names = ", ".join(alert.id for alert in alerts) or "none"
    amounts = []
    for alert in alerts:
        amount = _alert_amount(inst, alert)
        if amount is not None:
            amounts.append(money(amount))
    amount_text = ", ".join(amounts) if amounts else "no amount on the alert"
    sentences = (
        f"Case {case.id} for {who} leaves alert {names} unexplained ({amount_text}).",
        "Own-account limits, earlier reviews, list outcomes, and the documents this institution requires do not account for the activity.",
    )
    evidence = [case.customer_id, *[alert.id for alert in alerts]]
    for alert in alerts:
        evidence.extend(alert.transaction_ids)
    return Finding(
        verdict="ESCALATE",
        code="ACTIVITY_UNEXPLAINED",
        alert_ids=tuple(alert.id for alert in alerts),
        evidence_ids=tuple(evidence),
        sentences=sentences,
    )


def _list_candidates(inst: Institution, name: str) -> list:
    key = norm_name(name)
    if not key:
        return []
    direct = list(inst.list_by_name.get(key, ()))
    if direct:
        return direct
    # Token-equal and tight fuzzy hits are rare; scan only when the index misses.
    hits = []
    for entry in inst.list_entries:
        if names_match(name, entry.name):
            hits.append(entry)
    return hits


def lf_internal_list(inst: Institution, case: Case) -> list[Finding]:
    customer = _customer(inst, case)
    findings: list[Finding] = []
    for alert in _alerts(inst, case):
        people: list[tuple[str, str, str, str]] = []
        if customer and customer.name:
            people.append((customer.name, customer.dob, customer.country, "customer"))
        if alert.matched_name:
            people.append(
                (
                    alert.matched_name,
                    customer.dob if customer else "",
                    customer.country if customer else "",
                    "screened name",
                )
            )
        for txn in _txns_for(inst, alert):
            if txn.counterparty_name:
                people.append((txn.counterparty_name, "", txn.counterparty_country, "counterparty"))

        entries = []
        if alert.matched_list_id and alert.matched_list_id in inst.list_by_id:
            entries.append(inst.list_by_id[alert.matched_list_id])
        else:
            seen = set()
            for person_name, _, _, _ in people:
                for entry in _list_candidates(inst, person_name):
                    if entry.id not in seen:
                        seen.add(entry.id)
                        entries.append(entry)

        best_rank = "none"
        best_entry = None
        best_person = None
        rank_order = {"none": 0, "weak": 1, "refuted": 2, "confirmed": 3}
        for person_name, person_dob, person_country, role in people:
            pool = entries or _list_candidates(inst, person_name)
            for entry in pool:
                kind = classify_match(
                    person_name,
                    person_dob,
                    person_country,
                    entry.name,
                    entry.dob,
                    entry.country,
                )
                if rank_order[kind] > rank_order[best_rank]:
                    best_rank = kind
                    best_entry = entry
                    best_person = (person_name, role)

        screening = looks_like_screening(alert.typology, alert.narrative)
        if best_rank == "confirmed" and best_entry is not None and best_person is not None:
            who = _who(inst, case)
            sentences = (
                f"Case {case.id} for {who} matches internal-list entry {best_entry.id} ({best_entry.name})"
                f" on the {best_person[1]} name, with a corroborating date of birth or exact name and country.",
                f"Alert {alert.id} is escalated on that confirmed match. A name overlap without that corroboration would not have been enough.",
            )
            findings.append(
                Finding(
                    verdict="ESCALATE",
                    code="INTERNAL_LIST_MATCH",
                    alert_ids=(alert.id,),
                    evidence_ids=(alert.id, best_entry.id, case.customer_id),
                    sentences=sentences,
                    hard=True,
                )
            )
        elif (
            best_rank == "refuted"
            and screening
            and inst.policy.refuted_screening_may_close
            and best_entry
            and best_person
        ):
            who = _who(inst, case)
            sentences = (
                f"Case {case.id} for {who} was screened against internal-list entry {best_entry.id} ({best_entry.name}), and the dates of birth contradict.",
                f"The institution treats a contradicted date of birth as not a match, so screening alert {alert.id} is closed as a false positive.",
            )
            findings.append(
                Finding(
                    verdict="CLOSE",
                    code="LIST_MATCH_REFUTED",
                    alert_ids=(alert.id,),
                    evidence_ids=(alert.id, best_entry.id, case.customer_id),
                    sentences=sentences,
                )
            )
        elif (
            best_rank == "weak"
            and screening
            and inst.policy.weak_screening_asks_identity
            and best_entry
            and best_person
        ):
            who = _who(inst, case)
            sentences = (
                f"Case {case.id} for {who} shares a name with internal-list entry {best_entry.id}"
                f" ({best_entry.name}) but has no corroborating date of birth or country.",
                f"Ask the customer to confirm whether they are {best_entry.name}, and to provide their date"
                f" of birth and country of residence, before alert {alert.id} can be closed.",
            )
            findings.append(
                Finding(
                    verdict="RFI",
                    code="IDENTITY_CONFIRMATION",
                    alert_ids=(alert.id,),
                    evidence_ids=(alert.id, best_entry.id, case.customer_id),
                    sentences=sentences,
                )
            )
    return findings


def lf_own_account(inst: Institution, case: Case) -> list[Finding]:
    multiple = inst.policy.own_account_multiple
    if multiple is None:
        return []
    customer = _customer(inst, case)
    baseline = customer.expected_monthly if customer else None
    if baseline is None or baseline <= 0:
        return []
    limit = baseline * multiple
    findings = []
    who = _who(inst, case)
    for alert in _alerts(inst, case):
        txns = _txns_for(inst, alert)
        own_txns = [txn for txn in txns if is_own_account(txn, customer)]
        typology_says_own = "own account" in alert.typology.lower() or "own-account" in alert.typology.lower()
        if not own_txns and not typology_says_own:
            continue
        amounts = [txn.amount_gbp for txn in own_txns if txn.amount_gbp is not None]
        if not amounts and typology_says_own and alert.amount_gbp is not None:
            amounts = [alert.amount_gbp]
        if not amounts:
            continue
        peak = max(amounts)
        evidence = [alert.id, case.customer_id, *[txn.id for txn in own_txns]]
        if peak <= limit + 0.001:
            account_text = ""
            if own_txns and own_txns[0].counterparty_account:
                account_text = f" to account {own_txns[0].counterparty_account}"
            findings.append(
                Finding(
                    verdict="CLOSE",
                    code="OWN_ACCOUNT_WITHIN_LIMIT",
                    alert_ids=(alert.id,),
                    evidence_ids=tuple(evidence),
                    sentences=(
                        f"Case {case.id} for {who} is an own-account movement of {money(peak)}{account_text}.",
                        f"The expected monthly amount is {money(baseline)}, so the {multiple:g}x own-account limit"
                        f" in the {_policy_name(inst.name)} policy is {money(limit)}, and {money(peak)} sits inside it. Alert {alert.id} is explained.",
                    ),
                )
            )
        else:
            findings.append(
                Finding(
                    verdict="ESCALATE",
                    code="OWN_ACCOUNT_EXCEEDS_MULTIPLE",
                    alert_ids=(alert.id,),
                    evidence_ids=tuple(evidence),
                    sentences=(
                        f"Case {case.id} for {who} moves {money(peak)} between accounts the customer holds.",
                        f"That is above the {multiple:g}x own-account limit of {money(limit)} against an expected"
                        f" monthly amount of {money(baseline)}, so alert {alert.id} is not explained"
                        f" by the own-account rule in the {_policy_name(inst.name)} policy.",
                    ),
                )
            )
    return findings


def _doc_relation(item: Evidence, keyword: str, amount: float) -> str:
    blob = f"{item.kind} {item.title} {item.text}".lower()
    if keyword not in blob:
        return "irrelevant"
    amounts = extract_pounds(f"{item.title}\n{item.text}")
    if item.amount is not None:
        amounts.append(item.amount)
    if not amounts:
        return "match"
    if any(abs(candidate - amount) <= max(1.0, amount * 0.01) for candidate in amounts):
        return "match"
    return "mismatch"


def lf_documents(inst: Institution, case: Case) -> list[Finding]:
    if not inst.policy.requirements:
        return []
    evidence = _case_evidence(inst, case)
    who = _who(inst, case)
    findings = []
    for alert in _alerts(inst, case):
        txns = _txns_for(inst, alert)
        for requirement in inst.policy.requirements:
            relevant: list[tuple[str, float, str]] = []
            for txn in txns:
                amount = txn.amount_gbp
                if amount is None or amount + 0.001 < requirement.threshold_gbp:
                    continue
                if requirement.direction and txn.direction and txn.direction != requirement.direction:
                    continue
                label = txn.counterparty_name or "the counterparty"
                relevant.append((txn.id, amount, label))
            if not relevant and alert.amount_gbp is not None and alert.amount_gbp + 0.001 >= requirement.threshold_gbp:
                relevant.append(("", alert.amount_gbp, "the counterparty"))
            if not relevant:
                continue
            # One finding per alert per requirement, using the largest relevant payment.
            txn_id, amount, label = max(relevant, key=lambda item: item[1])
            relations = [_doc_relation(item, requirement.keyword, amount) for item in evidence]
            supporting = [item for item, relation in zip(evidence, relations, strict=False) if relation == "match"]
            conflicting = [item for item, relation in zip(evidence, relations, strict=False) if relation == "mismatch"]
            doc_name = requirement.keyword
            policy_name = _policy_name(inst.name)
            evidence_ids = [alert.id, case.customer_id]
            if txn_id:
                evidence_ids.append(txn_id)
            if supporting and not conflicting:
                doc = supporting[0]
                evidence_ids.append(doc.id)
                findings.append(
                    Finding(
                        verdict="CLOSE",
                        code=requirement.close_code,
                        alert_ids=(alert.id,),
                        evidence_ids=tuple(evidence_ids),
                        sentences=(
                            f"Case {case.id} for {who} includes {money(amount)}"
                            f" {('outbound to' if requirement.direction == 'out' else 'inbound from') if requirement.direction else 'with'} {label}.",
                            f"Document {doc.id} ({doc.title or doc_name}) matches that amount, which meets the"
                            f" {policy_name} requirement for {_article(doc_name)} {doc_name}"
                            f" at or above {money(requirement.threshold_gbp)}."
                            f" Alert {alert.id} is explained by that document.",
                        ),
                    )
                )
            elif conflicting and not supporting:
                doc = conflicting[0]
                evidence_ids.append(doc.id)
                findings.append(
                    Finding(
                        verdict="ESCALATE",
                        code=requirement.mismatch_code,
                        alert_ids=(alert.id,),
                        evidence_ids=tuple(evidence_ids),
                        sentences=(
                            f"Case {case.id} for {who} moves {money(amount)} with {label}, at or above the"
                            f" {money(requirement.threshold_gbp)} {doc_name} line in the {policy_name} policy.",
                            f"Document {doc.id} is a {doc_name} but its amount does not match {money(amount)}, so alert {alert.id} cannot be closed on it.",
                        ),
                    )
                )
            else:
                direction_word = (
                    "outbound payment"
                    if requirement.direction == "out"
                    else "inbound amount"
                    if requirement.direction == "in"
                    else "payment"
                )
                findings.append(
                    Finding(
                        verdict="RFI",
                        code=requirement.rfi_code,
                        alert_ids=(alert.id,),
                        evidence_ids=tuple(evidence_ids),
                        sentences=(
                            f"Case {case.id} for {who} has {_article(direction_word)} {direction_word} of {money(amount)} with {label}.",
                            f"The {policy_name} policy requires {_article(doc_name)} {doc_name} at or above"
                            f" {money(requirement.threshold_gbp)}, and the evidence pack has none that matches."
                            f" Ask the customer to provide the {doc_name} for {money(amount)} with {label},"
                            f" including the counterparty name and the amount, before alert {alert.id} can be closed.",
                        ),
                    )
                )
    return findings


def _review_covers(review_text: str, alert: Alert, txns: list[Transaction], amount: float | None) -> bool:
    text = norm_name(review_text)
    review_text.lower()
    typology = norm_name(alert.typology)
    mentioned = False
    if typology and typology in text:
        mentioned = True
    else:
        for token in typology.split():
            if len(token) >= 5 and token in text:
                mentioned = True
                break
    if not mentioned:
        for txn in txns:
            party = norm_name(txn.counterparty_name)
            if party and party in text:
                mentioned = True
                break
    if not mentioned:
        return False
    stated = extract_pounds(review_text)
    if amount is None:
        return True
    if not stated:
        return False
    return amount <= max(stated) * 1.25 + 0.01


def lf_prior_review(inst: Institution, case: Case) -> list[Finding]:
    reviews = inst.reviews_by_customer.get(case.customer_id, ())
    if not reviews:
        return []
    who = _who(inst, case)
    findings = []
    for alert in _alerts(inst, case):
        txns = _txns_for(inst, alert)
        amount = _alert_amount(inst, alert)
        covering = [review for review in reviews if _review_covers(review.text, alert, txns, amount)]
        if not covering:
            continue
        review = covering[0]
        findings.append(
            Finding(
                verdict="CLOSE",
                code="COVERED_BY_PRIOR_REVIEW",
                alert_ids=(alert.id,),
                evidence_ids=(alert.id, review.id, case.customer_id, *[txn.id for txn in txns]),
                sentences=(
                    f"Case {case.id} for {who} matches earlier review {review.id}, which describes this typology and this amount ({money(amount)}).",
                    f"The review does not get to stand in for activity it does not describe. Alert {alert.id}"
                    f" is the activity that review covers, so it is closed on that record.",
                ),
            )
        )
    return findings


def lf_expected_activity(inst: Institution, case: Case) -> list[Finding]:
    if not inst.policy.allows_expected_activity:
        return []
    customer = _customer(inst, case)
    if customer is None or customer.expected_monthly is None or customer.expected_monthly <= 0:
        return []
    who = _who(inst, case)
    findings = []
    for alert in _alerts(inst, case):
        if looks_like_screening(alert.typology, alert.narrative):
            continue
        txns = _txns_for(inst, alert)
        blob = " ".join([alert.typology, alert.narrative, *[txn.reference for txn in txns]])
        if looks_like_crypto(blob) or any(txn.is_crypto for txn in txns):
            continue
        if looks_like_cash(blob) or any(txn.is_cash for txn in txns):
            continue
        if any(is_own_account(txn, customer) for txn in txns):
            continue
        amount = _alert_amount(inst, alert)
        if amount is None or amount > customer.expected_monthly + 0.001:
            continue
        foreign = False
        for txn in txns:
            if txn.counterparty_country and customer.country and txn.counterparty_country != customer.country:
                foreign = True
        if foreign:
            continue
        findings.append(
            Finding(
                verdict="CLOSE",
                code="EXPECTED_ACTIVITY",
                alert_ids=(alert.id,),
                evidence_ids=(alert.id, case.customer_id, *[txn.id for txn in txns]),
                sentences=(
                    f"Case {case.id} for {who} is {money(amount)} of {alert.typology or 'activity'}, inside the"
                    f" expected monthly amount of {money(customer.expected_monthly)}.",
                    f"The {_policy_name(inst.name)} policy allows that in-profile activity to be closed when it"
                    f" is not cash, crypto, or a screening hit. Alert {alert.id} meets that test.",
                ),
            )
        )
    return findings


def lf_cash(inst: Institution, case: Case) -> list[Finding]:
    threshold = inst.policy.cash_escalate_gbp
    if threshold is None:
        return []
    who = _who(inst, case)
    findings = []
    for alert in _alerts(inst, case):
        txns = _txns_for(inst, alert)
        cash_amounts = [
            txn.amount_gbp
            for txn in txns
            if txn.is_cash and txn.amount_gbp is not None and txn.amount_gbp + 0.001 >= threshold
        ]
        typology_cash = looks_like_cash(alert.typology, alert.narrative)
        if (
            not cash_amounts
            and typology_cash
            and alert.amount_gbp is not None
            and alert.amount_gbp + 0.001 >= threshold
        ):
            cash_amounts = [alert.amount_gbp]
        if not cash_amounts:
            continue
        peak = max(cash_amounts)
        findings.append(
            Finding(
                verdict="ESCALATE",
                code="CASH_ABOVE_THRESHOLD",
                alert_ids=(alert.id,),
                evidence_ids=(alert.id, case.customer_id, *[txn.id for txn in txns]),
                sentences=(
                    f"Case {case.id} for {who} includes a cash amount of {money(peak)}.",
                    f"The {_policy_name(inst.name)} policy escalates cash at or above {money(threshold)}, so alert {alert.id} is escalated on that rule.",
                ),
            )
        )
    return findings


def context_notes(inst: Institution, case: Case) -> list[str]:
    if not inst.policy.context_is_not_decisive:
        return []
    notes = []
    round_hit = False
    shared_hit = False
    crypto_hit = False
    for alert in _alerts(inst, case):
        amount = _alert_amount(inst, alert)
        if is_round_pounds(amount):
            round_hit = True
        for txn in _txns_for(inst, alert):
            if is_round_pounds(txn.amount_gbp):
                round_hit = True
            if txn.device_id and txn.device_id in inst.shared_devices:
                shared_hit = True
            if txn.is_crypto or looks_like_crypto(txn.reference, alert.typology, alert.narrative):
                crypto_hit = True
        if looks_like_crypto(alert.typology, alert.narrative):
            crypto_hit = True
    if round_hit:
        notes.append("a round-pound amount")
    if shared_hit:
        notes.append("a device shared with another customer")
    if crypto_hit:
        notes.append("a crypto reference")
    return notes


def _attach(findings: list[Finding], alert_id: str) -> list[Finding]:
    attached = []
    for finding in findings:
        if not finding.alert_ids or alert_id in finding.alert_ids:
            attached.append(finding)
    return attached


def decide_case(inst: Institution, case: Case) -> Decision:
    alerts = _alerts(inst, case)
    context = context_notes(inst, case)
    findings: list[Finding] = []
    for function in (
        lf_internal_list,
        lf_own_account,
        lf_documents,
        lf_prior_review,
        lf_expected_activity,
        lf_cash,
    ):
        findings.extend(function(inst, case))

    if not alerts:
        winner = _unexplained(inst, case, alerts, context)
        reason = _compose(list(winner.sentences), context)
        return Decision(
            case_id=case.id,
            alert_ids=case.alert_ids,
            verdict="ESCALATE",
            reason_code="ACTIVITY_UNEXPLAINED",
            reason=reason,
            evidence=_evidence(inst, list(winner.evidence_ids)),
            findings=(winner,),
            context=tuple(context),
        )

    dispositions: list[tuple[str, Finding | None]] = []
    for alert in alerts:
        candidates = _attach(findings, alert.id)
        hard = [item for item in candidates if item.hard and item.verdict == "ESCALATE"]
        escalations = [item for item in candidates if item.verdict == "ESCALATE"]
        requests = [item for item in candidates if item.verdict == "RFI"]
        closes = [item for item in candidates if item.verdict == "CLOSE"]
        if hard:
            dispositions.append(("ESCALATE", _best(hard, ESCALATE_PRIORITY)))
        elif escalations:
            dispositions.append(("ESCALATE", _best(escalations, ESCALATE_PRIORITY)))
        elif requests:
            dispositions.append(("RFI", _best(requests, RFI_PRIORITY)))
        elif closes:
            dispositions.append(("CLOSE", _best(closes, CLOSE_PRIORITY)))
        else:
            dispositions.append(("ESCALATE", None))

    if any(verdict == "ESCALATE" for verdict, _ in dispositions):
        chosen = [finding for verdict, finding in dispositions if verdict == "ESCALATE" and finding is not None]
        open_alerts = [
            alert for alert, (kind, finding) in zip(alerts, dispositions, strict=False) if kind == "ESCALATE" and finding is None
        ]
        winner = (
            _best(chosen, ESCALATE_PRIORITY) if chosen else _unexplained(inst, case, open_alerts or alerts, context)
        )
        verdict = "ESCALATE"
        extra = []
        if open_alerts and len(open_alerts) < len(alerts):
            extra.append("At least one alert has no policy explanation, so the case cannot be closed.")
        sentences = list(winner.sentences) + extra
    elif any(verdict == "RFI" for verdict, _ in dispositions):
        chosen = [finding for verdict, finding in dispositions if verdict == "RFI" and finding is not None]
        winner = _best(chosen, RFI_PRIORITY)
        verdict = "RFI"
        sentences = []
        seen = set()
        for finding in chosen:
            for sentence in finding.sentences:
                if sentence not in seen:
                    seen.add(sentence)
                    sentences.append(sentence)
    else:
        chosen = [finding for _, finding in dispositions if finding is not None]
        winner = _best(chosen, CLOSE_PRIORITY)
        verdict = "CLOSE"
        sentences = list(winner.sentences)
        if len(alerts) > 1:
            sentences.append(f"Every alert on case {case.id} has a policy explanation, so the case is closed.")

    evidence_ids: list[str] = list(winner.evidence_ids)
    if verdict == "CLOSE":
        for _, item in dispositions:
            if item:
                evidence_ids.extend(item.evidence_ids)
    elif verdict == "RFI":
        for kind, item in dispositions:
            if kind == "RFI" and item:
                evidence_ids.extend(item.evidence_ids)

    return Decision(
        case_id=case.id,
        alert_ids=case.alert_ids,
        verdict=verdict,
        reason_code=winner.code,
        reason=_compose(sentences, context),
        evidence=_evidence(inst, evidence_ids),
        findings=tuple(findings),
        context=tuple(context),
    )


def decide_institution(inst: Institution) -> list[Decision]:
    decisions = []
    for case in inst.cases:
        try:
            decisions.append(decide_case(inst, case))
        except Exception as exc:  # a broken case must not become a silent close
            decisions.append(
                Decision(
                    case_id=case.id,
                    alert_ids=case.alert_ids,
                    verdict="ESCALATE",
                    reason_code="ACTIVITY_UNEXPLAINED",
                    reason=(
                        f"Case {case.id} could not be decided from its records ({type(exc).__name__}). "
                        "The case is escalated because a failure is not a ground for closure. "
                        "A reviewer should read the alert and the evidence pack."
                    ),
                    evidence=_evidence(inst, [case.customer_id, *case.alert_ids]),
                )
            )
    return decisions
