"""Final stage: assemble the reader-facing Report/ folder for an event.

Copies the deliverables (notes.md, slides.pdf, slide_captions.md, equations.md)
from the 05_briefing/ staging folder into work/events/<event_id>/Report/ — a
clean, self-contained deliverable folder (no manifests, no intermediate
artifacts). Copy (not move): the staged 05_briefing artifacts stay put so stage
caching/resume keeps working. A deliverable absent in 05_briefing is reported as
missing, never fatal (degrade-to-today).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from src import util

WORK_ROOT = Path("work")
# equations.md promoted into Report/ per the cloud-batch output contract ("Report + equations").
REPORT_FILES = ["notes.md", "slides.pdf", "slide_captions.md", "equations.md"]


def assemble_report(event_id: str, work_root: Path = WORK_ROOT) -> Path:
    src_dir = work_root / "events" / event_id / util.STAGE_BRIEFING
    dst_dir = work_root / "events" / event_id / "Report"
    dst_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []
    for name in REPORT_FILES:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, dst_dir / name)  # refreshes on rerun; preserves mtime
            copied.append(name)
        else:
            missing.append(name)

    msg = f"  [report] {event_id}: copied {copied} → {dst_dir}"
    if missing:
        msg += f"  (missing in 05_briefing: {missing})"
    print(msg, flush=True)
    return dst_dir
