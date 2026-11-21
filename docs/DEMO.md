# Demo

About three minutes. Desk at http://127.0.0.1:43123. Do not turn on `FORGE_LLM`.

## Script

0:00 Dashboard. One recommendation per case: close, ask, or escalate. A wrong close is the expensive mistake.

0:20 Runs. Pick a firm. Start batch run. Same command as `system/run`. No network.

0:45 Case queue. Search, verdict, firm. A card is the customer, the recommendation, one sentence, the amount, and how long it has been open.

1:10 Open a case. The recommendation is the paragraph at the top. Accept, Override, or Draft email.

1:30 Open the audit trail. It records who wrote the recommendation, the evidence, and any later change.

1:50 Override with a note. The trail shows the before and after.

2:10 Export, Decisions JSONL. One line per case.

2:25 How it works. The recommendation is what gets written. The score does not beat it, so it stays off the scored path.

2:45 Back to the dashboard.

## If the batch run is slow

Use Replay stored output. The decisions are the same file.
