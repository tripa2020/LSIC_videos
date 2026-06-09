"""Stage A.2 — Filter the manifest into a selected subset. NO downloads.

Filter (from review session):
  topics: Surface Power OR ISRU OR Excavation and Construction  (match ANY)
  categories: all
  grouping: whole-event — if any asset in an event matches, take the whole event
            (video + all decks + all PDFs). Standalone items (no event) are taken
            individually when they match.

Output:
  selected_manifest.json — the rows that would download
  prints a preview: count, by-kind, unique YouTube videos, event count

Run:  python download_lsic/select.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "download_manifest.json"
OUT = HERE / "selected_manifest.json"

TOPICS = {"Surface Power", "In Situ Resource Utilization", "Excavation and Construction"}
CATEGORIES: set[str] | None = None  # None = all categories
NO_EVENT = {"", "0", None}


def matches(row: dict) -> bool:
    if TOPICS and not (set(row["topics"]) & TOPICS):
        return False
    if CATEGORIES and row["category"] not in CATEGORIES:
        return False
    return True


def main() -> None:
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))
    direct = [r for r in rows if matches(r)]

    # whole-event expansion: pull every row sharing a matched event's id
    matched_events = {r["event_id"] for r in direct if r["event_id"] not in NO_EVENT}
    selected = [
        r for r in rows
        if (r["event_id"] in matched_events and r["event_id"] not in NO_EVENT)
        or (r in direct)
    ]
    # de-dup while preserving order
    seen, uniq = set(), []
    for r in selected:
        key = (r["row_id"], r["url"])
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    selected = uniq

    OUT.write_text(json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8")

    by_kind = Counter(r["kind"] for r in selected)
    yt_unique = len({r["yt_video_id"] for r in selected if r["yt_video_id"]})
    events = {r["event_id"] for r in selected if r["event_id"] not in NO_EVENT}
    standalone = sum(1 for r in selected if r["event_id"] in NO_EVENT)
    by_year = Counter(r["year"] for r in selected)

    print(f"SELECTED: {len(selected)} of {len(rows)} records")
    print(f"  direct topic matches: {len(direct)}  →  +whole-event expansion → {len(selected)}")
    print(f"  events: {len(events)}   standalone items: {standalone}")
    print(f"  unique YouTube videos to fetch (deduped): {yt_unique}")
    print("\n  by kind:")
    for k, v in by_kind.most_common():
        print(f"    {k:12} {v}")
    print("\n  by year:")
    for k, v in sorted(by_year.items()):
        print(f"    {k:8} {v}")
    print(f"\n[ok] wrote {OUT.relative_to(HERE.parent)} (no files downloaded)")


if __name__ == "__main__":
    main()
