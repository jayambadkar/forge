"""OpenAI-compatible reviewer. Temperature 0, schema-checked, hash-cached.

A suggestion is allowed to stand beside the rules decision. It is not allowed
to create a CLOSE the rules did not already reach, and an invalid or
low-confidence payload is discarded.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .codes import verdict_for

XAI_BASE_URL = "https://api.x.ai/v1"
XAI_MODEL = "grok-4"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "x-ai/grok-4"
MIN_CONFIDENCE = 0.8

SCHEMA_KEYS = ("verdict", "reason_code", "reason", "evidence", "confidence")


def content_hash(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cache_path(root: Path, digest: str) -> Path:
    return root / digest[:2] / f"{digest}.json"


def read_cache(root: Path, digest: str) -> dict | None:
    path = cache_path(root, digest)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def write_cache(root: Path, digest: str, value: dict) -> None:
    path = cache_path(root, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")


def validate_suggestion(payload: dict, allowed_ids: set[str]) -> dict | None:
    if not isinstance(payload, dict):
        return None
    if any(key not in payload for key in SCHEMA_KEYS):
        return None
    verdict = payload.get("verdict")
    code = payload.get("reason_code")
    if verdict not in {"CLOSE", "RFI", "ESCALATE"}:
        return None
    if verdict_for(str(code)) != verdict:
        return None
    raw_confidence = payload.get("confidence")
    if not isinstance(raw_confidence, (int, float, str)):
        return None
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        return None
    if confidence < MIN_CONFIDENCE:
        return None
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        return None
    if any(item not in allowed_ids for item in evidence):
        return None
    return {
        "verdict": verdict,
        "reason_code": code,
        "reason": reason.strip(),
        "evidence": sorted(set(evidence)),
        "confidence": confidence,
    }


def apply_guard(rules_verdict: str, suggestion: dict | None) -> dict | None:
    """Return the suggestion the product may show, or None if it must be dropped.

    CLOSE from the model is kept only when the rules already closed.
    """
    if suggestion is None:
        return None
    if suggestion["verdict"] == "CLOSE" and rules_verdict != "CLOSE":
        return None
    return suggestion


def complete(payload: dict, *, base_url: str, api_key: str, model: str, timeout: float = 60) -> dict:
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You review one transaction-monitoring case. Reply with a single JSON object "
                    "with keys verdict, reason_code, reason, evidence, confidence. "
                    "evidence must be a subset of the ids you were given. Do not close a case "
                    "unless the policy notes already say it is explained."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
        ],
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    content = parsed["choices"][0]["message"]["content"]
    return json.loads(content)


def resolve_adjudicator() -> dict | None:
    """Pick the provider that matches the key. No key means the policy engine stands.

    XAI_API_KEY uses https://api.x.ai/v1 and grok-4. OPENROUTER_API_KEY uses
    https://openrouter.ai/api/v1. If both keys are set, FORGE_LLM_PROVIDER
    (xai or openrouter) chooses; otherwise OpenRouter is used.
    """
    provider = (os.environ.get("FORGE_LLM_PROVIDER") or "").strip().lower()
    xai_key = os.environ.get("XAI_API_KEY") or ""
    open_key = os.environ.get("OPENROUTER_API_KEY") or ""
    use_xai = provider == "xai" or (provider != "openrouter" and xai_key and not open_key)
    use_open = provider == "openrouter" or (provider != "xai" and bool(open_key))
    if use_xai and xai_key and not use_open:
        return {
            "provider": "xai",
            "key": xai_key,
            "base": os.environ.get("XAI_BASE_URL", XAI_BASE_URL),
            "model": os.environ.get("FORGE_LLM_MODEL", XAI_MODEL),
        }
    if use_open and open_key:
        return {
            "provider": "openrouter",
            "key": open_key,
            "base": os.environ.get("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
            "model": os.environ.get("FORGE_LLM_MODEL", OPENROUTER_MODEL),
        }
    if xai_key:
        return {
            "provider": "xai",
            "key": xai_key,
            "base": os.environ.get("XAI_BASE_URL", XAI_BASE_URL),
            "model": os.environ.get("FORGE_LLM_MODEL", XAI_MODEL),
        }
    return None


def suggest(
    payload: dict,
    allowed_ids: set[str],
    *,
    cache_dir: Path | None = None,
    live: bool | None = None,
) -> dict | None:
    digest = content_hash(payload)
    if cache_dir is not None:
        cached = read_cache(cache_dir, digest)
        if cached is not None:
            return validate_suggestion(cached, allowed_ids)
    if live is None:
        live = os.environ.get("FORGE_LLM") == "1"
    chosen = resolve_adjudicator()
    if not live or chosen is None:
        return None
    try:
        raw = complete(payload, base_url=chosen["base"], api_key=chosen["key"], model=chosen["model"])
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError, OSError):
        return None
    checked = validate_suggestion(raw, allowed_ids)
    if checked is not None and cache_dir is not None and os.environ.get("FORGE_LLM_CACHE_WRITE") == "1":
        write_cache(cache_dir, digest, checked)
    return checked


def adjudicator_status() -> dict:
    """Say which agent would decide, without calling the network.

    system/run never calls the model. With no key, or with FORGE_LLM unset,
    the policy engine is the only agent.
    """
    live = os.environ.get("FORGE_LLM") == "1"
    chosen = resolve_adjudicator()
    if live and chosen is not None:
        where = "xAI" if chosen["provider"] == "xai" else "OpenRouter"
        return {
            "agent": "policy-engine",
            "llm": chosen["model"],
            "provider": chosen["provider"],
            "called": False,
            "note": f"{where} adjudicator {chosen['model']} is configured. The scored verdict is still the policy engine; system/run does not call the model.",
        }
    return {
        "agent": "policy-engine",
        "llm": "not-used",
        "provider": "",
        "called": False,
        "note": "Decided by the policy engine. The LLM adjudicator was not called: set FORGE_LLM=1"
        " and either XAI_API_KEY or OPENROUTER_API_KEY. No key is present, so the fallback is the policy verdict.",
    }
