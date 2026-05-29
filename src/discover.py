"""Stage 0: scan LSIC_Downloads/, cluster files into events, classify assets.

Clustering rule: sort by LSIC ID, walk the list, split when ID gap > 3.
Classification (per-file, in order):
  *.mp4              → video
  *SPCAslides*       → host_deck
  *notes*.pdf        → notes
  *.pptx | *.pdf     → presentation (provisional; reclassified after cluster)

Post-cluster: a cluster is an "event" if any asset is video/host_deck/notes.
Otherwise its presentations are reclassified to paper and pulled out as
standalone papers.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from src.contracts import Asset, AssetKind, Event


WORK_ROOT = Path("work")
ID_GAP_THRESHOLD = 3   # tighter than 10 so standalone papers (e.g. 2994) split out

_LSIC_PREFIX_RE = re.compile(r"^(\d+)-")
_YYYYMMDD_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")
_YEAR_MONTH_RE = re.compile(
    r"(20\d{2})\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\b", re.IGNORECASE,
)
_MONTH_YEAR_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(20\d{2})", re.IGNORECASE,
)
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def discover(folder: Path) -> dict:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"{folder} not a directory")

    seen: dict[str, Asset] = {}
    for f in sorted(folder.iterdir()):
        if f.name.startswith(".") or not f.is_file():
            continue
        lsic_id = _parse_lsic_id(f.name)
        if lsic_id is None:
            continue
        digest = _sha256(f, prefix=12)
        if digest in seen:
            continue  # dedup (catches 3178 ×2)
        seen[digest] = Asset(
            kind=_classify(f),
            path=f,
            sha256=digest,
            lsic_id=lsic_id,
            date_in_filename=_parse_date(f.name),
        )

    clusters = _cluster(list(seen.values()))

    events: list[Event] = []
    papers: list[Asset] = []
    for cluster in clusters:
        is_event = any(
            a.kind in ("video", "host_deck", "notes") for a in cluster
        )
        if is_event:
            events.append(_make_event(cluster))
        else:
            for a in cluster:
                if a.kind == "presentation":
                    papers.append(a.model_copy(update={"kind": "paper"}))
                else:
                    papers.append(a)

    WORK_ROOT.mkdir(exist_ok=True)
    out = WORK_ROOT / "events.json"
    out.write_text(json.dumps(
        {
            "events": [e.model_dump(mode="json") for e in events],
            "papers": [p.model_dump(mode="json") for p in papers],
        },
        indent=2,
        default=str,
    ))
    return {"events": events, "papers": papers}


def _classify(path: Path) -> AssetKind:
    name = path.name.lower()
    ext = path.suffix.lower()
    if ext == ".mp4":
        return "video"
    if "spcaslides" in name:
        return "host_deck"
    if ext == ".pdf" and "notes" in name:
        return "notes"
    if ext in (".pptx", ".pdf"):
        return "presentation"  # provisional — reclassified to paper if cluster has no anchor
    return "presentation"


def _parse_lsic_id(name: str) -> Optional[int]:
    m = _LSIC_PREFIX_RE.match(name)
    return int(m.group(1)) if m else None


def _sha256(path: Path, prefix: int = 12) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:prefix]


def _parse_date(name: str) -> Optional[date]:
    m = _YYYYMMDD_RE.search(name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = _YEAR_MONTH_RE.search(name)
    if m:
        try:
            return date(int(m.group(1)), _MONTHS[m.group(2).lower()], 1)
        except (KeyError, ValueError):
            pass
    m = _MONTH_YEAR_RE.search(name)
    if m:
        try:
            return date(int(m.group(2)), _MONTHS[m.group(1).lower()], 1)
        except (KeyError, ValueError):
            pass
    return None


def _cluster(assets: list[Asset]) -> list[list[Asset]]:
    if not assets:
        return []
    s = sorted(assets, key=lambda a: a.lsic_id)
    clusters: list[list[Asset]] = [[s[0]]]
    for prev, curr in zip(s, s[1:]):
        if curr.lsic_id - prev.lsic_id > ID_GAP_THRESHOLD:
            clusters.append([curr])
        else:
            clusters[-1].append(curr)
    return clusters


def _make_event(cluster: list[Asset]) -> Event:
    dates = [a.date_in_filename for a in cluster if a.date_in_filename]
    if dates:
        # prefer day-precision dates over month-only (day=1)
        high_precision = [d for d in dates if d.day != 1]
        ref = min(high_precision) if high_precision else min(dates)
        event_id = (
            f"lsic_{ref.year:04d}-{ref.month:02d}"
            if all(d.day == 1 for d in dates)
            else f"lsic_{ref.isoformat()}"
        )
    else:
        ref = date(1970, 1, 1)
        event_id = f"lsic_id_{cluster[0].lsic_id}"
    return Event(event_id=event_id, date=ref, assets=cluster, duration_sec=None)


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("LSIC_Downloads")
    result = discover(target)
    print(f"events: {len(result['events'])}, papers: {len(result['papers'])}")
    for e in result["events"]:
        kinds = ", ".join(a.kind for a in e.assets)
        print(f"  {e.event_id}: {len(e.assets)} assets [{kinds}]")
    for p in result["papers"]:
        print(f"  paper {p.lsic_id}: {p.path.name}")
