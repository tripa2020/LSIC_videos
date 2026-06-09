"""Stage A — Harvest the LSIC catalog into a review manifest. NO downloads.

The entire catalog is embedded in the public page
https://lsic.jhuapl.edu/Resources/Products.php as a JS array `allResults`.
One GET retrieves all ~1184 records. No auth, no Playwright, no pagination.

Output:
  download_manifest.json   — one row per catalog record (all 1184), tagged
  catalog_summary.md       — human-readable breakdown for picking a filter

Run:  python download_lsic/harvest.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

SRC_URL = "https://lsic.jhuapl.edu/Resources/Products.php"
BASE = "https://lsic.jhuapl.edu"
HERE = Path(__file__).resolve().parent
ART = HERE / "recon_artifacts"
MANIFEST = HERE / "download_manifest.json"
SUMMARY = HERE / "catalog_summary.md"


def fetch_html() -> str:
    cached = ART / "products.html"
    try:
        req = urllib.request.Request(SRC_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            html = r.read().decode("utf-8", "replace")
        ART.mkdir(parents=True, exist_ok=True)
        cached.write_text(html, encoding="utf-8")
        return html
    except Exception as e:  # offline fallback to last good copy
        if cached.exists():
            print(f"[warn] fetch failed ({e}); using cached products.html", file=sys.stderr)
            return cached.read_text(encoding="utf-8")
        raise


def extract_all_results(html: str) -> list[dict]:
    """Brace-match the `allResults = [ ... ]` array and json.loads it."""
    m = re.search(r"allResults\s*=\s*\[", html)
    if not m:
        raise RuntimeError("allResults array not found in page")
    start = m.end() - 1
    depth = 0
    for i in range(start, len(html)):
        c = html[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html[start : i + 1])
    raise RuntimeError("unterminated allResults array")


def yt_id(url: str) -> str | None:
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0].split("&")[0]
    if "watch?v=" in url:
        return urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("v", [None])[0]
    if "/embed/" in url:
        return url.split("/embed/")[1].split("?")[0]
    return None


def classify(r: dict) -> str:
    fp = (r.get("filePath") or "").lower()
    au = r.get("associatedUrl") or ""
    if au and ("youtu.be" in au or "youtube.com" in au):
        return "youtube"
    if fp.endswith((".mp4", ".mov", ".m4v")):
        return "video_file"
    if fp.endswith(".pdf"):
        return "pdf"
    if fp.endswith((".pptx", ".ppt")):
        return "pptx"
    if fp:
        return "otherfile"
    if au:
        return "otherurl"
    return "none"


def to_row(r: dict) -> dict:
    kind = classify(r)
    fp = r.get("filePath") or ""
    au = r.get("associatedUrl") or ""
    is_file = bool(fp)
    # target filename: file-backed items already encode <lsic_id>-<name> in filePath
    if is_file:
        target = fp.split("/")[-1]
        if not re.match(r"^\d+-", target) and r.get("file") not in (None, "0", ""):
            target = f"{r['file']}-{target}"
        lsic_id = int(r["file"]) if str(r.get("file", "")).isdigit() else None
        url = BASE + fp
    else:  # youtube / url-only — no file id; flag naming for download stage
        lsic_id = None
        url = au
        target = None  # decided at fetch (yt-dlp uses <row_id>-<title> or video id)
    return {
        "row_id": r.get("id"),
        "lsic_id": lsic_id,
        "kind": kind,
        "title": (r.get("title") or "").strip(),
        "speaker": r.get("speaker") or "",
        "url": url,
        "yt_video_id": yt_id(au) if kind == "youtube" else None,
        "target_filename": target,
        "category": r.get("categoryName") or "",
        "subcategory": r.get("subCategoryName") or "",
        "topics": r.get("topicList") or [],
        "event_id": r.get("associatedEvent") or "",
        "event_name": r.get("eventName") or "",
        "year": (r.get("releaseDate") or "")[:4] or "unknown",
        "release_date": r.get("releaseDate") or "",
    }


def write_summary(rows: list[dict]) -> str:
    def tally(key, multi=False):
        c = Counter()
        for row in rows:
            v = row[key]
            if multi:
                for x in v or ["(none)"]:
                    c[x] += 1
            else:
                c[v or "(none)"] += 1
        return c

    by_kind = tally("kind")
    by_cat = tally("category")
    by_topic = tally("topics", multi=True)
    by_year = tally("year")
    yt_unique = len({r["yt_video_id"] for r in rows if r["yt_video_id"]})

    def block(title, counter, n=40):
        lines = [f"### {title}", "", "| value | count |", "|---|---|"]
        for k, v in counter.most_common(n):
            lines.append(f"| {k} | {v} |")
        return "\n".join(lines) + "\n"

    out = [
        f"# LSIC catalog summary — {len(rows)} records",
        "",
        f"Source: {SRC_URL} (public, no auth). YouTube unique videos: {yt_unique}.",
        "",
        "**No files downloaded.** Pick a category + capability-area filter, then run the fetch stage.",
        "",
        block("By kind (how it downloads)", by_kind),
        block("By category", by_cat),
        block("By capability area (topic)", by_topic),
        block("By year", by_year),
    ]
    text = "\n".join(out)
    SUMMARY.write_text(text, encoding="utf-8")
    return text


def main() -> None:
    html = fetch_html()
    records = extract_all_results(html)
    rows = [to_row(r) for r in records]
    MANIFEST.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = write_summary(rows)
    print(summary)
    print(f"\n[ok] wrote {MANIFEST.relative_to(HERE.parent)} ({len(rows)} rows)")
    print(f"[ok] wrote {SUMMARY.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
