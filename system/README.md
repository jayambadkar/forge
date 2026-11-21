# How Forge decides

`system/run` reads one institution folder and writes one JSON line per case. On the official books (files that carry `rule_id`) it uses `forge_engine/sop.py`. On the fixture books it uses the earlier labelling functions.

The official path does not call a model and does not use a random seed. Two runs on the same folder write the same bytes. A language-model reviewer in `forge_engine/llm.py` runs only when `FORGE_LLM=1` and a key is set. `XAI_API_KEY` uses `https://api.x.ai/v1` and `grok-4`. `OPENROUTER_API_KEY` uses `https://openrouter.ai/api/v1`. If both are set, `FORGE_LLM_PROVIDER` chooses and otherwise OpenRouter is used. With no key, `suggest` returns nothing and the policy verdict stands. The reviewer cannot create a `CLOSE` the rules did not already reach. `system/run` does not call it.

A case closes only when every alert is tied to a document, an own-account statement, a reconciled cash record, or a list match the register shows is a different person. Fraud reports, unmatched structuring, an unexplained higher-risk corridor, and a confirmed list match escalate. Anything merely unexplained, with no sign of crime, becomes an RFI that names the document to ask for. Round amounts, shared devices, and crypto are not used as a verdict.

Own-account movements at or above five times declared monthly income or turnover are `RFI_UPDATED_PROFILE`. Payments and FX payments of £10,000 or more to someone other than the client need a matching invoice or contract.

On this machine a full institution (1,000 cases) finishes in about half a second, so 200 cases are well under a second and use no paid model calls.
