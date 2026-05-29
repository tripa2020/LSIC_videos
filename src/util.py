"""Utility functions used across stages.

Tiny, no I/O, no side effects — these are imported everywhere.
"""

from __future__ import annotations

import re
import unicodedata


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
