"""Stage 2: Transcribe audio with chunking, diarization, language tagging.

Default backend: GeminiTranscriber (gemini-2.5-flash). GPU/local swap path:
implement the Transcriber protocol (e.g. WhisperXTranscriber) and pass it in.

Output: list[Segment] cached at <workdir>/transcript.json. Timestamps are
absolute (chunk offsets added back), sorted, clamped to duration.

Crash-proofing (the core logic is pure + injectable → unit-tested with fakes):
- `_transcribe_segment(call_fn, split_fn)` — on output-token overflow (finish_reason
  MAX_TOKENS) the audio is split in half and re-transcribed, guaranteeing completion.
- `_parse_segments` / `_reassemble` — structured-response parsing + parallel merge.
The API call (`GeminiTranscriber._call_api`) is the only un-tested boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional, Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from src import util
from src.contracts import IngestResult, Segment  # noqa: F401 (Segment used above)


WORK_ROOT = Path("work")
DEFAULT_CHUNK_SEC = 300        # 5-min chunks: lighter calls survive flaky networks
GEMINI_MODEL = "gemini-2.5-flash"
ASR_CONCURRENCY = int(os.getenv("ASR_CONCURRENCY", "12"))  # chunks transcribed in parallel
MAX_OUTPUT_TOKENS = 32_768     # raise from the 8,192 default so dense chunks don't truncate
MAX_SPLIT_DEPTH = 3            # backstop: halve a chunk that still overflows, up to 3 levels

ASR_PROMPT = """\
Transcribe the attached audio.

Return ONLY a JSON array. Each element:
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


class _AsrRow(BaseModel):
    """Response schema for one ASR segment — forces Gemini to emit valid, typed JSON."""
    start: float
    end: float
    text: str
    speaker_id: Optional[str] = None
    language: Optional[str] = None


# ---- pure, injectable logic (unit-tested with fakes, no network) -------------

def _transient(e: Exception) -> bool:
    """Retryable Gemini/network/DNS errors — delegates to the shared classifier."""
    return util.is_transient(e)


def _parse_segments(parsed: Optional[list], offset: float) -> list[Segment]:
    """Structured ASR rows → Segments with the chunk offset applied. Skips malformed rows."""
    segs: list[Segment] = []
    for s in parsed or []:
        try:
            segs.append(Segment(
                start=float(s["start"]) + offset,
                end=float(s["end"]) + offset,
                text=str(s.get("text", "")).strip(),
                speaker_id=s.get("speaker_id"),
                language=s.get("language"),
            ))
        except (KeyError, TypeError, ValueError):
            continue  # one bad row never sinks the chunk
    return segs


def _reassemble(by_idx: dict[int, list[Segment]], duration: float) -> list[Segment]:
    """Merge per-chunk results (any completion order) → clamped, zero-dropped, sorted."""
    all_segs = [s for i in sorted(by_idx) for s in by_idx[i]]
    for s in all_segs:
        s.start = max(0.0, min(s.start, duration))
        s.end = max(s.start, min(s.end, duration))
    all_segs = [s for s in all_segs if s.end > s.start]
    all_segs.sort(key=lambda s: s.start)
    return all_segs


# call_fn(audio) -> (parsed_rows | None, finish_reason); split_fn(audio, offset) -> [(audio, off), ...]
CallFn = Callable[[object], "tuple[Optional[list], str]"]
SplitFn = Callable[[object, float], "list[tuple[object, float]]"]


def _transcribe_segment(audio: object, offset: float, call_fn: CallFn, split_fn: SplitFn,
                        depth: int = 0) -> list[Segment]:
    """Transcribe one audio segment; on output-token overflow split in half and recurse.

    Pure given call_fn/split_fn → unit-testable with fakes. The recursion guarantees a
    too-dense chunk completes instead of crashing on a truncated response.
    """
    parsed, finish = call_fn(audio)
    if parsed is not None and "MAX_TOKENS" not in str(finish):
        return _parse_segments(parsed, offset)
    if depth >= MAX_SPLIT_DEPTH:
        raise RuntimeError(f"ASR output overflow past split depth {MAX_SPLIT_DEPTH}")
    out: list[Segment] = []
    for sub_audio, sub_off in split_fn(audio, offset):
        out += _transcribe_segment(sub_audio, sub_off, call_fn, split_fn, depth + 1)
    return out


def _finish_reason(resp) -> str:
    try:
        return str(resp.candidates[0].finish_reason)
    except (AttributeError, IndexError, TypeError):
        return ""


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def _opus_cmd(src: Path) -> list[str]:
    """ffmpeg command: audio → 32 kbps mono Opus/OGG on stdout. Gemini downsamples
    all audio to 16 kbps anyway, so this is ~8x smaller than 16-bit WAV with no
    speech-quality loss — smaller inline payload, faster upload, fewer timeouts."""
    return ["ffmpeg", "-y", "-v", "error", "-i", str(src),
            "-c:a", "libopus", "-b:a", "32k", "-ac", "1", "-ar", "16000",
            "-f", "ogg", "pipe:1"]


def _to_opus_bytes(src: Path) -> bytes:
    return subprocess.run(_opus_cmd(src), check=True, capture_output=True).stdout


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path, duration: float, workdir: Path) -> list[Segment]: ...


