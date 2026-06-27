"""MAPRED: map-reduce synthesis over size-bounded windows (the lecture profile's descriptive call).

Removes the 140k single-call truncation (``synthesize._build_event_context`` cap) on long talks by
giving each window the model's full attention, then weaving ONCE:

  MAP    — per window, extract LOCAL facts only (key_points / methods / notable_claims /
           open_questions / citations / speakers), each grounded by evidence_id. A window NEVER
           emits a summary, expert lens, takeaway, field-implication or outlook — those are GLOBAL
           and produced exactly once in REDUCE (single-producer-per-section ⇒ structural coherence).
  REDUCE — one global synthesis over the union of all window facts. Reuses the profile's DESCRIPTIVE
           thematic prompt VERBATIM, so the reduce output is the same shape the renderer already
           consumes — no render change needed.

In-memory only (no per-window cache in v1). The caller auto-selects this when segmentation yields
≥2 windows; a single window falls back to today's single call (byte-identical / degrade-to-today).

``call_json`` (signature ``(client, system, user, max_tokens=...)``) is INJECTED by the caller —
``synthesize._call_gemini_json`` in prod, a fake in tests — so this module is import-light and
network-free (no dependency back on ``synthesize`` ⇒ no import cycle).
"""
from __future__ import annotations

from typing import Callable

from src import util
from src.segment import Window

# The MAP system prompt: LOCAL extraction only. Deliberately OMITS every global/synthesized field
# (summary, expert_lenses, title, takeaways, field_implications, industry_outlook) so a window
# CANNOT emit N disconnected summaries — those are woven once in REDUCE.
MAP_SYSTEM_PROMPT = """You extract the LOCAL facts from ONE window (a contiguous slice) of a longer talk transcript. You receive transcript lines, each tagged [ev_...].

Output ONLY a single JSON object with EXACTLY this shape (no prose, no code fences):
{
  "key_points":     [{"text": "<a main point made in THIS window>", "evidence_id": "ev_..."}],
  "methods":        [{"text": "<a method / approach / technique used or described>", "evidence_id": "ev_..."}],
  "notable_claims": [{"text": "<a specific load-bearing claim>", "basis": "<one-line basis shown>", "evidence_id": "ev_..."}],
  "open_questions": [{"text": "<an unresolved question raised>", "evidence_id": "ev_..."}],
  "citations":      [{"text": "<a paper/tool/dataset/standard cited>", "evidence_id": "ev_..."}],
  "speakers":       [{"label": "A", "role": "<role/identity if inferable>", "time_range": "mm:ss→mm:ss"}]
}

EXTRACT ONLY WHAT IS IN THIS WINDOW. Do NOT write a summary, takeaways, expert lenses, or any
whole-talk synthesis — those are produced later from all windows together. Be specific and technical.

CITATION RULE: every evidence_id MUST appear in this window's transcript. Never invent one. A field
with nothing to report → an empty list. Produce the JSON now."""

# the local keys a window MAY emit — used to format the reduce context AND asserted by the
# single-producer test (no global/synthesized key may appear here).
LOCAL_KEYS = ("key_points", "methods", "notable_claims", "open_questions", "citations", "speakers")


def _window_context(w: Window) -> str:
    """Format a window's transcript evidence as grounded lines for the MAP call."""
    head = f"=== WINDOW {w.index + 1} [{util.mmss(w.start)}-{util.mmss(w.end)}] ==="
    lines = [f"[{e.evidence_id}] {e.speaker_id or '?'}: {e.text}" for e in w.evidence]
    return head + "\n" + "\n".join(lines)


def map_extract(client, w: Window, call_json: Callable) -> dict:
    """MAP one window → local facts (LOCAL_KEYS only). One window's failure degrades to ``{}`` so a
    single bad extract never sinks the whole reduce."""
    user = _window_context(w) + "\n\nProduce the local-facts JSON for THIS window now."
    try:
        data = call_json(client, MAP_SYSTEM_PROMPT, user, max_tokens=8000)
    except Exception as e:
        print(f"    [mapreduce] window {w.index + 1} extract failed: {e}", flush=True)
        return {}
    return {k: data.get(k, []) for k in LOCAL_KEYS}


def _reduce_context(extracts: list[dict]) -> str:
    """Concatenate all window extracts into one compact, evidence-grounded context for REDUCE."""
    blocks: list[str] = []
    for i, ex in enumerate(extracts, 1):
        rows = [f"=== WINDOW {i} FACTS ==="]
        for key in LOCAL_KEYS:
            items = ex.get(key) or []
            if not items:
                continue
            rows.append(f"{key.upper()}:")
            for it in items:
                if key == "speakers":
                    rows.append(f"- {it.get('label', '?')}: "
                                f"{it.get('role', '')} {it.get('time_range', '')}".rstrip())
                else:
                    basis = f" (basis: {it.get('basis')})" if it.get("basis") else ""
                    rows.append(f"[{it.get('evidence_id', '')}] {it.get('text', '')}{basis}")
        blocks.append("\n".join(rows))
    return "\n\n".join(blocks)


def reduce_synth(client, extracts: list[dict], system_prompt: str, call_json: Callable) -> dict:
    """REDUCE: one global synthesis over the union of window facts → the full thematic dict. Reuses
    the profile's descriptive ``system_prompt`` verbatim, so the output matches what render expects."""
    context = _reduce_context(extracts)
    user = (f"=== EVENT CONTEXT (extracted facts from {len(extracts)} sequential windows of ONE "
            f"talk) ===\n{context}\n\nProduce the thematic JSON object now. Synthesize every section "
            f"ONCE across ALL windows (do not repeat per window). Every cited evidence_id must appear "
            f"in the EVENT CONTEXT above.")
    return call_json(client, system_prompt, user, max_tokens=32000)


def mapreduce_thematic(client, windows: list[Window], system_prompt: str,
                       call_json: Callable) -> dict:
    """Full map-reduce: MAP every window (in-memory) → REDUCE once. Returns a thematic dict shaped
    exactly like ``synthesize._call_thematic``'s output (a drop-in for the lecture descriptive call)."""
    print(f"  [synthesize] map-reduce thematic over {len(windows)} windows…", flush=True)
    extracts = [map_extract(client, w, call_json) for w in windows]
    return reduce_synth(client, extracts, system_prompt, call_json)
