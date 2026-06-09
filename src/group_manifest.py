"""Build work/events.json + per-event meta.json from the LSIC catalog manifest (G2).

Replaces discover.py's disk-scan for the downloaded corpus:
  - groups by the site's `associatedEvent` (authoritative, vs ID-proximity guessing)
  - names events `lsic_<date>` and lays asset paths into LSIC_Downloads/<event_id>/ (Layout B)
  - carries catalog truth (speaker, title, topics) into each asset's `meta` and a durable
    work/events/<event>/meta.json ledger so synthesize uses site truth, not filename guesses
  - multi-video aware: Zoom split recordings AND YouTube `?t=` sessions become video assets;
    a YouTube video's `?t=` rows are recorded as presentation windows in its meta

Videos are URL-backed (path=None, source_url set) → ingest fetches them transiently.
Docs are moved from the flat LSIC_Downloads/ into their event folder (Layout B).

Run:  python -m src.group_manifest 599 634 63600021     # specific events (pilot)
      python -m src.group_manifest                       # all events in the selection
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from src.contracts import Asset, Event

MANIFEST = Path("download_lsic/selected_manifest.json")
DOWNLOADS = Path("LSIC_Downloads")
WORK = Path("work")
NO_EVENT = {"", "0", None}


def _kind(row: dict) -> str:
    k, fn = row["kind"], (row.get("target_filename") or "").lower()
    if k in ("youtube", "video_file"):
        return "video"
    if k == "pptx":
        return "host_deck" if "spcaslides" in fn else "presentation"
    if k == "pdf":
        return "notes" if "notes" in fn else "presentation"
    return "presentation"


def _event_date(rows: list[dict]) -> str:
    ds = [r["release_date"] for r in rows
          if r.get("release_date") and r["release_date"] != "0000-00-00"]
    return Counter(ds).most_common(1)[0][0] if ds else "unknown"


def _asset_meta(row: dict) -> dict:
    return {k: row.get(k) for k in
            ("row_id", "lsic_id", "title", "speaker", "topics",
             "category", "subcategory", "release_date", "yt_video_id", "url")}


def _t_offset(url: str) -> int:
    m = re.search(r"[?&]t=(\d+)", url or "")
    return int(m.group(1)) if m else 0


def build(event_ids: set[str] | None, move_docs: bool = True) -> dict:
    rows = json.loads(MANIFEST.read_text())
    by_event: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["event_id"] in NO_EVENT:
            continue
        if event_ids and r["event_id"] not in event_ids:
            continue
        by_event[r["event_id"]].append(r)

    events: list[Event] = []
    used_ids: set[str] = set()
    for site_eid, erows in sorted(by_event.items()):
        d = _event_date(erows)
        eid = f"lsic_{d}"
        if eid in used_ids:                      # two meetings same day → disambiguate
            eid = f"lsic_{d}_{site_eid}"
        used_ids.add(eid)
        folder = DOWNLOADS / eid

        assets: list[Asset] = []
        # --- videos ---
        yt_rows = [r for r in erows if r["kind"] == "youtube"]
        by_vid: dict[str, list[dict]] = defaultdict(list)
        for r in yt_rows:
            by_vid[r["yt_video_id"]].append(r)
        for order, (vid, vrows) in enumerate(sorted(by_vid.items())):
            pres = sorted(vrows, key=lambda r: _t_offset(r["url"]))
            windows = []
            for i, p in enumerate(pres):
                start = _t_offset(p["url"])
                end = _t_offset(pres[i + 1]["url"]) if i + 1 < len(pres) else None
                windows.append({"t_start": start, "t_end": end, "title": p["title"],
                                "speaker": p["speaker"], "row_id": p["row_id"]})
            m = _asset_meta(pres[0]) | {"order": order, "yt_video_id": vid,
                                        "presentations": windows}
            clean = pres[0]["url"].split("&")[0].split("?t=")[0]
            assets.append(Asset(kind="video", source_url=clean, meta=m))
        for order, r in enumerate(r for r in erows if r["kind"] == "video_file"):
            assets.append(Asset(kind="video", lsic_id=r["lsic_id"], source_url=r["url"],
                                meta=_asset_meta(r) | {"order": order}))
        # --- docs (moved into the event folder) ---
        for r in erows:
            if r["kind"] in ("pdf", "pptx"):
                fn = r["target_filename"]
                if move_docs:
                    _relocate(DOWNLOADS / fn, folder / fn)
                assets.append(Asset(kind=_kind(r), lsic_id=r["lsic_id"],
                                    path=folder / fn, source_url=r["url"], meta=_asset_meta(r)))

        ev_meta = {
            "site_event_id": site_eid,
            "event_name": erows[0]["event_name"],
            "date": d,
            "category": erows[0]["category"],
            "topics": sorted({t for r in erows for t in (r.get("topics") or [])}),
            "speakers": sorted({r["speaker"] for r in erows if r["speaker"]}),
            "n_videos": sum(1 for a in assets if a.kind == "video"),
        }
        try:
            ev_date = date.fromisoformat(d)
        except ValueError:
            ev_date = date(1970, 1, 1)
        events.append(Event(event_id=eid, date=ev_date, assets=assets, meta=ev_meta))

        # durable per-event ledger (survives video deletion)
        meta_dir = WORK / "events" / eid
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "meta.json").write_text(json.dumps(
            {"event": ev_meta, "assets": [a.meta for a in assets]}, indent=2, ensure_ascii=False))

    WORK.mkdir(exist_ok=True)
    (WORK / "events.json").write_text(json.dumps(
        {"events": [e.model_dump(mode="json") for e in events], "papers": []},
        indent=2, default=str, ensure_ascii=False))
    return {"events": events}


def _relocate(src: Path, dst: Path) -> None:
    """Move a flat doc into its event folder (idempotent; no-op if already placed)."""
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(dst))


if __name__ == "__main__":
    ids = set(sys.argv[1:]) or None
    result = build(ids)
    print(f"[group_manifest] wrote work/events.json — {len(result['events'])} events")
    for e in result["events"]:
        kinds = Counter(a.kind for a in e.assets)
        nv = sum(1 for a in e.assets if a.kind == "video")
        print(f"  {e.event_id:22} {dict(kinds)}  videos={nv}  {e.meta['event_name'][:40]}")
