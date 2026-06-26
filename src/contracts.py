"""Pydantic contracts — typed seams between pipeline stages.

If you're adding a field, this file is the only place that needs to change for
downstream stages to pick it up. Keep these models in lockstep with
golden/2026-03-26_event_mockup.md — every section there maps to a model here.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


AssetKind = Literal["video", "host_deck", "presentation", "paper", "notes"]
ConfidenceFlag = Literal["claimed", "inferred"]
CustomerStatus = Literal["Active funding", "Active PO", "Open RFP/RFI", "Aspirational"]
ChokepointStage = Literal["Research", "Development", "Funding", "Implementation"]


class Asset(BaseModel):
    kind: AssetKind
    path: Optional[Path] = None            # None for URL-backed video until fetched
    sha256: Optional[str] = Field(default=None, min_length=12, max_length=64)
    lsic_id: Optional[int] = None          # None for YouTube (no file-id on the site)
    date_in_filename: Optional[date] = None
    source_url: Optional[str] = None       # YouTube/Zoom URL; ingest fetches → path
    meta: Optional[dict] = None            # catalog truth: speaker, title, topics, t= windows


class Event(BaseModel):
    event_id: str
    date: date
    assets: list[Asset]
    duration_sec: Optional[float] = None
    meta: Optional[dict] = None            # event-level catalog truth (name, topics, speakers)


class VideoPart(BaseModel):
    """One video within an event. Events can have N videos (Zoom split recordings,
    Bi-Annual sessions). Parts are concatenated onto one event timeline via offset_sec."""
    key: str                               # stable id: lsic_id or yt_video_id
    path: Optional[Path] = None            # local file (after fetch)
    source_url: Optional[str] = None       # Zoom/YouTube URL
    duration_sec: float
    offset_sec: float = 0.0                # cumulative start on the event timeline
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


class IngestResult(BaseModel):
    event_id: str
    workdir: Path
    audio_path: Optional[Path] = None      # concatenated audio across all parts
    video_path: Optional[Path] = None      # first part (back-compat / single-video)
    duration_sec: float                    # total across all parts
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    video_parts: list[VideoPart] = []      # NEW — empty for legacy single-video events


class Segment(BaseModel):
    start: float
    end: float
    text: str
    speaker_id: Optional[str] = None
    language: Optional[str] = None


class Caption(BaseModel):
    t: float
    frame_path: Path
    visible_text: str = ""
    description: str = ""
    has_equation: bool = False
    has_diagram: bool = False
    trigger: Optional[Literal["scene", "safety", "text-delta", "audio-cue"]] = None
    caption_status: str = "ok"   # "ok" | "failed: <ExceptionType>"


class Slide(BaseModel):
    n: int
    text: str = ""
    speaker_notes: str = ""
    png_path: Optional[Path] = None


class DeckIndex(BaseModel):
    asset_id: str
    title: Optional[str] = None
    slides: list[Slide]


class Presentation(BaseModel):
    asset_id: str
    title: str
    start: float
    end: float
    slides_count: int
    match_score: float


class Section(BaseModel):
    start: float
    end: float
    transcript: str
    keyframes: list[Caption] = []
    speakers: list[str] = []
    languages: list[str] = []
    evidence_ids: list[str] = []   # refs into evidence.json (M4)


class AlignmentResult(BaseModel):
    """M4 output: sections + presentations + duration sanity."""
    event_id: str
    duration_sec: float
    sections: list["Section"]
    presentations: list["Presentation"]


class TRLRow(BaseModel):
    technology: str
    trl: str
    basis: str
    confidence: ConfidenceFlag
    source_timestamp: str


class ExpertLens(BaseModel):
    role: str
    emoji: str
    take: str
    source_timestamp: Optional[str] = None


class FundingRow(BaseModel):
    org: str
    mechanism: str
    scale: str
    focus: str
    source_timestamp: str


class CustomerRow(BaseModel):
    customer: str
    mechanism: str
    status: CustomerStatus
    horizon: str
    source: str


class ChokepointRow(BaseModel):
    stage: ChokepointStage
    chokepoint: str
    source_timestamp: str


class PerQuestionBlock(BaseModel):
    question: str
    source_timestamp: str
    role_takes: list[ExpertLens]


class SlideHighlight(BaseModel):
    image_path: Path
    caption: str
    source_timestamp: str


class CuratedSlide(BaseModel):
    """One slide from a deck, VLM-curated for the M5.5 slide_book."""
    asset_id: str
    slide_n: int
    png_path: Path
    is_informative: bool
    topic: str = ""
    commentary: str = ""
    contains_equation: bool = False
    kind: Literal["graph", "diagram", "model", "image", "table",
                  "equation", "text-only"] = "text-only"
    # normalized (0-1) bounding box of informative region for PDF cropping
    bbox: Optional[dict[str, float]] = None


class Evidence(BaseModel):
    """Universal claim primitive. Emitted at M4; consumed at M5 for citation grounding."""
    evidence_id: str
    kind: Literal["transcript", "slide", "asset", "metadata"]
    source_id: str
    timestamp_start: float
    timestamp_end: float
    speaker_id: Optional[str] = None
    source_asset: Optional[str] = None
    text: str
    confidence: float = 0.0
    tags: list[str] = []


class ValidationIssue(BaseModel):
    """One failed check from a validator. Section/offending/suggestion are optional."""
    section: Optional[str] = None
    rule: str
    offending: Optional[str] = None
    suggestion: Optional[str] = None


class ValidationResult(BaseModel):
    passed: bool
    issues: list[ValidationIssue] = []


class Briefing(BaseModel):
    """The complete event briefing — data behind the markdown writer."""

    event_id: str
    date: date
    title: str
    duration: str
    speakers_detected: int
    languages: list[str]

    bottom_line: str
    expert_lenses_top: list[ExpertLens]
    presentations: list[Presentation]
    whats_being_done: list[str]
    whats_being_done_lenses: list[ExpertLens]
    eng_questions: list[str]
    eng_questions_lenses: list[ExpertLens]
    per_question_analysis: list[PerQuestionBlock]
    constraints: list[str]
    funding_rows: list[FundingRow]
    funding_lenses: list[ExpertLens]
    customer_intro: str
    customer_rows: list[CustomerRow]
    chokepoint_rows: list[ChokepointRow]
    trl_rows: list[TRLRow]
    equations: Optional[list[str]] = None
    speakers: list[str]
    citations: list[str]
    slide_highlights: list[SlideHighlight]


# --- DEPTH v2: cognition layer (the dedicated cognition-call output schema) ---

class OperatingAlgorithm(BaseModel):
    """The speaker's idiosyncratic, transferable reasoning signature as one arrow-chain."""
    arrow_chain: str = ""
    tags: list[str] = Field(default_factory=list)


