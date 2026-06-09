"""Stage 4: sectioning + per-deck fingerprint match + Evidence Object emission.

Inputs (per event workdir):
  01_ingest/manifest.json         IngestResult (duration, video_path)
  01_ingest/decks/<id>/           slide_index.json | doc_index.json (M1)
  02_transcript/transcript.json   list[Segment] (M2)
  03_keyframes/captions.json      list[Caption] (M3, optional)

Outputs (in 04_aligned/):
  aligned.json     AlignmentResult (sections + presentations)
  evidence.json    list[Evidence] — every claimable source unit

Algorithm:
  1. Cut sections from sorted segments on silence gap >2.5s OR 450-word cap.
  2. Attach captions to sections by time range; orphans → nearest midpoint.
  3. Per guest deck: token-overlap fingerprint match against transcript
     windows → assign deck a contiguous [start, end] window.
  4. Emit Evidence objects for every segment (transcript), caption (slide),
     and deck slide (slide). Section.evidence_ids = segment + caption evidence
     within the section's time range. M5 fetches deck-slide evidence via
     presentation overlap separately.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from src import util
from src.contracts import (
    AlignmentResult, Caption, DeckIndex, Evidence, IngestResult,
    Presentation, Section, Segment,
)


WORK_ROOT = Path("work")
GAP_THRESHOLD = 2.5     # silence gap that suggests a topic break
MAX_WORDS = 450         # ~3000 tokens — M5 per-section prompt budget
WINDOW_SEC = 60.0       # transcript window for fingerprint scoring
MIN_DECK_SCORE = 3      # minimum token hits to consider a deck present

_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "have", "will",
    "are", "you", "can", "our", "but", "not", "all", "was", "has", "your",
    "one", "two", "now", "any", "out", "use", "way", "may", "his", "her",
    "they", "them", "their", "into", "more", "what", "when", "which",
    "would", "could", "about", "also", "been", "than", "then", "some",
    "very", "well", "just", "like", "make", "many", "much", "such", "even",
    "only", "over", "back", "first", "after", "before", "where", "these",
    "those", "should", "really", "actually", "going", "things", "thing",
}

_WORD_RE = re.compile(r"\b[a-z][a-z0-9\-]{4,}\b")


def align(event_id: str, work_root: Path = WORK_ROOT) -> AlignmentResult:
    workdir = work_root / "events" / event_id
    aligned_dir = workdir / util.STAGE_ALIGNED
    aligned_dir.mkdir(parents=True, exist_ok=True)
    aligned_path = aligned_dir / "aligned.json"
    if util.is_complete(aligned_path):
        return AlignmentResult.model_validate_json(aligned_path.read_text())

    ing = IngestResult.model_validate_json(
        (workdir / util.STAGE_INGEST / "manifest.json").read_text())
    segments = _load_segments(workdir)
    captions = _load_captions(workdir)
    decks = _load_decks(workdir)

    sections = _cut_sections(segments)
    _attach_keyframes(sections, captions)
    presentations = _match_presentations(decks, segments)
    # YouTube events have no decks to fingerprint — seed presentation windows
    # from the catalog `?t=` offsets recorded in meta.json (mapped onto the
    # event timeline via each video's offset). Deck-backed events seed nothing.
    presentations += _seed_presentations_from_meta(workdir, ing)
    presentations.sort(key=lambda p: p.start)

    evidence_list = _emit_evidence(segments, captions, decks, presentations)
    _attach_evidence_ids(sections, evidence_list)

    result = AlignmentResult(
        event_id=event_id, duration_sec=ing.duration_sec,
        sections=sections, presentations=presentations,
    )
    util.write_with_manifest(
        aligned_path, result.model_dump_json(indent=2), stage="align")
    util.write_with_manifest(
        aligned_dir / "evidence.json",
        json.dumps([e.model_dump(mode="json") for e in evidence_list], indent=2),
        stage="align",
    )
    print(f"  [align] {len(sections)} sections · {len(presentations)} presentations · "
          f"{len(evidence_list)} evidence objects", flush=True)
    return result


# --- loaders ---

def _load_segments(workdir: Path) -> list[Segment]:
    p = workdir / util.STAGE_TRANSCRIPT / "transcript.json"
    return [Segment.model_validate(s) for s in json.loads(p.read_text())]


def _load_captions(workdir: Path) -> list[Caption]:
    p = workdir / util.STAGE_KEYFRAMES / "captions.json"
    if not p.exists():
        return []
    return [Caption.model_validate(c) for c in json.loads(p.read_text())]


def _load_decks(workdir: Path) -> list[tuple[str, DeckIndex]]:
    """Return [(asset_id, DeckIndex), ...] for every guest presentation deck."""
    decks: list[tuple[str, DeckIndex]] = []
    decks_dir = workdir / util.STAGE_INGEST / "decks"
    if not decks_dir.is_dir():
        return decks
    for d in sorted(decks_dir.iterdir()):
        if not d.is_dir():
            continue
        idx_path = d / "slide_index.json"
        if not idx_path.exists():
            idx_path = d / "doc_index.json"
        if not idx_path.exists():
            continue
        decks.append((d.name, DeckIndex.model_validate_json(idx_path.read_text())))
    return decks


# --- sectioning + keyframe attach ---

def _cut_sections(segments: list[Segment]) -> list[Section]:
    s = sorted(segments, key=lambda x: x.start)
    sections: list[Section] = []
    current: list[Segment] = []
    word_count = 0
    for seg in s:
        if current and (
            seg.start - current[-1].end > GAP_THRESHOLD
            or word_count >= MAX_WORDS
        ):
            sections.append(_build_section(current))
            current, word_count = [], 0
        current.append(seg)
        word_count += len(seg.text.split())
    if current:
        sections.append(_build_section(current))
    return sections


def _build_section(segs: list[Segment]) -> Section:
    return Section(
        start=segs[0].start, end=segs[-1].end,
        transcript=" ".join(s.text for s in segs),
        speakers=sorted({s.speaker_id for s in segs if s.speaker_id}),
        languages=sorted({s.language for s in segs if s.language}),
    )


def _attach_keyframes(sections: list[Section], captions: list[Caption]) -> None:
    if not captions or not sections:
        return
    assigned: set[float] = set()
    for c in captions:
        for sec in sections:
            if sec.start <= c.t <= sec.end:
                sec.keyframes.append(c)
                assigned.add(c.t)
                break
    # orphans → nearest section by midpoint
    for c in captions:
        if c.t in assigned:
            continue
        nearest = min(sections,
                      key=lambda s: abs(c.t - (s.start + s.end) / 2))
        nearest.keyframes.append(c)


# --- per-deck fingerprint match ---

def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if t not in _STOPWORDS}


def _match_presentations(decks: list[tuple[str, DeckIndex]],
                         segments: list[Segment]) -> list[Presentation]:
    """Token-overlap fingerprint: window-score each deck, pick best contiguous window."""
    if not decks or not segments:
        return []

    presentations: list[Presentation] = []
    used_windows: list[tuple[float, float]] = []

    for asset_id, deck in decks:
        deck_text = " ".join(s.text + " " + s.speaker_notes for s in deck.slides)
        deck_toks = _tokens(deck_text)
        if not deck_toks:
            continue

        # score each segment by # of distinct deck tokens it contains
        seg_scores = [
            (seg.start, seg.end, len(_tokens(seg.text) & deck_toks))
            for seg in segments
        ]
        # smooth by summing scores in a WINDOW_SEC sliding window
        best_start, best_end, best_score = 0.0, 0.0, 0
        for i, (s_start, _, _) in enumerate(seg_scores):
            window_end = s_start + WINDOW_SEC
            j = i
            score = 0
            while j < len(seg_scores) and seg_scores[j][0] <= window_end:
                # avoid claiming a window already taken by another deck
                if not _overlaps(seg_scores[j][0], seg_scores[j][1], used_windows):
                    score += seg_scores[j][2]
                j += 1
            if score > best_score:
                best_score = score
                best_start = s_start
                best_end = seg_scores[min(j - 1, len(seg_scores) - 1)][1]
        if best_score < MIN_DECK_SCORE:
            continue
        # extend forward while score stays positive
        end = best_end
        for s_start, s_end, sc in seg_scores:
            if s_start > best_end and s_start < best_end + WINDOW_SEC and sc > 0:
                end = max(end, s_end)
        used_windows.append((best_start, end))
        presentations.append(Presentation(
            asset_id=asset_id, title=deck.title or asset_id,
            start=best_start, end=end,
            slides_count=len(deck.slides),
            match_score=float(best_score),
        ))

    presentations.sort(key=lambda p: p.start)
    return presentations


def _seed_presentations_from_meta(workdir: Path, ing: IngestResult) -> list[Presentation]:
    """Build presentations from YouTube `?t=` windows (meta.json) for deck-less
    events. Each window's video-local times are lifted onto the event timeline
    by that video's offset_sec; the last window of a video runs to video end."""
    meta_path = workdir / "meta.json"
    if not meta_path.exists():
        return []
    meta = json.loads(meta_path.read_text())
    parts = {p.key: p for p in ing.video_parts}
    seeded: list[Presentation] = []
    for a in meta.get("assets", []):
        windows = a.get("presentations")
        vid = a.get("yt_video_id")
        if not windows or not vid:
            continue
        part = parts.get(str(vid))
        if part is None:
            continue  # video didn't ingest (dead/skipped) — drop its orphaned windows
        off = part.offset_sec
        vdur = part.duration_sec
        for w in windows:
            start = float(w.get("t_start") or 0) + off
            end = (float(w["t_end"]) + off) if w.get("t_end") is not None else off + vdur
            seeded.append(Presentation(
                asset_id=f"yt_{vid}_{w.get('row_id')}",
                title=(w.get("title") or f"yt_{vid}")[:120],
                start=start, end=max(end, start + 1.0),
                slides_count=0, match_score=1.0,
            ))
    return seeded


