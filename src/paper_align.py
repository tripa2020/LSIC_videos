"""Paper alignment — pages → Sections + Evidence, the paper twin of ``align.py``.

A paper has no audio timeline, but every downstream consumer (segment windowing,
``synthesize._build_event_context`` bucketing, the eval decile math) is purely numeric over
``Evidence.timestamp_start`` — so the PAGE NUMBER rides the existing float field and nothing
downstream changes. The paper profile's render turns it back into a human ``[p.N]`` citation,
and ``synth_eval``'s page mode reads the same unit. ``duration_sec`` carries the page count.

Same stage contract as align: reads the ingest artifact (``01_ingest/decks/*/doc_index.json``,
written by ``pdf_handler.extract``), writes ``04_aligned/aligned.json`` + ``evidence.json``
with manifests, and skips when already complete (idempotent / crash-resumable).
"""
from __future__ import annotations

import json
from pathlib import Path

from src import util
from src.contracts import AlignmentResult, DeckIndex, Evidence, Section

WORK_ROOT = Path("work")


def align_paper(event_id: str, work_root: Path = WORK_ROOT) -> AlignmentResult:
    workdir = work_root / "events" / event_id
    aligned_dir = workdir / util.STAGE_ALIGNED
    aligned_dir.mkdir(parents=True, exist_ok=True)
    aligned_path = aligned_dir / "aligned.json"
    if util.is_complete(aligned_path):
        return AlignmentResult.model_validate_json(aligned_path.read_text())

    decks_dir = workdir / util.STAGE_INGEST / "decks"
    idx_files = sorted(decks_dir.glob("*/doc_index.json")) + \
        sorted(decks_dir.glob("*/slide_index.json"))
    if not idx_files:
        raise RuntimeError(f"{event_id}: no doc_index.json under {decks_dir} — run --ingest first")
    deck = DeckIndex.model_validate_json(idx_files[0].read_text())

    # One Section + one transcript-kind Evidence per non-empty page. kind="transcript" (not
    # "slide") because the page text IS the primary source here — it's what the descriptive
    # context, the MAPRED windows, and the verbatim-quote check all read.
    sections: list[Section] = []
    evidence: list[Evidence] = []
    for page in deck.slides:
        text = (page.text or "").strip()
        if not text:                       # figure-only page: nothing citable to ground on
            continue
        eid = f"ev_p{page.n:03d}"
        evidence.append(Evidence(
            evidence_id=eid, kind="transcript", source_id=deck.asset_id,
            timestamp_start=float(page.n), timestamp_end=float(page.n),
            text=text, confidence=1.0, tags=["page"]))
        sections.append(Section(start=float(page.n), end=float(page.n),
                                transcript=text, evidence_ids=[eid]))

    if not evidence:
        raise RuntimeError(f"{event_id}: no extractable text on any page (scanned PDF?)")

    result = AlignmentResult(event_id=event_id, duration_sec=float(len(deck.slides)),
                             sections=sections, presentations=[])
    util.write_with_manifest(aligned_path, result.model_dump_json(indent=2), stage="align")
    util.write_with_manifest(
        aligned_dir / "evidence.json",
        json.dumps([e.model_dump(mode="json") for e in evidence], indent=2),
        stage="align",
    )
    print(f"  [paper_align] {len(sections)} pages with text · "
          f"{len(deck.slides)} pages total", flush=True)
    return result
