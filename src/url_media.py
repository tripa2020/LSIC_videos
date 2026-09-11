"""URL-input media backends — Gemini reads a public YouTube URL server-side; nothing is
downloaded. This is what makes the pipeline hostable on any datacenter IP (yt-dlp from a
cloud VM hits YouTube's bot wall; Google's own fetch does not).

ONE module owns everything URL-specific (complexity review, hosted wrapper, Reduction 2):
- ``url_part`` — how a YouTube URL + clip offsets are expressed as a Gemini content part.
- ``windows`` — how a long video is cut so no single response truncates (same 5-min unit as
  the WAV chunks; timestamps come back RELATIVE to the clip, offset added back exactly like
  ``transcribe`` does for chunks).
- ``URL_TRANSIENT`` — the preview feature's quirk: 3-6 % of URL requests return a spurious
  ``400 INVALID_ARGUMENT`` that succeeds on retry (Google forum, Feb-Aug 2026).
- ``probe_duration`` — the model reports total length (measured exact on the reference event:
  4218 vs ffprobe 4218.7) from one low-fps whole-video call; this is the only no-download
  source of ``duration_sec``.
- ``URLTranscriber`` / ``URLDescriber`` — the ``Transcriber`` / visual backends, selected by
  the stages purely from MANIFEST STATE (``url_parts``: video parts with a ``source_url`` and
  no local ``path``) — no flag threads through any stage (Reduction 1).

Reuses ``transcribe``'s pure pieces (prompt, schema, ``_transcribe_segment`` overflow split,
``_parse_segments``, ``_reassemble``) so the URL path produces the same ``Segment`` stream.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Optional

from google.genai import types

from src import gemini_caller, util
from src.contracts import Caption, IngestResult, Segment, VideoPart

DEFAULT_WINDOW_SEC = 300          # same unit as transcribe.DEFAULT_CHUNK_SEC
PROBE_FPS = 0.05                  # duration probe: one frame per 20 s keeps the call cheap
URL_TRANSIENT = ("400 INVALID_ARGUMENT",)
GEMINI_MODEL = "gemini-2.5-flash"
URL_TIMEOUT_MS = 300_000
MAX_VISUAL_PER_WINDOW = 12

VISUAL_URL_PROMPT = """\
Watch this clip from a technical talk. List the SALIENT VISUAL MOMENTS — slides, diagrams,
equations, charts, tables, code, demos. Skip plain talking-head shots.

Return ONLY a JSON array (at most %d elements). Each element:
{
  "t": <seconds from the start of THIS clip, float>,
  "visible_text": "<readable on-screen text, verbatim; empty if none>",
  "description": "<one or two sentences describing what's shown>",
  "has_equation": <true|false>,
  "has_diagram": <true|false>
}""" % MAX_VISUAL_PER_WINDOW


def is_url_source(url: Optional[str]) -> bool:
    """YouTube only for now — the documented server-side fetch target."""
    return bool(url) and ("youtu.be" in url or "youtube.com" in url)


def url_parts(ing: IngestResult) -> list[VideoPart]:
    """The manifest-state selector: URL mode ⇔ no audio AND every video part is a URL with no
    local file. A downloaded (today's) manifest returns [] ⇒ every stage takes its old path."""
    if ing.audio_path is not None or not ing.video_parts:
        return []
    if all(p.path is None and is_url_source(p.source_url) for p in ing.video_parts):
        return list(ing.video_parts)
    return []


def url_part(url: str, start: Optional[float] = None, end: Optional[float] = None,
             fps: Optional[float] = None) -> types.Part:
    vm: dict[str, Any] = {}
    if start is not None:
        vm["start_offset"] = f"{int(start)}s"
    if end is not None:
        vm["end_offset"] = f"{int(end)}s"
    if fps is not None:
        vm["fps"] = fps
    return types.Part(file_data=types.FileData(file_uri=url),
                      video_metadata=types.VideoMetadata(**vm) if vm else None)


def windows(duration: float, window_sec: float = DEFAULT_WINDOW_SEC) -> list[tuple[float, float]]:
    """[(start, end), …] covering [0, duration]; always ≥1 window; last one is the remainder."""
    if duration <= 0:
        return [(0.0, 0.0)]
    out, t = [], 0.0
    while t < duration:
        out.append((t, min(t + window_sec, duration)))
        t += window_sec
    return out


def _low_res(cfg: types.GenerateContentConfig) -> types.GenerateContentConfig:
    cfg.media_resolution = types.MediaResolution.MEDIA_RESOLUTION_LOW
    return cfg


def probe_duration(url: str, client=None, model: str = GEMINI_MODEL) -> tuple[float, int]:
    """(duration_sec, n_speakers) from one low-fps whole-video call. Loud on nonsense."""
    client = client or gemini_caller.make_client(timeout_ms=URL_TIMEOUT_MS)
    d = gemini_caller.generate_json(
        client, model=model,
        contents=['Return ONLY JSON: {"duration_sec": <total length of this video in seconds, '
                  'as a number>, "speakers": <number of distinct speakers>}',
                  url_part(url, fps=PROBE_FPS)],
        config=_low_res(types.GenerateContentConfig(
            temperature=0.0, response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0))),
        expect=dict, extra_transient=URL_TRANSIENT, tag="url-probe")
    dur = float(d.get("duration_sec") or 0)
    if dur <= 0:
        raise RuntimeError(f"url probe returned no duration for {url}: {d}")
    return dur, int(d.get("speakers") or 0)


