# Forge — plan

Forge is the OS for financial monitoring. This pass builds the Track 1 scorer (transaction-monitoring alert triage) and the analyst product around it: a deterministic policy engine, a guarded LLM reviewer, a calibrated risk model, a .NET API, and a React workstation.

The official institution folders are the source of thresholds, currencies, and reason codes. A research note on feature engineering used dollar examples (including a generic $10k). Those figures are not used. Amounts are GBP. A limit applies only when that institution's `POLICY.md` states it.

## Revision log

### Pass 1

A four-agent bus (rules, LLM, gradient boosting, aggregator) with the LLM allowed to close ambiguous cases, a pooled random k-fold, and public PaySim labels mixed into training.

### Pass 2 — Occam

The bus was ceremony. One pipeline function is the same system and is testable. There is one rules module, one OpenAI-compatible client, and two classical models. Institution differences are parsed policy data, not four codebases. PaySim is a bad label source for this task and is not used as one.

### Pass 3 — score, leakage, reproducibility

Wrongful `CLOSE` is the expensive error (cost 10). Over-caution costs 2–3. Escalate-everything scores 0, so the system must close real false positives, but only on a policy ground.

- A case closes only when every alert is explained by a labelling function grounded in that institution's SOP.
- The LLM never creates a `CLOSE`. Invalid JSON, unknown evidence ids, or low confidence leave the rules decision untouched. Temperature is 0, output is schema-checked, and the cache key is a hash of the canonical request.
- `system/run` does not call the network. Live LLM review is a separate, explicit switch so five scored runs stay identical.
- The model is a disagreement detector. It is not wired into `system/run` as a closer.
- Cross-validation is `StratifiedGroupKFold`, grouped by customer, run inside each institution. Learned thresholds, if any, are fit on training folds only. The 5x rule and the invoice limit are specifications, not parameters we tune.
- Customer history used as a baseline is that customer's own case file. It is not a label, and it is not another customer's outcome.
- No development case id, name, or amount is hard-coded in the engine.

## Research input

Applied from the research brief supplied with this build:

- Labelling functions written from the SOPs are the training signal. There are no gold labels. `CLOSE` is the hard decision.
- Validate with grouped folds so one customer's cases do not sit on both sides of a split. Stratify within the institution. Do not fit labelling functions or numeric cutoffs on the fold you are scoring.
- LLM calls use temperature 0, a constrained JSON object, evidence-id citations, and a content-hash cache. A bad or low-confidence completion cannot become `CLOSE`.
- Public AML sets (IBM AML transactions, SAML-D) are useful only to check that feature code runs. They are not verdict labels. PaySim is mobile-money fraud and is a poor stand-in. This pass does not download them.

Methods those conclusions rely on, checked against the primary sources rather than quoted from memory of the brief:

- Ratner, Bach, Ehrenberg, Fries, Wu, Ré. *Snorkel: Rapid Training Data Creation with Weak Supervision.* PVLDB 11(3), 2017. Labelling functions may abstain; they are heuristics, not ground truth.
- scikit-learn `StratifiedGroupKFold`. Each group is entirely in train or entirely in test. Class proportions are preserved as far as the grouping allows.

What the metrics measure: agreement with the SOP labelling functions. They do not measure agreement with the hidden test labels. The UI and the model report say this in those words.

## Architecture

```
institution folder
        │
        ▼
system/run  (Python 3, cwd-independent)
        │
        ├─ load jsonl + evidence markdown + POLICY.md
        ├─ labelling functions (pure, ordered aggregation)
        ├─ optional cached LLM suggestion (cannot close)
        └─ output jsonl  {case_id, alert_ids, verdict, reason_code, reason, evidence}
                │
                ▼
backend  ASP.NET Core 10 minimal API
        reads output, case files, and the CV report
        starts system/run and streams stderr + result lines
                │
                ▼
frontend  Vite + React + TypeScript
        queue, case drill-down, evidence, decision, institutions, models, simulation
```

Python is the scoring language because the work is JSONL, text policy, and scikit-learn. The .NET API is the product boundary: it shells out to `system/run` and serves the workstation. The rules are not reimplemented in C#.

`system/run <institution_folder> <output_file.jsonl>` takes absolute paths, reads only that folder, and writes only that file. Two hundred cases are a few seconds of CPU. A missing or failed case is written as `ESCALATE` / `ACTIVITY_UNEXPLAINED` so a gap cannot become a silent close.

## Data model

Internal records are normalised through an alias map (`customer_id` / `party_id`, `amount` / `amount_gbp`, and so on). Extra fields are kept on the raw record so a new file layout does not require a new engine, only a new alias when a concept is unnamed.

| File | Role |
| --- | --- |
| `cases.jsonl` | One case, its alert ids, its customer |
| `alerts.jsonl` | Typology, narrative, linked transactions |
| `transactions.jsonl` | Amount, currency, direction, counterparty, device, own-account flag |
| `customers.jsonl` | Name, date of birth, country, expected monthly amount, accounts |
| `evidence.jsonl` + `evidence/*.md` | Invoices, source-of-funds notes, agreements |
| `previous_reviews.jsonl` | What an earlier review actually described |
| `internal_list.jsonl` | Names and corroborating identifiers |
| `POLICY.md` | The SOP for this institution |

Evidence ids emitted in the output are harvested from `*_id` fields and evidence filenames. Anything not in that set is dropped.

## Decision pipeline

Labelling functions abstain or return a finding tied to specific alerts and evidence ids.

