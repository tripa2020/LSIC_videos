"""The ONE Gemini seam — client construction, retry policy, and JSON parsing.

Every Gemini-backed stage (transcribe · visual · synthesize/MAPRED · slide_book · the batch
prefill client) goes through here. Before this module each stage carried its own copy of the
key lookup, its own ``genai.Client`` with its own timeout, and its own hand-rolled retry loop
with a different attempt count and backoff — four places encoding one decision. Now a vendor,
endpoint, or policy change is a one-file edit (the same shape as ``anthropic_caller``).

- ``make_client(timeout_ms)`` — the only place ``GEMINI_API_KEY`` is read.
- ``generate(...)`` — one ``generate_content`` call under the shared transient-retry policy.
- ``generate_json(...)`` — the same, plus fence-strip + JSON parse + type guard, with bad JSON
  retried on the same budget as transient errors. A ``MAX_TOKENS`` finish raises
  :class:`Truncated` **immediately** (no retry — identical params would truncate identically
  at full price; the retry-storm class already killed in ``anthropic_caller``).

``google.genai`` is imported lazily inside ``make_client`` so importing this module — and every
stage that imports it — stays dependency-free for the fakes-only test suite. ``generate*`` take
any object exposing ``.models.generate_content(**kwargs)``, so tests inject fakes.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from src import util

DEFAULT_TIMEOUT_MS = 300_000     # synthesis-sized; stages pass their own (ASR 180s, VLM 90s)
DEFAULT_ATTEMPTS = 5
DEFAULT_BASE_DELAY = 5.0         # linear backoff: base * (attempt + 1) seconds


class Truncated(RuntimeError):
    """The model stopped at ``max_output_tokens`` — the body is cut mid-JSON. Raised before any
    parse attempt so the caller decides (transcribe splits the audio; synthesis fails loud)."""


def api_key() -> str:
    """The single ``GEMINI_API_KEY`` (or ``GOOGLE_API_KEY``) lookup. Loud when unset."""
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")
    return key


def make_client(timeout_ms: int = DEFAULT_TIMEOUT_MS):
    """A real ``genai.Client`` with a request timeout so a network blip raises (→ retried)
    instead of hanging forever. Lazy import keeps module import dep-free."""
    from google import genai
    from google.genai import types
    return genai.Client(api_key=api_key(),
                        http_options=types.HttpOptions(timeout=timeout_ms))


def finish_reason(resp: Any) -> str:
    try:
        return str(resp.candidates[0].finish_reason)
    except (AttributeError, IndexError, TypeError):
        return ""


def _gen_kwargs(model: str, contents: Any, config: Any) -> dict:
    kwargs: dict[str, Any] = {"model": model, "contents": contents}
    if config is not None:
        kwargs["config"] = config
    return kwargs


def generate(client, *, model: str, contents: Any, config: Any = None,
             attempts: int = DEFAULT_ATTEMPTS, base_delay: float = DEFAULT_BASE_DELAY):
    """One ``generate_content`` call under the shared transient-retry policy; returns the raw
    response. Non-transient errors propagate immediately (``util.retry_transient``)."""
    return util.retry_transient(
        lambda: client.models.generate_content(**_gen_kwargs(model, contents, config)),
        attempts=attempts, base_delay=base_delay)


def parse_json(text: str | None, *, expect: type | None = None) -> Any:
    """Fence-stripped JSON parse with an optional type guard. An empty body is ``[]`` when a
    list is expected (a silent audio chunk legitimately transcribes to nothing); otherwise an
    empty body is an error so the caller retries rather than rendering a blank section."""
    raw = util.strip_fences(text or "")
    if not raw:
        if expect is list:
            return []
        raise ValueError("empty response body")
    data = json.loads(raw)
    if expect is not None and not isinstance(data, expect):
        raise ValueError(f"expected JSON {expect.__name__}, got {type(data).__name__}")
    return data


def generate_json(client, *, model: str, contents: Any, config: Any = None,
                  expect: type | None = None, attempts: int = DEFAULT_ATTEMPTS,
                  base_delay: float = DEFAULT_BASE_DELAY, tag: str = "gemini",
                  extra_transient: tuple[str, ...] = ()) -> Any:
    """``generate`` + ``parse_json`` in ONE retry loop: a transient API error and a
    flaky/partial JSON body both re-issue the call on the same ``attempts`` budget.
    ``MAX_TOKENS`` raises :class:`Truncated` at once (never retried). ``extra_transient``
    adds call-specific retryable markers (the YouTube-URL preview's spurious 400s)."""
    last_raw = ""
    for attempt in range(attempts):
        try:
            resp = client.models.generate_content(**_gen_kwargs(model, contents, config))
        except Exception as e:                               # noqa: BLE001 — classifier decides
            retryable = util.is_transient(e) or any(m in str(e) for m in extra_transient)
            if retryable and attempt < attempts - 1:
                print(f"    [{tag}] transient ({str(e)[:70]}) — retry {attempt + 1}/{attempts}",
                      flush=True)
                time.sleep(base_delay * (attempt + 1))
                continue
            raise
        if "MAX_TOKENS" in finish_reason(resp):
            raise Truncated(f"{tag}: response truncated at max_output_tokens ({model})")
        last_raw = getattr(resp, "text", None) or ""
        try:
            return parse_json(last_raw, expect=expect)
        except (json.JSONDecodeError, ValueError) as e:
            if attempt < attempts - 1:
                time.sleep(base_delay * (attempt + 1))
                continue
            raise RuntimeError(
                f"{tag}: invalid JSON after {attempts} tries ({e}); "
                f"response head: {last_raw[:200]!r}") from e
    raise RuntimeError(f"{tag}: call failed after {attempts} tries")   # unreachable
