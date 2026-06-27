"""MAPRED: size-bounded windowing of evidence into map-units (NOT author chapters).

Map-reduce synthesis splits a long talk into windows sized to a char/token budget so each gets the
model's full attention with no 140k truncation. The real constraint is *context size* — which
scales with video length — not where an uploader happened to draw chapter marks, so we window by
size and ignore ``meta["chapters"]`` entirely. ``segment()`` ALWAYS returns ≥1 window (R5): a short
talk under budget yields a single window ⇒ the caller falls back to today's single-call path
(degrade-to-today).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from src.contracts import Evidence

# Per-window budget in CHARACTERS (≈ tokens × 4 — a deterministic, network-free proxy for token
# count, so the fakes-only tests need no tokenizer). Override via env WINDOW_BUDGET. Default 45k
# chars (~11k tokens): small enough for focused attention, large enough not to over-fragment.
WINDOW_BUDGET = 45_000


@dataclass
class Window:
    """One map-unit: a contiguous, time-ordered slice of transcript evidence under the budget."""
    index: int
    start: float
    end: float
    evidence: list[Evidence] = field(default_factory=list)


def _budget() -> int:
    """Resolve the budget at call time (env override wins). Falsy/invalid ⇒ the default."""
    try:
        return int(os.environ.get("WINDOW_BUDGET") or WINDOW_BUDGET)
    except (TypeError, ValueError):
        return WINDOW_BUDGET


def segment(evidence: list[Evidence], budget_chars: int | None = None) -> list[Window]:
    """Window transcript evidence into size-bounded map-units, time-ordered. ALWAYS ≥1 window.

    Greedy: accumulate evidence (sorted by ``timestamp_start``) until adding the next item would
    push the window's text past ``budget_chars``, then close the window and start the next. A single
    item larger than the budget still gets its own window (never dropped / never split mid-segment).
    Non-transcript evidence is ignored (the descriptive context is transcript-grounded). Empty input
    ⇒ one empty window so downstream consumers always see N ≥ 1.
    """
    budget = budget_chars if budget_chars is not None else _budget()
    transcript = sorted((e for e in evidence if e.kind == "transcript"),
                        key=lambda e: e.timestamp_start)
    if not transcript:
        return [Window(index=0, start=0.0, end=0.0, evidence=[])]

    windows: list[Window] = []
    cur: list[Evidence] = []
    size = 0
    for e in transcript:
        n = len(e.text or "")
        if cur and size + n > budget:                      # close the current window, start anew
            windows.append(Window(index=len(windows), start=cur[0].timestamp_start,
                                  end=cur[-1].timestamp_end, evidence=cur))
            cur, size = [], 0
        cur.append(e)
        size += n
    if cur:
        windows.append(Window(index=len(windows), start=cur[0].timestamp_start,
                              end=cur[-1].timestamp_end, evidence=cur))
    return windows
