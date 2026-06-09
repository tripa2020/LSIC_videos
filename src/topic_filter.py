"""Deterministic Energy ∪ ISRU event filter (Part 2, M-C3).

The cloud batch-1 slice = events whose catalog ``topics`` include **Surface Power** (Energy)
or **In Situ Resource Utilization** (ISRU). Pure set algebra over the curated
``selected_manifest`` ``topics`` field — no keyword guessing. The resulting event-id set feeds
``group_manifest.build(event_ids)``.

Reproduces the locked counts: **130 events / 122 with video** (see CLOUD_BATCH_PLAN.md).
Zero network — reads the local manifest only.
"""
from __future__ import annotations

import json
from pathlib import Path

MANIFEST = Path("download_lsic/selected_manifest.json")
ENERGY = "Surface Power"
ISRU = "In Situ Resource Utilization"
SLICE_TOPICS = frozenset({ENERGY, ISRU})
_NO_EVENT = {None, "", "0"}
_VIDEO_EXTS = (".mp4", ".mov", ".m4v")


def _rows(manifest_path: Path | str) -> list[dict]:
    return json.loads(Path(manifest_path).read_text())


def _has_video(row: dict) -> bool:
    if row.get("kind") == "youtube" or row.get("yt_video_id"):
        return True
    return (row.get("target_filename") or "").lower().endswith(_VIDEO_EXTS)


def energy_isru_event_ids(manifest_path: Path | str = MANIFEST) -> set[str]:
    """Event_ids with at least one row tagged Surface Power or ISRU (the slice)."""
    ids: set[str] = set()
    for r in _rows(manifest_path):
        eid = r.get("event_id")
        if eid in _NO_EVENT:
            continue
        if SLICE_TOPICS & set(r.get("topics") or []):
            ids.add(eid)
    return ids


def with_video(manifest_path: Path | str = MANIFEST,
               ids: set[str] | None = None) -> set[str]:
    """Subset of ``ids`` (default: the Energy∪ISRU set) that has ≥1 video row — the runnable
    batch (deck/paper-only events have no audio spine)."""
    if ids is None:
        ids = energy_isru_event_ids(manifest_path)
    return {r.get("event_id") for r in _rows(manifest_path)
            if r.get("event_id") in ids and _has_video(r)}


if __name__ == "__main__":
    all_ids = energy_isru_event_ids()
    vid_ids = with_video(ids=all_ids)
    print(f"[topic_filter] Energy∪ISRU: {len(all_ids)} events, {len(vid_ids)} with video")
    print(" ".join(sorted(vid_ids)))