class CognitiveMove(BaseModel):
    """One repeatable mental move, tagged by OPERATION (not topic) + the work it does."""
    move: str = ""
    tag: str = ""
    work: str = ""
    evidence_id: str = ""


class ClaimEpistemic(BaseModel):
    """Epistemic overlay for a descriptive notable_claim, matched by ``evidence_id``. The claims
    themselves stay in the descriptive call; the cognition call only adds the judgement so claims
    survive a cognition failure (matched on evidence_id, un-matched claims simply render untagged)."""
    evidence_id: str = ""
    status: str = ""           # consensus | his bet | contested | his frame
    when_it_fails: str = ""     # boundary condition where the play backfires (+ who lost running it)


class TransferQuestion(BaseModel):
    """A reusable self-question derived from a cognitive move, for the reader's domain."""
    prompt: str = ""
    from_move: str = ""
    evidence_id: str = ""


class CognitionOutput(BaseModel):
    """The dedicated-cognition-call result (merged into the lecture thematic dict before render)."""
    operating_algorithm: OperatingAlgorithm = Field(default_factory=OperatingAlgorithm)
    cognitive_moves: list[CognitiveMove] = Field(default_factory=list)
    claim_epistemics: list[ClaimEpistemic] = Field(default_factory=list)
    what_doesnt_transfer: str = ""
    transfer_questions: list[TransferQuestion] = Field(default_factory=list)
