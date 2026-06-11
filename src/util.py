"""Utility functions used across stages.

Tiny helpers — table alignment, string cleanup, atomic artifact writes,
and the per-event workdir layout constants.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---- per-event workdir stage layout (locked 2026-05-30) ----
# Each event's work/events/<event_id>/ has these stage subfolders:
STAGE_INGEST = "01_ingest"        # IngestResult manifest, audio.wav, decks/
STAGE_TRANSCRIPT = "02_transcript"  # transcript.json, chunks/
STAGE_KEYFRAMES = "03_keyframes"   # captions.json, frames/
STAGE_ALIGNED = "04_aligned"       # aligned.json, evidence.json (M4)
STAGE_BRIEFING = "05_briefing"     # notes.md (M5)
STAGE_REFERENCES = "06_references"  # references.md/.json (M3 enrich — related papers)


def strip_fences(s: str) -> str:
    """Drop ```...``` markdown fences that LLMs sometimes wrap JSON in."""
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else ""
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def mmss(seconds: float) -> str:
    """Format a duration in seconds as `[mm:ss]` for citation inlining."""
    seconds = max(0, int(seconds))
    return f"[{seconds // 60:02d}:{seconds % 60:02d}]"


def slugify(text: str) -> str:
    """Lowercase ASCII slug for event_id / asset_id generation."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return text


def _display_width(s: str) -> int:
    """Visible cell width — wide unicode (CJK/emoji) counts as 2.

    Pragmatic estimate good enough for the LSIC corpus (mostly ASCII plus the
    occasional µ, ³, →, em-dash). Markdown viewers align by display width.
    """
    width = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("F", "W"):
            width += 2
        else:
            width += 1
    return width


def align_table(rows: list[list[str]]) -> str:
    """Render a markdown table with all columns space-padded to the widest cell.

    `rows[0]` is the header. The divider row is auto-generated with dashes
    matching each column's width. Every `|` aligns across rows.

    Raises ValueError if rows have mismatched column counts.
    """
    if not rows:
        return ""
    n_cols = len(rows[0])
    if not all(len(r) == n_cols for r in rows):
        raise ValueError(f"align_table: ragged rows ({n_cols} cols expected)")

    widths = [
        max(_display_width(row[c]) for row in rows)
        for c in range(n_cols)
    ]

    def fmt_row(row: list[str]) -> str:
        cells = []
        for c, val in enumerate(row):
            pad = widths[c] - _display_width(val)
            cells.append(" " + val + " " * pad + " ")
        return "|" + "|".join(cells) + "|"

    def divider() -> str:
        return "|" + "|".join("-" * (widths[c] + 2) for c in range(n_cols)) + "|"

    out = [fmt_row(rows[0]), divider()]
    out.extend(fmt_row(row) for row in rows[1:])
    return "\n".join(out)


# ---- atomic artifact writes + manifest gate (M2.6) ----

def atomic_write_text(path: Path, text: str) -> None:
    """Write text to <path>.tmp then rename. Same-filesystem rename is atomic.

    Crashes mid-write leave only the .tmp file (which the manifest gate
    will not promote to 'complete'). Never leaves a half-written artifact
    that downstream cache-skip would falsely trust.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def write_with_manifest(path: Path, text: str, stage: str,
                        input_hash: Optional[str] = None) -> None:
    """Atomically write the artifact, then write its sibling .manifest.json."""
    atomic_write_text(path, text)
    manifest = {
        "stage": stage,
        "status": "complete",
        "artifact": path.name,
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if input_hash is not None:
        manifest["input_hash"] = input_hash
    atomic_write_text(
        path.with_suffix(path.suffix + ".manifest.json"),
        json.dumps(manifest, indent=2),
    )


def is_complete(path: Path) -> bool:
    """Cache-skip gate: artifact exists AND its manifest says status=complete.

    Plain `path.exists()` lies after a kill mid-write. This check is the
    minimum safe gate for stage-skip.
    """
    if not path.exists():
        return False
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    if not manifest_path.exists():
        return False
    try:
        m = json.loads(manifest_path.read_text())
        return m.get("status") == "complete"
    except (json.JSONDecodeError, OSError):
        return False


# ---- one shared retry classifier for every Gemini stage (transcribe/visual/synth) ----

_TRANSIENT_MARKERS = (
    # Gemini server-side: overload / rate / deadline
    "503", "429", "500", "502", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED",
    "overloaded", "high demand", "DEADLINE",
    # dropped connections
    "RemoteProtocolError", "Server disconnected", "disconnected",
    "ConnectError", "ConnectionError", "RemoteDisconnected", "EOF occurred",
    "timed out", "Timeout",
    # DNS / name-resolution blips on flaky networks
    "nodename nor servname", "getaddrinfo", "Name or service not known",
    "Temporary failure in name resolution", "Errno 8", "Errno -2", "Errno -3",
)


def is_transient(e: Exception) -> bool:
    """True for retryable Gemini/network errors (overload, deadline, dropped
    connection, or DNS blip). Single source of truth across all API stages."""
    msg = str(e)
    return any(k in msg for k in _TRANSIENT_MARKERS)


def retry_transient(fn, *, attempts: int = 5, base_delay: float = 5.0,
                    sleep=None):
    """Call ``fn()`` and return its result; on a transient error (``is_transient``)
    retry up to ``attempts`` times with linear backoff ``base_delay*(n+1)`` seconds.

    The shared retry *policy* companion to ``is_transient`` — one place, every stage.
    Non-transient errors propagate immediately. The last transient error re-raises
    once ``attempts`` is exhausted. ``sleep`` is injectable (defaults to ``time.sleep``,
    resolved at call time so tests can monkeypatch ``util.time.sleep``) — no real wait.

    Degrade-to-today: ``fn`` that succeeds first call returns with **zero** added
    latency and no sleep — byte-identical to a bare ``fn()``.
    """
    _sleep = sleep if sleep is not None else time.sleep
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — classifier decides retry vs raise
            if is_transient(e) and attempt < attempts - 1:
                _sleep(base_delay * (attempt + 1))
                continue
            raise