def _overlaps(s: float, e: float, used: list[tuple[float, float]]) -> bool:
    for us, ue in used:
        if not (e < us or s > ue):
            return True
    return False


# --- evidence emission ---

def _evidence_id(kind: str, source_id: str, start: float) -> str:
    h = hashlib.sha256(f"{kind}|{source_id}|{start:.3f}".encode()).hexdigest()[:12]
    return f"ev_{h}"


def _emit_evidence(segments: list[Segment], captions: list[Caption],
                   decks: list[tuple[str, DeckIndex]],
                   presentations: list[Presentation]) -> list[Evidence]:
    out: list[Evidence] = []
    for i, seg in enumerate(segments):
        sid = f"segment_{i:04d}"
        out.append(Evidence(
            evidence_id=_evidence_id("transcript", sid, seg.start),
            kind="transcript", source_id=sid,
            timestamp_start=seg.start, timestamp_end=seg.end,
            speaker_id=seg.speaker_id, text=seg.text,
            confidence=1.0,
        ))
    for i, cap in enumerate(captions):
        sid = f"caption_{i:04d}"
        out.append(Evidence(
            evidence_id=_evidence_id("slide", sid, cap.t),
            kind="slide", source_id=sid,
            timestamp_start=cap.t, timestamp_end=cap.t,
            source_asset=str(cap.frame_path),
            text=(cap.visible_text + "\n" + cap.description).strip(),
            confidence=1.0 if cap.caption_status == "ok" else 0.3,
            tags=["has_equation"] * bool(cap.has_equation)
                 + ["has_diagram"] * bool(cap.has_diagram),
        ))
    # deck slides — timestamp = matched presentation window, or 0 if unmatched
    pres_by_asset = {p.asset_id: p for p in presentations}
    for asset_id, deck in decks:
        p = pres_by_asset.get(asset_id)
        t_start = p.start if p else 0.0
        t_end = p.end if p else 0.0
        for slide in deck.slides:
            sid = f"asset_{asset_id}_slide_{slide.n:03d}"
            text = (slide.text + "\n" + slide.speaker_notes).strip()
            if not text:
                continue
            out.append(Evidence(
                evidence_id=_evidence_id("slide", sid, t_start),
                kind="slide", source_id=sid,
                timestamp_start=t_start, timestamp_end=t_end,
                source_asset=f"asset_{asset_id}",
                text=text, confidence=1.0,
                tags=["deck"],
            ))
    return out


def _attach_evidence_ids(sections: list[Section], evidence: list[Evidence]) -> None:
    """Each section claims transcript + caption evidence within its time range."""
    in_window = {e.evidence_id: e for e in evidence
                 if e.kind in ("transcript", "slide") and "deck" not in e.tags}
    for sec in sections:
        sec.evidence_ids = [
            eid for eid, e in in_window.items()
            if sec.start <= e.timestamp_start <= sec.end
        ]
