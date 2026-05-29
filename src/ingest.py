"""Stage 1: per-asset ingest dispatch.

Video → 16 kHz mono WAV via ffmpeg + container metadata via ffprobe.
PPTX → text + notes + per-slide PNG via pptx_handler.
PDF  → text + per-page PNG via pdf_handler.
Notes-only event: PDF text extract only, no audio.

Idempotent: each event/paper writes a manifest.json that short-circuits reruns.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from src import pdf_handler, pptx_handler
from src.contracts import Asset, Event, IngestResult


WORK_ROOT = Path("work")


def ingest_event(event: Event, work_root: Path = WORK_ROOT) -> IngestResult:
    workdir = work_root / "events" / event.event_id
    workdir.mkdir(parents=True, exist_ok=True)
    manifest = workdir / "manifest.json"
    if manifest.exists():
        return IngestResult.model_validate_json(manifest.read_text())

    audio_path: Optional[Path] = None
    duration: float = 0.0
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    video_path: Optional[Path] = None

    for asset in event.assets:
        if asset.kind == "video":
            audio_path = workdir / "audio.wav"
            video_path = asset.path
            _ffmpeg_extract_wav(asset.path, audio_path)
            duration, fps, width, height = _ffprobe(asset.path)
        elif asset.kind in ("host_deck", "presentation"):
            handler = pptx_handler if asset.path.suffix.lower() == ".pptx" else pdf_handler
            handler.extract(asset.path, workdir / "decks" / str(asset.lsic_id))
        elif asset.kind == "notes":
            pdf_handler.extract(asset.path, workdir / "notes" / str(asset.lsic_id))
        elif asset.kind == "paper":
            pdf_handler.extract(asset.path, workdir / "papers" / str(asset.lsic_id))

    result = IngestResult(
        event_id=event.event_id,
        workdir=workdir,
        audio_path=audio_path,
        video_path=video_path,
        duration_sec=duration,
        fps=fps,
        width=width,
        height=height,
    )
    manifest.write_text(result.model_dump_json(indent=2))
    return result


def ingest_paper(asset: Asset, work_root: Path = WORK_ROOT) -> Path:
    out_dir = work_root / "papers" / str(asset.lsic_id)
    pdf_handler.extract(asset.path, out_dir)
    return out_dir


def _ffmpeg_extract_wav(src: Path, target: Path) -> None:
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src),
         "-ac", "1", "-ar", "16000", "-vn", str(target)],
        check=True, capture_output=True,
    )


def _ffprobe(path: Path) -> tuple[float, Optional[float], Optional[int], Optional[int]]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, text=True,
    )
    info = json.loads(out.stdout)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    duration = float(info["format"]["duration"])
    if v is None:
        return duration, None, None, None
    fps = None
    try:
        num, den = v["r_frame_rate"].split("/")
        fps = float(num) / float(den) if float(den) else None
    except (KeyError, ValueError, ZeroDivisionError):
        pass
    return duration, fps, int(v.get("width", 0)) or None, int(v.get("height", 0)) or None


def load_events_json(work_root: Path = WORK_ROOT) -> tuple[list[Event], list[Asset]]:
    """Read events.json (produced by discover.py) into typed objects."""
    raw = json.loads((work_root / "events.json").read_text())
    events = [Event.model_validate(e) for e in raw["events"]]
    papers = [Asset.model_validate(p) for p in raw["papers"]]
    return events, papers


def ingest_one_event(event_id: str, work_root: Path = WORK_ROOT) -> IngestResult:
    events, _ = load_events_json(work_root)
    target = next((e for e in events if e.event_id == event_id), None)
    if target is None:
        raise KeyError(
            f"event_id '{event_id}' not in events.json — "
            f"known: {sorted(e.event_id for e in events)}"
        )
    return ingest_event(target, work_root)


def ingest_all(work_root: Path = WORK_ROOT) -> dict:
    events, papers = load_events_json(work_root)
    event_results = [ingest_event(e, work_root) for e in events]
    paper_dirs = [ingest_paper(p, work_root) for p in papers]
    return {"events": len(event_results), "papers": len(paper_dirs)}
