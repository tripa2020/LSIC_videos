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
    path: Path
    sha256: str = Field(..., min_length=12, max_length=64)
    lsic_id: int
    date_in_filename: Optional[date] = None


class Event(BaseModel):
    event_id: str
    date: date
    assets: list[Asset]
    duration_sec: Optional[float] = None


class IngestResult(BaseModel):
    event_id: str
    workdir: Path
    audio_path: Optional[Path] = None
    video_path: Optional[Path] = None
    duration_sec: float
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


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