COLLAPSE_MIN_SEGS = 10
COLLAPSE_SPAN_FRACTION = 0.2


def _collapsed(segs: list[Segment], window_len: float) -> bool:
    """True when many segments share a tiny time span — the model lost the clip timeline
    (content is intact, timestamps are not). Short/sparse windows are never 'collapsed'."""
    if len(segs) < COLLAPSE_MIN_SEGS or window_len <= 0:
        return False
    span = max(s.end for s in segs) - min(s.start for s in segs)
    return span < COLLAPSE_SPAN_FRACTION * window_len


def _spread(segs: list[Segment], abs_off: float, window_len: float) -> list[Segment]:
    """Degrade: keep text + order, place segments evenly across the window (each gets
    ~window_len / n seconds) so downstream citations point into the right region."""
    n = len(segs)
    step = window_len / n
    out = []
    for k, s in enumerate(segs):
        out.append(s.model_copy(update={"start": abs_off + k * step,
                                        "end": abs_off + (k + 1) * step}))
    return out


def _parallel(fn: Callable, items: list, workers: int) -> dict[int, Any]:
    """Run fn(i, item) for every item, up to ``workers`` at a time; {i: result}."""
    out: dict[int, Any] = {}
    if workers <= 1 or len(items) <= 1:
        for i, it in enumerate(items):
            out[i] = fn(i, it)
        return out
    ex = ThreadPoolExecutor(max_workers=workers)
    try:
        futs = {ex.submit(fn, i, it): i for i, it in enumerate(items)}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
    return out


class URLTranscriber:
    """``Transcriber`` backend over URL parts. Per-window cache under ``<workdir>/windows/``
    (resume-safe, mirrors the chunk cache); overflow on a dense window halves it via the
    shared ``_transcribe_segment``; timestamps are clip-relative → offset added back, then
    clamped to the window (the model overshoots a clip's end by a few seconds)."""

    def __init__(self, parts: list[VideoPart], model: str = GEMINI_MODEL,
                 window_sec: float = DEFAULT_WINDOW_SEC, concurrency: Optional[int] = None,
                 client=None):
        from src import transcribe
        self.parts, self.model, self.window_sec = parts, model, window_sec
        self.concurrency = max(1, concurrency if concurrency is not None
                               else transcribe.ASR_CONCURRENCY)
        self.client = client or gemini_caller.make_client(timeout_ms=URL_TIMEOUT_MS)

    # --- the live boundary ---
    def _call_api(self, win: tuple[str, float, float]) -> tuple[Optional[list], str]:
        from src import transcribe
        url, start, end = win
        try:
            rows = gemini_caller.generate_json(
                self.client, model=self.model,
                contents=[transcribe.ASR_PROMPT, url_part(url, start, end)],
                config=_low_res(transcribe._asr_config()), expect=list,
                extra_transient=URL_TRANSIENT, tag="transcribe/url")
        except gemini_caller.Truncated:
            return None, "MAX_TOKENS"
        return rows, "STOP"

    @staticmethod
    def _split(win: tuple[str, float, float], offset: float) -> list[tuple[tuple[str, float, float], float]]:
        url, start, end = win
        mid = (start + end) / 2.0
        return [((url, start, mid), offset), ((url, mid, end), offset + (mid - start))]

    def _window_segments(self, i: int, item: tuple[Path, str, float, float, float]) -> list[Segment]:
        from src import transcribe
        cache, url, start, end, abs_off = item
        if cache.exists():
            segs = [Segment.model_validate(s) for s in json.loads(cache.read_text())]
            print(f"  [transcribe/url] window {i + 1} @ {abs_off:.0f}s … CACHED ({len(segs)} seg)",
                  flush=True)
            return segs
        print(f"  [transcribe/url] window {i + 1} @ {abs_off:.0f}s … start", flush=True)
        segs = transcribe._transcribe_segment((url, start, end), abs_off, self._call_api, self._split)
        if _collapsed(segs, end - start):    # observed 2026-09-11: 76 segs squeezed into 5 s
            print(f"  [transcribe/url] window {i + 1}: timestamps collapsed — re-issuing once",
                  flush=True)
            segs = transcribe._transcribe_segment((url, start, end), abs_off, self._call_api, self._split)
            if _collapsed(segs, end - start):
                print(f"  [transcribe/url] window {i + 1}: still collapsed — spreading evenly "
                      f"(citations approximate in this window)", flush=True)
                segs = _spread(segs, abs_off, end - start)
        hi = abs_off + (end - start)
        for s in segs:                       # per-window clamp: clip-relative timestamps overshoot
            s.start = max(abs_off, min(s.start, hi))
            s.end = max(s.start, min(s.end, hi))
        segs = [s for s in segs if s.end > s.start]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps([s.model_dump(mode="json") for s in segs], indent=2))
        print(f"  [transcribe/url] window {i + 1} @ {abs_off:.0f}s … done (+{len(segs)} seg)",
              flush=True)
        return segs

    def transcribe(self, audio_path: Optional[Path], duration: float, workdir: Path) -> list[Segment]:
        from src import transcribe
        items: list[tuple[Path, str, float, float, float]] = []
        for p in self.parts:
            for (s, e) in windows(p.duration_sec, self.window_sec):
                items.append((workdir / "windows" / f"{p.key}_{int(s):06d}.segments.json",
                              p.source_url, s, e, p.offset_sec + s))
        n = len(items)
        print(f"  [transcribe/url] {n} windows · {min(self.concurrency, n)}-way parallel",
              flush=True)
        by_idx = _parallel(self._window_segments, items, self.concurrency)
        return transcribe._reassemble({i + 1: v for i, v in by_idx.items()}, duration)


