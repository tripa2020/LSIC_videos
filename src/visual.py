"""Stage 3: video keyframe extraction + Gemini VLM captioning.

Hybrid sampling triggers (any-of):
- Scene change       (pyscenedetect, threshold 27.0)
- 60-second safety   (avoid missing long static segments)
- Audio cue          (transcript contains "this equation/diagram/figure", etc.)
- Slide-text delta   (deferred to M3.1 — needs second VLM pass)

All kept frames phash-deduped at Hamming ≤ 4, downscaled to 1024 px,
captioned by Gemini VLM. Per-frame cache so kill mid-loop doesn't lose work.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Optional, Protocol

import cv2
import imagehash
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
from scenedetect import detect, ContentDetector

from src import util
from src.contracts import Caption, IngestResult, Segment, VideoPart


WORK_ROOT = Path("work")
GEMINI_MODEL = "gemini-2.5-flash"
SCENE_THRESHOLD = 27.0
SAFETY_NET_SEC = 60.0
PHASH_HAMMING_MAX = 4
DOWNSCALE_MAX = 1024
JPEG_QUALITY = 85

AUDIO_CUE_PATTERNS = [
    re.compile(r"\b(this|the|that) (equation|diagram|figure|chart|graph|slide|plot|image)\b", re.I),
    re.compile(r"\bas (you can see|shown|depicted|illustrated)\b", re.I),
    re.compile(r"\blook at (this|the|here)\b", re.I),
    re.compile(r"\bin (this|the) (slide|figure|diagram|chart|graph)\b", re.I),
]

VLM_PROMPT = """Look at this frame from a meeting recording.

Return ONLY a JSON object (no prose, no markdown fences) with these fields:
{
  "visible_text": "<all readable text in the frame, verbatim; empty if none>",
  "description": "<one or two sentences describing what's shown>",
  "has_equation": <true|false>,
  "has_diagram": <true|false>
}