class GeminiTranscriber:
    def __init__(self, model: str = GEMINI_MODEL, chunk_sec: int = DEFAULT_CHUNK_SEC,
                 concurrency: int = ASR_CONCURRENCY):
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set in .env")
        # request timeout so a network blip raises (→ retried) instead of hanging forever
        self.client = genai.Client(api_key=api_key,
                                   http_options=types.HttpOptions(timeout=180_000))
        self.model = model
        self.chunk_sec = chunk_sec
        self.concurrency = max(1, concurrency)

    # --- the only un-tested boundary: the live API call + audio split ---

    def _call_api(self, audio_path: object) -> "tuple[Optional[list], str]":
        """Inline-Opus + generate (structured output). Returns (rows|None, finish_reason).
        finish_reason MAX_TOKENS → (None, 'MAX_TOKENS') so the caller splits the audio.
        The audio is transcoded to ~32 kbps Opus and sent inline (one request, no upload)."""
        part = types.Part.from_bytes(data=_to_opus_bytes(Path(audio_path)), mime_type="audio/ogg")
        for attempt in range(5):
            try:
                resp = self.client.models.generate_content(
                    model=self.model,
                    contents=[ASR_PROMPT, part],
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                        max_output_tokens=MAX_OUTPUT_TOKENS,
                        response_mime_type="application/json",
                        response_schema=list[_AsrRow],
                    ),
                )
                finish = _finish_reason(resp)
                if "MAX_TOKENS" in finish:
                    return None, "MAX_TOKENS"          # signal: split + retry on halves
                return json.loads(resp.text or "[]"), finish
            except json.JSONDecodeError:                # rare partial body → re-request
                if attempt < 4:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise
            except Exception as e:                      # transient overload/disconnect → retry
                if _transient(e) and attempt < 4:
                    print(f"    [transcribe] transient ({str(e)[:70]}) — retry {attempt + 1}/5",
                          flush=True)
                    time.sleep(5 * (attempt + 1))
                    continue
                raise
        raise RuntimeError("ASR call failed after retries")

    def _split_audio(self, audio_path: object, offset: float) -> "list[tuple[object, float]]":
        """Halve an over-dense audio chunk via ffmpeg; offsets map onto the event timeline."""
        p = Path(audio_path)
        half = _probe_duration(p) / 2.0
        a = p.with_name(f"{p.stem}_a{p.suffix}")
        b = p.with_name(f"{p.stem}_b{p.suffix}")
        subprocess.run(["ffmpeg", "-y", "-i", str(p), "-t", str(half), "-c", "copy", str(a)],
                       check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", str(p), "-ss", str(half), "-c", "copy", str(b)],
                       check=True, capture_output=True)
        return [(a, offset), (b, offset + half)]

    def _transcribe_chunk(self, chunk_path: Path, offset_sec: float) -> list[Segment]:
        return _transcribe_segment(chunk_path, offset_sec, self._call_api, self._split_audio)

    # --- orchestration (parallel, cache-first) ---

    def _chunk_segments(self, i: int, n: int, chunk_path: Path, offset: float) -> list[Segment]:
        """Transcribe one chunk (cache-first). Independent of every other chunk."""
        cache = chunk_path.with_suffix(".segments.json")
        if cache.exists():  # resumable: prior run finished this chunk's API call
            segs = [Segment.model_validate(s) for s in json.loads(cache.read_text())]
            print(f"  [transcribe] chunk {i}/{n} @ {offset:.0f}s … CACHED ({len(segs)} seg)",
                  flush=True)
            return segs
        print(f"  [transcribe] chunk {i}/{n} @ {offset:.0f}s … start", flush=True)
        segs = self._transcribe_chunk(chunk_path, offset)
        cache.write_text(json.dumps([s.model_dump(mode="json") for s in segs], indent=2))
        print(f"  [transcribe] chunk {i}/{n} @ {offset:.0f}s … done (+{len(segs)} seg)",
              flush=True)
        return segs

    def transcribe(self, audio_path: Path, duration: float, workdir: Path) -> list[Segment]:
        chunks = self._chunk_audio(audio_path, workdir)
        n = len(chunks)
        tasks = [(i, cp, off) for i, (cp, off) in enumerate(chunks, start=1)]
        by_idx: dict[int, list[Segment]] = {}

        workers = min(self.concurrency, n)
        if workers <= 1:
            for i, cp, off in tasks:
                by_idx[i] = self._chunk_segments(i, n, cp, off)
        else:
            print(f"  [transcribe] {n} chunks · {workers}-way parallel", flush=True)
            ex = ThreadPoolExecutor(max_workers=workers)
            try:
                futs = {ex.submit(self._chunk_segments, i, n, cp, off): i
                        for i, cp, off in tasks}
                for fut in as_completed(futs):
                    by_idx[futs[fut]] = fut.result()
            finally:
                ex.shutdown(wait=True, cancel_futures=True)

        return _reassemble(by_idx, duration)

    def _chunk_audio(self, audio_path: Path, workdir: Path) -> list[tuple[Path, float]]:
        chunk_dir = workdir / "chunks"
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
    manifest_path = event_workdir / util.STAGE_INGEST / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no ingest manifest at {manifest_path} — run --ingest first")
    ing = IngestResult.model_validate_json(manifest_path.read_text())
    if ing.audio_path is None:
        raise RuntimeError(f"{event_id} has no audio (notes-only event)")

    audio_path = Path(ing.audio_path)
    duration = ing.duration_sec
    transcript_dir = event_workdir / util.STAGE_TRANSCRIPT

    if max_sec is not None and max_sec < duration:
        slice_root = event_workdir / f"slice_{int(max_sec)}s"
        slice_root.mkdir(exist_ok=True)
        slice_path = slice_root / "audio.wav"
        if not slice_path.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(audio_path),
                 "-t", str(max_sec), "-c", "copy", str(slice_path)],
                check=True, capture_output=True,
            )
        audio_path = slice_path
        duration = float(max_sec)
        transcript_dir = slice_root / util.STAGE_TRANSCRIPT

    transcript_dir.mkdir(parents=True, exist_ok=True)
    segs = transcribe(audio_path, duration, transcript_dir)
    return transcript_dir / "transcript.json", segs