class URLDescriber:
    """Visual backend over URL parts: per window, the model lists salient visual moments with
    clip-relative timestamps → ``Caption`` rows with ``frame_path=None`` and ``trigger="url"``.
    Per-window cache; a failed window is logged and left uncached (retried next run)."""

    def __init__(self, parts: list[VideoPart], model: str = GEMINI_MODEL,
                 window_sec: float = DEFAULT_WINDOW_SEC, concurrency: int = 4, client=None):
        self.parts, self.model, self.window_sec = parts, model, window_sec
        self.concurrency = max(1, concurrency)
        self.client = client or gemini_caller.make_client(timeout_ms=URL_TIMEOUT_MS)

    def _window(self, i: int, item: tuple[Path, str, float, float, float]) -> list[Caption]:
        cache, url, start, end, abs_off = item
        if cache.exists():
            rows = json.loads(cache.read_text())
        else:
            try:
                rows = gemini_caller.generate_json(
                    self.client, model=self.model,
                    contents=[VISUAL_URL_PROMPT, url_part(url, start, end)],
                    config=_low_res(types.GenerateContentConfig(
                        temperature=0.0, response_mime_type="application/json",
                        thinking_config=types.ThinkingConfig(thinking_budget=0))),
                    expect=list, extra_transient=URL_TRANSIENT, tag="visual/url")
            except Exception as e:
                print(f"  [visual/url] window {i + 1} @ {abs_off:.0f}s FAILED: "
                      f"{type(e).__name__}: {str(e)[:80]}", flush=True)
                return []
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(rows, indent=2))
        out: list[Caption] = []
        hi = end - start
        for r in rows[:MAX_VISUAL_PER_WINDOW]:
            try:
                t = max(0.0, min(float(r.get("t", 0.0)), hi)) + abs_off
                out.append(Caption(
                    t=t, frame_path=None, trigger="url",
                    visible_text=str(r.get("visible_text", "") or ""),
                    description=str(r.get("description", "") or ""),
                    has_equation=bool(r.get("has_equation", False)),
                    has_diagram=bool(r.get("has_diagram", False))))
            except (TypeError, ValueError):
                continue
        return out

    def captions(self, cache_dir: Path) -> list[Caption]:
        items = [(cache_dir / "windows" / f"{p.key}_{int(s):06d}.captions.json",
                  p.source_url, s, e, p.offset_sec + s)
                 for p in self.parts for (s, e) in windows(p.duration_sec, self.window_sec)]
        print(f"  [visual/url] {len(items)} windows", flush=True)
        by_idx = _parallel(self._window, items, self.concurrency)
        caps = [c for i in sorted(by_idx) for c in by_idx[i]]
        caps.sort(key=lambda c: c.t)
        return caps
