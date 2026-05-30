"""Utility functions used across stages.

Tiny helpers — table alignment, string cleanup, atomic artifact writes.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


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
