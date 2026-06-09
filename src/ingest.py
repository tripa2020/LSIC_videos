"""Stage 1: per-asset ingest dispatch.

Video(s) → 16 kHz mono WAV via ffmpeg + container metadata via ffprobe.
Events may have N videos (Zoom split recordings, Bi-Annual sessions): each is a
VideoPart with a cumulative offset; their audio is concatenated into one
audio.wav so transcribe/align/synthesize see a single event timeline.
URL-backed videos (source_url, no path) are fetched first: yt-dlp for YouTube,
curl for Zoom.

PPTX → text + notes + per-slide PNG. PDF → text + per-page PNG.
Idempotent: each event/paper writes a manifest.json that short-circuits reruns.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Optional

from src import pdf_handler, pptx_handler, util
from src.contracts import Asset, Event, IngestResult, VideoPart


WORK_ROOT = Path("work")


def _video_key(asset: Asset) -> str:
    if asset.lsic_id is not None:
        return str(asset.lsic_id)
    if asset.meta and asset.meta.get("yt_video_id"):
        return str(asset.meta["yt_video_id"])
    return util.slugify(asset.source_url or asset.kind)[:24]


def _video_sort_key(asset: Asset) -> tuple:
    order = (asset.meta or {}).get("order", 0)
    return (order, asset.lsic_id if asset.lsic_id is not None else 1 << 30, _video_key(asset))


def ingest_event(event: Event, work_root: Path = WORK_ROOT) -> IngestResult:
    workdir = work_root / "events" / event.event_id
    ingest_dir = workdir / util.STAGE_INGEST
    ingest_dir.mkdir(parents=True, exist_ok=True)
    manifest = ingest_dir / "manifest.json"
    if util.is_complete(manifest):
        return IngestResult.model_validate_json(manifest.read_text())

    videos = sorted([a for a in event.assets if a.kind == "video"], key=_video_sort_key)
    parts: list[VideoPart] = []
    part_wavs: list[Path] = []
    offset = 0.0
    for asset in videos:
        key = _video_key(asset)
        try:
            local = _resolve_video(asset, ingest_dir / "videos" / f"{key}.mp4")
            part_wav = ingest_dir / "audio_parts" / f"{key}.wav"
            _ffmpeg_extract_wav(local, part_wav)
            dur, fps, w, h = _ffprobe(local)
        except Exception as e:
            # Dead/unavailable video (deleted, private, geo-blocked). Skip it
            # rather than crash the event; align drops its orphaned t= windows.
            print(f"  [ingest] SKIP video {key}: {type(e).__name__}: {str(e)[:120]}", flush=True)
            continue
        parts.append(VideoPart(key=key, path=local, source_url=asset.source_url,
                               duration_sec=dur, offset_sec=offset, fps=fps, width=w, height=h))
        part_wavs.append(part_wav)
        offset += dur

    if videos and not parts:
        # every video failed to fetch — don't cache a bogus no-audio manifest
        raise RuntimeError(
            f"{event.event_id}: all {len(videos)} videos failed to ingest "
            f"(check yt-dlp / network); not writing manifest")

    audio_path: Optional[Path] = None
    if part_wavs:
        audio_path = ingest_dir / "audio.wav"
        _concat_wavs(part_wavs, audio_path)

    # non-video assets
    for asset in event.assets:
        if asset.kind in ("host_deck", "presentation"):
            handler = pptx_handler if str(asset.path).lower().endswith(".pptx") else pdf_handler
            handler.extract(asset.path, ingest_dir / "decks" / str(asset.lsic_id))
        elif asset.kind == "notes":
            pdf_handler.extract(asset.path, ingest_dir / "notes" / str(asset.lsic_id))
        elif asset.kind == "paper":
            pdf_handler.extract(asset.path, ingest_dir / "papers" / str(asset.lsic_id))

    first = parts[0] if parts else None
    result = IngestResult(
        event_id=event.event_id,
        workdir=workdir,
        audio_path=audio_path,
        video_path=(first.path if first else None),
        duration_sec=offset,
        fps=(first.fps if first else None),
        width=(first.width if first else None),
        height=(first.height if first else None),
        video_parts=parts,
    )
    util.write_with_manifest(manifest, result.model_dump_json(indent=2), stage="ingest")
    return result


def _resolve_video(asset: Asset, dest: Path) -> Path:
    """Return a local path to the video, fetching from source_url if needed."""
    if asset.path and Path(asset.path).exists():
        return Path(asset.path)
    if dest.exists():
        return dest
    if not asset.source_url:
        raise FileNotFoundError(f"video asset has neither path nor source_url: {asset!r}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = asset.source_url
    if "youtu.be" in url or "youtube.com" in url:
        _fetch_youtube(url, dest)
    else:
        _fetch_http(url, dest)
    if not dest.exists():
        raise RuntimeError(f"fetch produced no file for {url}")
    return dest


def _fetch_youtube(url: str, dest: Path) -> None:
    # strip ?t= so we always pull the whole recording (presentations are windows)
    clean = url.split("&")[0].split("?t=")[0]
    # 480p: ASR audio is unaffected, keyframes stay legible, downloads ~6x smaller.
    # yt-dlp resumes its own .part and retries fragments on flaky networks.
    subprocess.run(
        [sys.executable, "-m", "yt_dlp",
         "-f", "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
         "--merge-output-format", "mp4", "--retries", "10", "--fragment-retries", "20",
         "-o", str(dest), clean],
        check=True, capture_output=True,
    )


def _fetch_http(url: str, dest: Path) -> None:
    """Resumable, atomic download: -C - resumes the .part on retry (exit 56 =
    dropped connection mid-stream); rename to final only on full success."""
    enc = urllib.parse.quote(url, safe=":/?&=%")
    part = dest.with_suffix(dest.suffix + ".part")
    subprocess.run(
        ["curl", "-sS", "-L", "--fail", "-C", "-",
         "--retry", "8", "--retry-delay", "3", "--retry-all-errors",
         "--max-time", "3600", "-o", str(part), enc],
        check=True,
    )
    part.replace(dest)


def _concat_wavs(wavs: list[Path], out: Path) -> None:
    if out.exists():
        return
    if len(wavs) == 1:
        _ffmpeg_extract_wav(wavs[0], out)  # re-encode-copy single part
        return
    listfile = out.parent / "concat_list.txt"
    listfile.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
         "-c", "copy", str(out)],
        check=True, capture_output=True,
    )


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
    """Read events.json (produced by discover.py or group_manifest.py) into typed objects."""
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


def load_ingest_result(event_id: str, work_root: Path = WORK_ROOT) -> IngestResult:
    """Read a previously-written IngestResult from its stage subfolder."""
    path = work_root / "events" / event_id / util.STAGE_INGEST / "manifest.json"
    return IngestResult.model_validate_json(path.read_text())


def ingest_all(work_root: Path = WORK_ROOT) -> dict:
    events, papers = load_events_json(work_root)
    event_results = [ingest_event(e, work_root) for e in events]
    paper_dirs = [ingest_paper(p, work_root) for p in papers]
    return {"events": len(event_results), "papers": len(paper_dirs)}
