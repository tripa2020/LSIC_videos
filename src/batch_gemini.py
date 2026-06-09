"""Gemini Batch transport (Part 1, M-B1).

Pure batch-request transport behind one small interface. It knows **nothing** about any
stage's cache layout (R1): it returns ``{custom_id: response}`` and the calling stage owns
mapping results back into its own cache. Failed ``custom_id``s are simply **absent** from
the returned map (R4) — the pipeline's manifest-gate + resume re-enqueues them on the next
run, so there is deliberately no retry code here.

Hybrid submit: an inline request list under ``INLINE_THRESHOLD`` (fast, no file lifecycle —
ideal for the 5-event slice); a JSONL-via-Files-API upload above it (scales to the full
122-event fan-out of thousands of requests). Media (audio/frames) is referenced through the
Files API inside each request's ``contents`` in **both** paths — this module only chooses how
the request *batch* is delivered, never how media is carried.

Test posture (CLAUDE.md Engineering Discipline — fakes-only, no network): the request body
build, JSONL build, threshold pick, custom_id mapping, and failed-id omission are all pure
and unit-tested against fakes. The thin SDK extraction in ``resolve``/``poll`` (exact
``BatchJob`` field names) is verified live on the VM at plan milestone M-C2.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Any

# ≤ this many requests → inline list; above → JSONL file upload.
INLINE_THRESHOLD = 100

# Gemini batch job lifecycle: these end the poll loop.
TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}


@dataclass
class BatchRequest:
    """One unit of LLM work. ``custom_id`` is the ONLY handle back to the caller — it is
    stage-minted, stable, and echoed by the batch output so mapping is order-independent."""

    custom_id: str
    model: str
    contents: Any
    config: Any = None


# --- pure request/payload builders (no client, no network) ---

def _request_payload(r: BatchRequest) -> dict:
    """The per-request body shared by the inline and JSONL paths."""
    body: dict[str, Any] = {"model": r.model, "contents": r.contents}
    if r.config is not None:
        body["config"] = r.config
    return body


def _to_inlined(r: BatchRequest) -> dict:
    """Inline request carrying its key so responses map by key, not by position."""
    return {"key": r.custom_id, "request": _request_payload(r)}


def build_jsonl(requests: list[BatchRequest]) -> str:
    """One JSON line per request: ``{"key": custom_id, "request": {...}}``. ``key`` is what
    the batch output echoes back, giving us the custom_id → response mapping (R1)."""
    return "\n".join(
        json.dumps(_to_inlined(r), default=str) for r in requests
    )


# --- pure response mappers (fed already-extracted SDK data; unit-tested directly) ---

def map_inline_responses(keys: list[str], responses: list[Any]) -> dict[str, Any]:
    """Map inline responses back to custom_ids. Failed/empty entries are omitted (R4).

    ``keys`` is the submit-order list of custom_ids; ``responses`` is the parallel inline
    response list. An entry is a failure when it is ``None`` or carries an ``error`` field."""
    out: dict[str, Any] = {}
    for key, resp in zip(keys, responses):
        if resp is None:
            continue
        if isinstance(resp, dict) and resp.get("error"):
            continue
        out[key] = resp.get("response", resp) if isinstance(resp, dict) else resp
    return out


def parse_jsonl_output(text: str) -> dict[str, Any]:
    """Map a downloaded batch output JSONL to ``{key: response}``; error lines omitted (R4)."""
    out: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        key = row.get("key")
        if key is None or row.get("error"):
            continue
        out[key] = row.get("response", row)
    return out


# --- client-driven orchestration (client injected → fakeable; never imports genai) ---

def _norm_state(state: Any) -> str:
    """Normalise an SDK enum / string job state to its bare name."""
    return getattr(state, "name", str(state)).rsplit(".", 1)[-1]


def response_text(resp: Any) -> str:
    """Extract the model's text from a resolved batch response, shape-tolerantly.

    Sync callers read ``resp.text``; a batch-resolved response may instead be a plain dict
    (``candidates[0].content.parts[0].text``) or already a string. This bridges both so a
    stage's prefill can reuse its existing text-parsing. Exact live dict shape verified at
    M-C2; the branches below are unit-tested against fakes."""
    if resp is None:
        return ""
    if isinstance(resp, str):
        return resp
    text = getattr(resp, "text", None)
    if text is not None:
        return text
    if isinstance(resp, dict):
        if isinstance(resp.get("text"), str):
            return resp["text"]
        try:
            parts = resp["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            return ""
    return ""


def submit(client, requests: list[BatchRequest], *,
           inline_threshold: int = INLINE_THRESHOLD) -> str:
    """Create a batch job and return its job name. Hybrid: inline under the threshold,
    JSONL-file upload above it. All requests must share one model (one job = one model)."""
    if not requests:
        raise ValueError("submit() called with no requests")
    model = requests[0].model
    if len(requests) <= inline_threshold:
        src: Any = [_to_inlined(r) for r in requests]
    else:
        buf = io.BytesIO(build_jsonl(requests).encode("utf-8"))
        upload = client.files.upload(file=buf, config={"mime_type": "application/jsonl"})
        src = upload.name
    job = client.batches.create(model=model, src=src)
    return job.name


def poll(client, job_name: str) -> str:
    """Return the normalised job state (use ``is_terminal`` to end the loop)."""
    return _norm_state(client.batches.get(name=job_name).state)


def is_terminal(state: Any) -> bool:
    return _norm_state(state) in TERMINAL_STATES


def resolve(client, job_name: str) -> dict[str, Any]:
    """Fetch a terminal job and return ``{custom_id: response}`` (failures omitted, R4).

    Inline jobs expose responses on ``dest.inlined_responses``; file jobs expose a
    ``dest.file_name`` we download and parse. The field names are SDK-version-specific and
    verified live at M-C2; the mapping *logic* is the unit-tested part above."""
    job = client.batches.get(name=job_name)
    dest = getattr(job, "dest", None)
    inlined = getattr(dest, "inlined_responses", None) if dest is not None else None
    if inlined is not None:
        keys = [getattr(r, "key", None) or (r.get("key") if isinstance(r, dict) else None)
                for r in inlined]
        bodies = [getattr(r, "response", None) or (r.get("response") if isinstance(r, dict) else None)
                  if not (isinstance(r, dict) and r.get("error"))
                  else None
                  for r in inlined]
        return map_inline_responses(keys, bodies)
    file_name = getattr(dest, "file_name", None) if dest is not None else None
    if file_name:
        blob = client.files.download(file=file_name)
        text = blob.decode("utf-8") if isinstance(blob, (bytes, bytearray)) else blob
        return parse_jsonl_output(text)
    return {}
