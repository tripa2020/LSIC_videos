"""Anthropic (Claude) JSON caller — the cognition synthesis pass (DEPTH v2).

Scoped to the lecture **cognition** call: the one focused *reasoning* call per talk where a
frontier model earns its keep (idiosyncratic operating algorithm, epistemic status + boundary
conditions, domain-transfer questions). The 122 LSIC **briefing** batch stays single-backend
Gemini — this module is never on that path.

CLOUD_BATCH dropped the `anthropic` dep for batch unification; we re-introduce it here, **lazily**
(imported inside ``_client`` only). So importing this module is dep-free, and fakes-only tests
inject a fake ``client`` and never touch the SDK or the network.

Default model: Claude Opus 4.8 (``claude-opus-4-8``) with adaptive thinking + high effort — the
reasoning-quality lever. One bounded call per talk, so cost is trivial.
"""
from __future__ import annotations

import json
import os
import time

from src import util

DEFAULT_MODEL = "claude-opus-4-8"
MAX_OUTPUT_TOKENS = 16000

# The ONLY pricing table in the repo (per complexity review — no pre-call estimators
# duplicating this knowledge). $ per Mtok (input, output). Unknown model → cost not printed.
PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
}


def _report_cost(model: str, resp) -> None:
    """Print ACTUAL usage→$ for one call (DEPTH v3: observe real cost before any ceiling is
    set — OQ9). Silent when the response carries no usage (fakes) or the model is unpriced."""
    u = getattr(resp, "usage", None)
    tin = getattr(u, "input_tokens", 0) or 0
    tout = getattr(u, "output_tokens", 0) or 0
    if not (tin or tout) or model not in PRICE_PER_MTOK:
        return
    pin, pout = PRICE_PER_MTOK[model]
    cost = tin / 1e6 * pin + tout / 1e6 * pout
    print(f"  [anthropic] {model}: {tin} in / {tout} out tokens ≈ ${cost:.2f}", flush=True)


def _client():
    """Build a real Anthropic client (lazy import keeps module import dep-free)."""
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set — the cognition passes route to Claude "
            "(COGNITION_MODEL, default claude-fable-5). Set the key in .env; without it "
            "the cognition layer degrades with a visible cognition_status.")
    import anthropic
    return anthropic.Anthropic(api_key=key)


def _extract_json(text: str) -> dict:
    """Parse a JSON object from a model response, tolerant of code fences and prose preamble /
    trailing commentary (Claude is reliable at instruction-driven JSON, but adaptive thinking can
    occasionally wrap it). Tries fenced/bare parse first, then the outermost balanced ``{...}``."""
    s = util.strip_fences(text or "").strip()
    if not s:
        raise ValueError("empty response text (no JSON to parse)")
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start = s.find("{")
        if start == -1:
            raise
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(s[start:i + 1])
        raise


def call_json(system: str, user: str, *, model: str = DEFAULT_MODEL,
              max_tokens: int = MAX_OUTPUT_TOKENS, client=None, attempts: int = 4,
              sleep=time.sleep) -> dict:
    """One focused JSON call to Claude → parsed dict (caller validates against the schema).

    Adaptive thinking + ``effort: high`` for the reasoning task; JSON is requested via the prompt
    and parsed tolerantly (``_extract_json``). Retries transient API / malformed-JSON blips with
    linear backoff; **fails fast** on a deterministic binding error (wrong SDK version → TypeError)
    and on a structural stop (refusal / max_tokens-before-text) rather than burning all attempts.
    """
    client = client or _client()
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": "high"},
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except (TypeError, AttributeError) as e:     # SDK-surface mismatch (dep too old) — deterministic
            raise RuntimeError(f"Anthropic call binding error ({type(e).__name__}: {e}); "
                               f"the anthropic SDK is likely too old (needs >=0.77)") from e
        except Exception as e:                        # transient API/network error → backoff + retry
            last = e
            if attempt < attempts - 1:
                sleep(5 * (attempt + 1))
                continue
            raise

        _report_cost(model, resp)                     # billed regardless of what follows
        stop = getattr(resp, "stop_reason", None)
        if stop == "refusal":                         # don't retry a policy refusal
            raise RuntimeError(f"Anthropic refused (stop_details={getattr(resp, 'stop_details', None)})")
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        if not text and stop == "max_tokens":         # truncated before any text — bump max_tokens
            raise RuntimeError("Anthropic hit max_tokens before producing text; raise max_tokens")
        try:
            return _extract_json(text)
        except (ValueError, json.JSONDecodeError) as e:
            if stop == "max_tokens":
                # Truncated mid-JSON: deterministic — retrying identical params re-buys the same
                # truncation at full price (observed 4×$1.70 on the v4.1 run). Fail fast; the
                # caller (cognition._pass) owns the retry/fallback policy.
                raise RuntimeError(f"output truncated at max_tokens={max_tokens} "
                                   f"(unparseable JSON) — raise max_tokens") from e
            last = e                                      # malformed/empty → one more attempt
            if attempt < attempts - 1:
                sleep(5 * (attempt + 1))
                continue
            raise
    raise last                                        # pragma: no cover (loop always returns/raises)