If the frame is clearly a slide, prioritize verbatim text capture."""


def _transient(e: Exception) -> bool:
    """Retryable Gemini/network/DNS errors — delegates to the shared classifier."""
    return util.is_transient(e)


class Describer(Protocol):
    def caption(self, image_path: Path) -> dict: ...


class GeminiDescriber:
    def __init__(self, model: str = GEMINI_MODEL):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set in .env")
        self.client = genai.Client(api_key=api_key,
                                   http_options=types.HttpOptions(timeout=90_000))
        self.model = model

    def caption(self, image_path: Path) -> dict:
        img_bytes = image_path.read_bytes()
        last: Exception | None = None
        for attempt in range(4):
            try:
                resp = self.client.models.generate_content(
                    model=self.model,
                    contents=[
                        VLM_PROMPT,
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                return json.loads(util.strip_fences(resp.text or ""))
            except Exception as e:  # transient overload → backoff + retry
                last = e
                if _transient(e) and attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        raise last  # unreachable


def _kept_frames(ing: IngestResult, workdir: Path,
                 keyframes_dir: Path) -> list[tuple[float, Path, str]]:
    """Select + phash-dedup keyframes across the event's video parts on one timeline.

    Single source of frame selection: ``extract_visual`` (sync) and ``batch_prefill_captions``
    (batch) both call it, so both caption the exact same frames into the same cache files."""
    parts = ing.video_parts or [VideoPart(
        key="0", path=ing.video_path, duration_sec=ing.duration_sec, offset_sec=0.0)]

    segments: list[Segment] = []
    transcript_path = workdir / util.STAGE_TRANSCRIPT / "transcript.json"
    if transcript_path.exists():
        segments = [Segment.model_validate(s) for s in json.loads(transcript_path.read_text())]

    # extract per video in part-local time, then lift onto the event timeline (+offset).
    # phash set is shared across parts so a slide repeated across videos dedups once.
    kept: list[tuple[float, Path, str]] = []
    seen_hashes: list[imagehash.ImageHash] = []
    for part in parts:
        local_segs = [s.model_copy(update={"start": s.start - part.offset_sec,
                                           "end": s.end - part.offset_sec})
                      for s in segments
                      if part.offset_sec <= s.start < part.offset_sec + part.duration_sec]
        cand = _collect_candidates(Path(part.path), part.duration_sec, local_segs)
        part_kept = _extract_and_dedup(Path(part.path), cand, keyframes_dir / "frames",
                                       seen_hashes, key=part.key)
        for local_t, png, trig in part_kept:
            kept.append((local_t + part.offset_sec, png, trig))
        if len(parts) > 1:
            print(f"  [visual] part {part.key} @ +{part.offset_sec:.0f}s: "
                  f"{len(cand)} candidates → {len(part_kept)} frames", flush=True)
    kept.sort(key=lambda x: x[0])
    print(f"  [visual] {len(parts)} video(s) · {len(kept)} unique frames after phash dedup",
          flush=True)
    return kept


def batch_prefill_captions(event_id: str, caller, work_root: Path = WORK_ROOT) -> int:
    """Batch-fill every uncached frame caption in one job, then return #written.

    Writes visual's own ``<frame>.caption.json`` cache (R1). The subsequent ``extract_visual``
    run finds them CACHED and makes no live call — so the sync path stays byte-identical.
    Frames missing from the batch result (failures, R4) are left uncached for that loop."""
    from google.genai import types
    from src.batch_gemini import response_text
    from src.llm_caller import LLMRequest, prefill

    workdir = work_root / "events" / event_id
    keyframes_dir = workdir / util.STAGE_KEYFRAMES
    keyframes_dir.mkdir(parents=True, exist_ok=True)
    ing = IngestResult.model_validate_json(
        (workdir / util.STAGE_INGEST / "manifest.json").read_text())
    pending = [(t, png, trig) for (t, png, trig) in _kept_frames(ing, workdir, keyframes_dir)
               if not png.with_suffix(".caption.json").exists()]

    reqs = [LLMRequest(
                custom_id=str(png.with_suffix(".caption.json")),
                model=GEMINI_MODEL,
                contents=[VLM_PROMPT,
                          types.Part.from_bytes(data=png.read_bytes(), mime_type="image/jpeg")],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    thinking_config=types.ThinkingConfig(thinking_budget=0)))
            for (t, png, trig) in pending]

    def write_one(cid: str, resp) -> None:
        d = json.loads(util.strip_fences(response_text(resp) or "{}"))
        d["caption_status"] = "ok"
        Path(cid).write_text(json.dumps(d, indent=2))

    return prefill(caller, reqs, write_one)


def extract_visual(event_id: str, work_root: Path = WORK_ROOT,
                   describer: Optional[Describer] = None) -> list[Caption]:
    workdir = work_root / "events" / event_id
    keyframes_dir = workdir / util.STAGE_KEYFRAMES
    keyframes_dir.mkdir(parents=True, exist_ok=True)
    captions_path = keyframes_dir / "captions.json"
    if util.is_complete(captions_path):
        return [Caption.model_validate(c) for c in json.loads(captions_path.read_text())]

    ingest_manifest = workdir / util.STAGE_INGEST / "manifest.json"
    ing = IngestResult.model_validate_json(ingest_manifest.read_text())
    if ing.video_path is None and not ing.video_parts:
        raise RuntimeError(f"{event_id} has no video (notes-only event)")

    kept = _kept_frames(ing, workdir, keyframes_dir)

    describer = describer or GeminiDescriber()
    captions: list[Caption] = []
    for i, (t, png_path, trigger) in enumerate(kept, start=1):
        cache_path = png_path.with_suffix(".caption.json")
        if cache_path.exists():
            d = json.loads(cache_path.read_text())
            print(f"  [visual] caption {i}/{len(kept)} @ {t:.1f}s [{trigger}]… CACHED",
                  flush=True)
        else:
            print(f"  [visual] caption {i}/{len(kept)} @ {t:.1f}s [{trigger}]…",
                  flush=True, end=" ")
            try:
                d = describer.caption(png_path)
                d["caption_status"] = "ok"
                print("ok")
            except Exception as e:
                d = {"visible_text": "", "description": "",
                     "has_equation": False, "has_diagram": False,
                     "caption_status": f"failed: {type(e).__name__}"}
                print(f"FAILED: {e}")
            cache_path.write_text(json.dumps(d, indent=2))
        captions.append(Caption(
            t=t, frame_path=png_path, trigger=trigger,
            visible_text=d.get("visible_text", ""),
            description=d.get("description", ""),
            has_equation=bool(d.get("has_equation", False)),
            has_diagram=bool(d.get("has_diagram", False)),
            caption_status=d.get("caption_status", "ok"),
        ))

    util.write_with_manifest(
        captions_path,
        json.dumps([c.model_dump(mode="json") for c in captions], indent=2),
        stage="visual",
    )
    return captions


def _collect_candidates(video_path: Path, duration_sec: float,
                        segments: list[Segment]) -> list[tuple[float, str]]:
    """Return sorted [(time_sec, trigger), ...]. First trigger wins on dedup."""
    candidates: list[tuple[float, str]] = []

    try:
        scenes = detect(str(video_path), ContentDetector(threshold=SCENE_THRESHOLD))
        for s, e in scenes:
            candidates.append(((s.get_seconds() + e.get_seconds()) / 2, "scene"))
    except Exception as e:
        print(f"  [visual] scene detect failed: {e}", flush=True)

    t = 0.0
    while t < duration_sec:
        candidates.append((t, "safety"))
        t += SAFETY_NET_SEC

    for seg in segments:
        if any(pat.search(seg.text) for pat in AUDIO_CUE_PATTERNS):
            candidates.append((seg.start, "audio-cue"))

    seen: dict[float, str] = {}
    for t, trig in candidates:
        key = round(t, 1)
        if key not in seen:
            seen[key] = trig
    return sorted(seen.items())


def _extract_and_dedup(video_path: Path, candidates: list[tuple[float, str]],
                       kf_dir: Path, seen_hashes: list[imagehash.ImageHash],
                       key: str = "0") -> list[tuple[float, Path, str]]:
    """Extract candidate frames from one video (part-local times). seen_hashes is
    shared across an event's videos so a repeated slide dedups once. Returns
    (part_local_time, png, trigger); caller adds the part's offset."""
    kf_dir.mkdir(parents=True, exist_ok=True)
    kept: list[tuple[float, Path, str]] = []
    cap = cv2.VideoCapture(str(video_path))
    try:
        for time_sec, trigger in candidates:
            cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img.thumbnail((DOWNSCALE_MAX, DOWNSCALE_MAX))
            phash = imagehash.phash(img)
            if any(phash - h <= PHASH_HAMMING_MAX for h in seen_hashes):
                continue
            png_path = kf_dir / f"frame_{key}_{int(time_sec * 10):08d}.jpg"
            img.save(png_path, "JPEG", quality=JPEG_QUALITY)
            seen_hashes.append(phash)
            kept.append((time_sec, png_path, trigger))
    finally:
        cap.release()
    return kept
