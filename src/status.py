"""Progress view — per-event stage-completion matrix from the manifest gates.

Reads the same `is_complete` gates the pipeline uses, so it always reflects real,
resumable state: a ✅ means that stage's artifact exists AND its manifest says
complete (so the pipeline would skip it). Answers "where is every event stuck?".
"""
from __future__ import annotations

from pathlib import Path

from src import util

WORK_ROOT = Path("work")

# (column label, artifact path relative to the event dir)
STAGES: list[tuple[str, str]] = [
    ("ingest", f"{util.STAGE_INGEST}/manifest.json"),
    ("transcribe", f"{util.STAGE_TRANSCRIPT}/transcript.json"),
    ("visual", f"{util.STAGE_KEYFRAMES}/captions.json"),
    ("align", f"{util.STAGE_ALIGNED}/aligned.json"),
    ("synth", f"{util.STAGE_BRIEFING}/notes.md"),
    ("slides", f"{util.STAGE_BRIEFING}/slides.pdf"),
    ("report", "Report/notes.md"),
]


def _done(ev_dir: Path, rel: str) -> bool:
    p = ev_dir / rel
    if rel.startswith("Report/"):
        return p.exists()           # report folder has no manifest gate
    return util.is_complete(p)


def first_incomplete(ev_dir: Path) -> str | None:
    """Name of the first stage not yet complete for an event, or None if all done."""
    return next((s for s, rel in STAGES if not _done(ev_dir, rel)), None)


def print_status(work_root: Path = WORK_ROOT, event_id: str | None = None) -> None:
    root = work_root / "events"
    if not root.is_dir():
        print("no work/events/ yet — nothing to report")
        return
    evs = [event_id] if event_id else sorted(d.name for d in root.iterdir() if d.is_dir())

    labels = [s for s, _ in STAGES]
    w = max(11, max((len(e) for e in evs), default=11))
    header = f"{'event':<{w}} " + " ".join(f"{l:>10}" for l in labels) + "   next"
    print(header)
    print("-" * len(header))
    done_count = 0
    for ev in evs:
        ev_dir = root / ev
        cells = ["✅" if _done(ev_dir, rel) else "·" for _, rel in STAGES]
        nxt = first_incomplete(ev_dir)
        done_count += nxt is None
        print(f"{ev:<{w}} " + " ".join(f"{c:>10}" for c in cells) + f"   {nxt or 'DONE'}")
    print("-" * len(header))
    print(f"{done_count}/{len(evs)} events complete   (✅ = stage done · · = pending)")
