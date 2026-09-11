"""Progress view — per-event stage-completion matrix from the manifest gates — AND the single
owner of stage ORDER per event kind (``stage_names``).

Reads the same `is_complete` gates the pipeline uses, so it always reflects real,
resumable state: a ✅ means that stage's artifact exists AND its manifest says
complete (so the pipeline would skip it). Answers "where is every event stuck?".

``main.event_stages`` maps the names returned by ``stage_names`` onto stage functions, so the
pipeline runner, the paper front door, and this matrix all read ONE ordering (complexity
review Reduction 2 — before, ``run_adhoc_paper`` hand-chained a second copy and this matrix a
third, telling a paper its next stage was "transcribe").
"""
from __future__ import annotations

import json
from pathlib import Path

from src import util

WORK_ROOT = Path("work")

# stage name → artifact path relative to the event dir (the manifest gate the stage skips on)
STAGE_ARTIFACT: dict[str, str] = {
    "ingest": f"{util.STAGE_INGEST}/manifest.json",
    "transcribe": f"{util.STAGE_TRANSCRIPT}/transcript.json",
    "visual": f"{util.STAGE_KEYFRAMES}/captions.json",
    "align": f"{util.STAGE_ALIGNED}/aligned.json",
    "synthesize": f"{util.STAGE_BRIEFING}/notes.md",
    "slide_book": f"{util.STAGE_BRIEFING}/slides.pdf",
    "report": "Report/notes.md",
}
_VIDEO_CHAIN = ["ingest", "transcribe", "visual", "align", "synthesize", "slide_book", "report"]
_PAPER_CHAIN = ["ingest", "align", "synthesize", "slide_book", "report"]   # no audio, no frames
_LABEL = {"synthesize": "synth", "slide_book": "slides"}                  # matrix column labels


def stage_names(paper: bool = False) -> list[str]:
    """The ONE stage ordering. ``paper`` events (PDF sources) skip transcribe + visual —
    ``paper_align`` anchors evidence to pages instead. ``enrich`` (opt-in) is inserted by the
    runner after ``synthesize`` and has no matrix column."""
    return list(_PAPER_CHAIN if paper else _VIDEO_CHAIN)


def is_paper_event(event) -> bool:
    """A paper event carries ``meta.paper`` (minted by ``adhoc.build_adhoc_paper_event``)."""
    return bool((getattr(event, "meta", None) or {}).get("paper"))


def _paper_ids(work_root: Path) -> set[str]:
    """Event ids flagged as papers in events.json (absent/unreadable → none)."""
    try:
        raw = json.loads((work_root / "events.json").read_text())
        return {e["event_id"] for e in raw.get("events", [])
                if (e.get("meta") or {}).get("paper")}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def _done(ev_dir: Path, rel: str) -> bool:
    p = ev_dir / rel
    if rel.startswith("Report/"):
        return p.exists()           # report folder has no manifest gate
    return util.is_complete(p)


def first_incomplete(ev_dir: Path, paper: bool = False) -> str | None:
    """Name of the first stage not yet complete for an event, or None if all done."""
    return next((s for s in stage_names(paper) if not _done(ev_dir, STAGE_ARTIFACT[s])), None)


def print_status(work_root: Path = WORK_ROOT, event_id: str | None = None) -> None:
    root = work_root / "events"
    if not root.is_dir():
        print("no work/events/ yet — nothing to report")
        return
    evs = [event_id] if event_id else sorted(d.name for d in root.iterdir() if d.is_dir())
    papers = _paper_ids(work_root)

    labels = [_LABEL.get(s, s) for s in _VIDEO_CHAIN]
    w = max(11, max((len(e) for e in evs), default=11))
    header = f"{'event':<{w}} " + " ".join(f"{l:>10}" for l in labels) + "   next"
    print(header)
    print("-" * len(header))
    done_count = 0
    for ev in evs:
        ev_dir = root / ev
        paper = ev in papers
        chain = set(stage_names(paper))
        cells = [("✅" if _done(ev_dir, STAGE_ARTIFACT[s]) else "·") if s in chain else "—"
                 for s in _VIDEO_CHAIN]
        nxt = first_incomplete(ev_dir, paper)
        done_count += nxt is None
        print(f"{ev:<{w}} " + " ".join(f"{c:>10}" for c in cells) + f"   {nxt or 'DONE'}")
    print("-" * len(header))
    print(f"{done_count}/{len(evs)} events complete   "
          f"(✅ = stage done · · = pending · — = not in this event's chain)")
