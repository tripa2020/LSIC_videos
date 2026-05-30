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
from src.contracts import Caption, IngestResult, Segment


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


class Describer(Protocol):
    def caption(self, image_path: Path) -> dict: ...


class GeminiDescriber:
    def __init__(self, model: str = GEMINI_MODEL):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set in .env")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def caption(self, image_path: Path) -> dict:
        img_bytes = image_path.read_bytes()
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


def extract_visual(event_id: str, work_root: Path = WORK_ROOT,
                   describer: Optional[Describer] = None) -> list[Caption]:
    workdir = work_root / "events" / event_id
    captions_path = workdir / "captions.json"
    if util.is_complete(captions_path):
        return [Caption.model_validate(c) for c in json.loads(captions_path.read_text())]

    ing = IngestResult.model_validate_json((workdir / "manifest.json").read_text())
    if ing.video_path is None:
        raise RuntimeError(f"{event_id} has no video (notes-only event)")

    segments: list[Segment] = []
    transcript_path = workdir / "transcript.json"
    if transcript_path.exists():
        segments = [Segment.model_validate(s) for s in json.loads(transcript_path.read_text())]

    candidates = _collect_candidates(Path(ing.video_path), ing.duration_sec, segments)
    print(f"  [visual] candidates: {len(candidates)} "
          f"(scene={sum(1 for _, t in candidates if t == 'scene')} "
          f"safety={sum(1 for _, t in candidates if t == 'safety')} "
          f"audio-cue={sum(1 for _, t in candidates if t == 'audio-cue')})",
          flush=True)

    kept = _extract_and_dedup(Path(ing.video_path), candidates, workdir / "keyframes")
    print(f"  [visual] after phash dedup: {len(kept)} unique frames", flush=True)

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
                       kf_dir: Path) -> list[tuple[float, Path, str]]:
    kf_dir.mkdir(parents=True, exist_ok=True)
    kept: list[tuple[float, Path, str]] = []
    seen_hashes: list[imagehash.ImageHash] = []
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
            png_path = kf_dir / f"frame_{int(time_sec * 10):08d}.jpg"
            img.save(png_path, "JPEG", quality=JPEG_QUALITY)
            seen_hashes.append(phash)
            kept.append((time_sec, png_path, trigger))
    finally:
        cap.release()
    return kept
