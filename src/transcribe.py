"""Stage 2: Transcribe audio with chunking, diarization, language tagging.

Default backend: GeminiTranscriber (gemini-2.5-flash). GPU/local swap path:
implement the Transcriber protocol (e.g. WhisperXTranscriber) and pass it in.

Output: list[Segment] cached at <workdir>/transcript.json. Timestamps are
absolute (chunk offsets added back), sorted, clamped to duration.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src import util
from src.contracts import IngestResult, Segment  # noqa: F401 (Segment used above)


WORK_ROOT = Path("work")
DEFAULT_CHUNK_SEC = 600        # 10-min chunks keep each JSON response under output limits
GEMINI_MODEL = "gemini-2.5-flash"
FILE_ACTIVE_TIMEOUT_SEC = 60

ASR_PROMPT = """\
Transcribe the attached audio.

Return ONLY a JSON array (no prose, no markdown fences). Each element:
{
  "start": <seconds float, from start of THIS clip>,
  "end":   <seconds float>,
  "text":  "<verbatim speech>",
  "speaker_id": "A" | "B" | "C" (consistent per voice across the clip),
  "language": "<ISO 639-1 code, e.g. 'en'>"
}

Segment at natural clause boundaries (~5-15s per segment). Use the SAME
speaker letter for the same voice every time. Do not invent content during
silence."""


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path, duration: float, workdir: Path) -> list[Segment]: ...


class GeminiTranscriber:
    def __init__(self, model: str = GEMINI_MODEL, chunk_sec: int = DEFAULT_CHUNK_SEC):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set in .env")
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.chunk_sec = chunk_sec

    def transcribe(self, audio_path: Path, duration: float, workdir: Path) -> list[Segment]:
        chunks = self._chunk_audio(audio_path, workdir)
        all_segs: list[Segment] = []
        for i, (chunk_path, offset) in enumerate(chunks, start=1):
            chunk_cache = chunk_path.with_suffix(".segments.json")
            if chunk_cache.exists():
                # Resumable: prior run completed this chunk's API call. Skip Gemini.
                segs = [Segment.model_validate(s) for s in json.loads(chunk_cache.read_text())]
                print(f"  [transcribe] chunk {i}/{len(chunks)} @ {offset:.0f}s "
                      f"({chunk_path.name})… CACHED ({len(segs)} segments)", flush=True)
            else:
                print(f"  [transcribe] chunk {i}/{len(chunks)} @ {offset:.0f}s "
                      f"({chunk_path.name})…", flush=True)
                segs = self._transcribe_chunk(chunk_path, offset)
                # Per-chunk atomic write so a kill mid-loop never costs more
                # than the in-flight chunk's API spend on rerun.
                chunk_cache.write_text(json.dumps(
                    [s.model_dump(mode="json") for s in segs], indent=2,
                ))
                print(f"    + {len(segs)} segments")
            all_segs.extend(segs)

        for s in all_segs:
            s.start = max(0.0, min(s.start, duration))
            s.end = max(s.start, min(s.end, duration))
        # drop zero-duration segments — usually tail artifacts where Gemini
        # extrapolated past the clip end and got clamped flat
        all_segs = [s for s in all_segs if s.end > s.start]
        all_segs.sort(key=lambda s: s.start)
        return all_segs

    def _chunk_audio(self, audio_path: Path, workdir: Path) -> list[tuple[Path, float]]:
        chunk_dir = workdir / "audio_chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(chunk_dir.glob("chunk_*.wav"))
        if existing:
            return [(c, i * self.chunk_sec) for i, c in enumerate(existing)]
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path),
             "-f", "segment", "-segment_time", str(self.chunk_sec),
             "-ar", "16000", "-ac", "1",
             str(chunk_dir / "chunk_%03d.wav")],
            check=True, capture_output=True,
        )
        chunks = sorted(chunk_dir.glob("chunk_*.wav"))
        return [(c, i * self.chunk_sec) for i, c in enumerate(chunks)]

    def _transcribe_chunk(self, chunk_path: Path, offset_sec: float) -> list[Segment]:
        audio_file = self.client.files.upload(file=str(chunk_path))
        deadline = time.monotonic() + FILE_ACTIVE_TIMEOUT_SEC
        while audio_file.state.name == "PROCESSING" and time.monotonic() < deadline:
            time.sleep(1)
            audio_file = self.client.files.get(name=audio_file.name)
        if audio_file.state.name != "ACTIVE":
            raise RuntimeError(f"Gemini file upload not ACTIVE: {audio_file.state.name}")

        resp = self.client.models.generate_content(
            model=self.model,
            contents=[ASR_PROMPT, audio_file],
            config=types.GenerateContentConfig(
                temperature=0.0,
                # Disable thinking — verbatim ASR doesn't benefit from it, and
                # thinking causes 5-10x slowdown on long audio chunks (observed
                # 25+ min stall on a 10-min chunk that should take ~1 min).
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = util.strip_fences(resp.text or "")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Gemini returned non-JSON ({chunk_path.name}): {raw[:300]}…") from e

        segs: list[Segment] = []
        for s in parsed:
            segs.append(Segment(
                start=float(s["start"]) + offset_sec,
                end=float(s["end"]) + offset_sec,
                text=str(s["text"]).strip(),
                speaker_id=s.get("speaker_id"),
                language=s.get("language"),
            ))
        return segs


def transcribe(audio_path: Path, duration: float, workdir: Path,
               transcriber: Optional[Transcriber] = None) -> list[Segment]:
    cache = workdir / "transcript.json"
    if util.is_complete(cache):
        return [Segment.model_validate(s) for s in json.loads(cache.read_text())]
    transcriber = transcriber or GeminiTranscriber()
    segs = transcriber.transcribe(audio_path, duration, workdir)
    util.write_with_manifest(
        cache,
        json.dumps([s.model_dump(mode="json") for s in segs], indent=2),
        stage="transcribe",
    )
    return segs


def transcribe_one_event(event_id: str, max_sec: Optional[float] = None,
                         work_root: Path = WORK_ROOT) -> tuple[Path, list[Segment]]:
    event_workdir = work_root / "events" / event_id
    manifest_path = event_workdir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no manifest at {manifest_path} — run --ingest first")
    ing = IngestResult.model_validate_json(manifest_path.read_text())
    if ing.audio_path is None:
        raise RuntimeError(f"{event_id} has no audio (notes-only event)")

    audio_path = Path(ing.audio_path)
    duration = ing.duration_sec
    target_workdir = event_workdir

    if max_sec is not None and max_sec < duration:
        slice_path = event_workdir / f"audio_slice_{int(max_sec)}s.wav"
        if not slice_path.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(audio_path),
                 "-t", str(max_sec), "-c", "copy", str(slice_path)],
                check=True, capture_output=True,
            )
        audio_path = slice_path
        duration = float(max_sec)
        target_workdir = event_workdir / f"transcript_slice_{int(max_sec)}s"
        target_workdir.mkdir(exist_ok=True)

    segs = transcribe(audio_path, duration, target_workdir)
    return target_workdir / "transcript.json", segs