1. **Internal list.** Confirmed match (same normalised name, plus the same date of birth, or the same exact name and the same country) is a hard `ESCALATE`. A date of birth that contradicts the person refutes a screening hit and can close that screening alert. A name-only overlap asks for identity confirmation (`RFI`). Names are compared only for the customer, the counterparties on the alert, and any list id the alert already cites.
2. **Own accounts and the 5x rule.** When the SOP states the multiple, an own-account alert at or under `multiple × expected monthly amount` is explained. Above it, the own-account story is not available and the alert is escalated. No baseline in the case file means the function abstains rather than inventing one.
3. **Document limits parsed from the SOP.** Example: payments_fx invoices at or above the GBP figure written next to "invoice" (the brief's £10k, not a generic $10k). A matching document explains the payment. A missing document is an `RFI` that names the counterparty, the amount, and the document. A document whose amount conflicts is an escalation. The same parser covers source-of-funds and subscription-agreement lines in the other SOPs.
4. **Earlier reviews.** A review covers an alert only when its text names the typology or the counterparty, and any amount it states is not below the alert. A review about salary does not cover crypto.
5. **Expected activity.** Used only when the SOP says in-profile activity may be closed, and only when the amount is within the stated monthly expectation, the country matches, and the alert is not cash, crypto, or screening.
6. **Context signals.** Round amounts, a device shared with another customer, and crypto are recorded and may be named in the reason. They are not a ground for `CLOSE` or for `ESCALATE`. An alert with nothing else is unexplained, and unexplained escalates because it cannot be closed.

Aggregation, per alert, in order: hard escalation, other escalation, RFI, close, else unexplained. The case takes the worst alert. One unexplained alert blocks `CLOSE`. A hard list match blocks `RFI`.

Reason text is two to four sentences built from the winning findings. It names the customer, the amounts, and the document or review ids. An `RFI` states what to ask for.

Reason codes live in one registry (`codes.py`) and each code belongs to one verdict. When `BRIEF.html` is beside the institution tree and contains the official list, that list replaces the registry before any case is written. Provisional codes used until then are the ones the registry ships with, and they are the codes the fixture SOPs exercise.

## LLM reviewer

`forge_engine/llm.py` talks to an OpenAI-compatible chat endpoint. Default base URL `https://api.x.ai/v1`, model `grok-4`, key `XAI_API_KEY`. Request temperature is 0. The cache key is SHA-256 of the canonical JSON body. `system/run` reads a cache entry only when `FORGE_LLM=1` and still refuses to adopt a `CLOSE` the rules did not already reach. With no key, the rules decision is the decision. The workstation can show the suggestion beside the scored verdict.

## ML

Features are behavioural and policy-shaped counts computed from the case file: amounts versus the customer's own expectation, own-account ratio, counterparty and country counts, round-amount ratio, crypto ratio, shared device, list outcome, review coverage, document threshold. The label is the labelling-function verdict.

Split, per institution:

1. Hold out 20% of customers (seed 42). Every case of a customer is on one side.
2. On the remainder, `StratifiedGroupKFold` with five folds when there are at least five customer groups per class, otherwise fewer folds, reported as such.
3. Models: L2 logistic regression and `HistGradientBoostingClassifier`. No threshold is chosen on the hold-out.
4. A second logistic regression sees behavioural features only (list result, review coverage, and document flags removed) so the report can show whether closes are recoverable without the SOP facts. They usually should not be.

The report is `ml/report.json`. The model file is not loaded by `system/run`.

`ml/backtest_public.py` replays the same feature function on a local IBM AML or SAML-D CSV if someone places one next to it. It does not download, and it does not emit verdicts.

## Frontend

Dark, dense, copper accent on a near-black ground. IBM Plex Sans and IBM Plex Mono.

- **Queue.** Institution, verdict, and text filters. Verdict, reason code, customer, amount.
- **Case.** Alerts, transaction timeline, evidence reader, decision panel with evidence links and the labelling-function trace.
- **Institutions.** Verdict mix and reason-code counts for the four books.
- **Models.** CV table, the honesty note about labels, behavioural-only comparison.
- **Simulation.** Run `system/run` on a folder and stream cases as they land. Replay streams an existing output file.

Empty, loading, and error states are explicit. The layout collapses to one column under 960px.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Process up, which book is loaded |
| GET | `/api/institutions` | The four books and their counts |
| GET | `/api/cases` | Queue page |
| GET | `/api/cases/{institution}/{caseId}` | Drill-down |
| GET | `/api/models` | CV report |
| POST | `/api/runs` | Start `system/run` or a replay |
| GET | `/api/runs/{id}/events` | Server-sent events |

The API does not re-decide. It serves what `system/run` wrote plus the case files.

## Repository

```
docs/PLAN.md
system/run
system/README.md
system/forge_engine/
backend/
frontend/
ml/train.py
ml/backtest_public.py
eval/harness.py
tests/
fixtures/demo/institutions/{bank,emoney,investment,payments_fx}/
output/{bank,emoney,investment,payments_fx}.jsonl
data/hackathon/          official extract, not committed
```

`./dev.sh` starts the API and the workstation.

## Milestones

1. Plan, including this revision log.
2. Rules engine, `system/run`, schema and determinism harness, fixture book with SOP-derived expected verdicts.
3. Output files for whichever book is on disk. Official dev folders win over the fixture book the moment they are present.
4. ASP.NET Core API.
5. Forge workstation, then screenshots.
6. Grouped CV report.
7. README, tests, no secrets.

## Known risk

The scored reason-code strings have to be the brief's strings. The registry is one module, and `BRIEF.html` overrides it when the official list can be read. Until that file is in the tree, the fixture book is what the workstation and the output files contain, and it is labelled as such.
