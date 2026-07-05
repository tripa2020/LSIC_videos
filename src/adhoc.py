"""Ad-hoc input adapter — turn one YouTube URL or local video file into an Event and run
the full pipeline, optionally copying the Report bundle to a chosen folder.

The third ``events.json`` producer (alongside ``discover.py`` and ``group_manifest.py``). It
mints one Event + one video Asset, merges it NON-DESTRUCTIVELY into ``work/events.json`` (so it
never disturbs LSIC events), then reuses ``main.pipeline_cmd`` unchanged. Acquisition is already
general: ``ingest._fetch_youtube`` handles any YouTube URL, ``_fetch_http`` other URLs, and a
local file path is used directly. The one network call (yt-dlp metadata) is isolated behind an
injectable ``runner`` so the adapter is unit-tested with zero network.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from src import contracts, util

WORK_ROOT = Path("work")

_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")


def is_youtube(s: str) -> bool:
    """Match ingest's own substring test so acquisition and id-minting agree."""
    return "youtu.be" in s or "youtube.com" in s


def _youtube_id(url: str) -> Optional[str]:
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None


def mint_event_id(meta: Optional[dict], source: str, on_date: date) -> str:
    """Deterministic, slug-clean event_id (event dirs are work/events/<id>/, so it must be a
    clean slug). YouTube → ``yt_<videoid>`` (stable → idempotent re-runs); local file →
    ``adhoc_<slug(stem)>_<date>``; unparseable URL → ``adhoc_<slug>_<date>``."""
    if is_youtube(source):
        vid = (meta or {}).get("yt_video_id") or _youtube_id(source)
        if vid:
            return f"yt_{vid}"
        return f"adhoc_{util.slugify(source)[:24]}_{on_date.isoformat()}"
    return f"adhoc_{util.slugify(Path(source).stem)}_{on_date.isoformat()}"


def fetch_youtube_meta(url: str, runner: Callable = subprocess.run) -> Optional[dict]:
    """yt-dlp metadata probe (no download). Returns a small dict or ``None`` on ANY failure
    (caller degrades to a URL-regex id). ``--no-playlist`` collapses watch?list=/playlist URLs
    to the single video. ``runner`` is injectable so tests pass a fake — no network."""
    try:
        cp = runner(
            [sys.executable, "-m", "yt_dlp", "--dump-single-json",
             "--skip-download", "--no-playlist", url],
            check=True, capture_output=True, text=True,
        )
        d = json.loads(cp.stdout)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    return {
        "yt_video_id": d.get("id"),
        "title": d.get("title"),
        "uploader": d.get("uploader"),
        "upload_date": d.get("upload_date"),   # YYYYMMDD
        "duration": d.get("duration"),
        "url": d.get("webpage_url") or url,
        "chapters": d.get("chapters") or [],   # [{title, start_time}] → lecture Outline
        "description": d.get("description") or "",   # → lecture description-link references
    }


def _parse_upload_date(s: Optional[str]) -> Optional[date]:
    if s and len(s) == 8 and s.isdigit():
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None
    return None


def build_adhoc_event(source: str, *, meta_fetcher: Callable = fetch_youtube_meta,
                      on_date: Optional[date] = None) -> contracts.Event:
    """URL or local file → a single-video Event. Pure given the injected ``meta_fetcher``.
    A local file is resolved + existence-checked BEFORE any events.json mutation (fail fast)."""
    on_date = on_date or date.today()
    if is_youtube(source):
        meta = meta_fetcher(source)
        event_id = mint_event_id(meta, source, on_date)
        asset = contracts.Asset(
            kind="video", source_url=source,
            meta=meta or {"url": source, "yt_video_id": _youtube_id(source)})
        event_date = _parse_upload_date((meta or {}).get("upload_date")) or on_date
        title = (meta or {}).get("title")
    else:
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"ad-hoc source not found: {source}")
        event_id = mint_event_id(None, str(path), on_date)
        asset = contracts.Asset(kind="video", path=path, meta={"source": str(path)})
        event_date = on_date
        title = path.stem
    return contracts.Event(
        event_id=event_id, date=event_date, assets=[asset],
        meta={"adhoc": True, "source": source, "title": title})


def append_event(event: contracts.Event, work_root: Path = WORK_ROOT) -> None:
    """Non-clobbering merge into events.json: replace-by-event_id (idempotent re-run), preserve
    every existing event and the ``papers`` list. Atomic write — a kill mid-write can't corrupt
    the LSIC events.json (the .tmp is never promoted)."""
    path = work_root / "events.json"
    raw = json.loads(path.read_text()) if path.exists() else {"events": [], "papers": []}
    raw.setdefault("events", [])
    raw.setdefault("papers", [])
    raw["events"] = [e for e in raw["events"] if e.get("event_id") != event.event_id]
    raw["events"].append(event.model_dump(mode="json"))
    util.atomic_write_text(
        path, json.dumps(raw, indent=2, default=str, ensure_ascii=False))


def run_adhoc(source: str, *, out: Optional[Path] = None, profile: Optional[str] = None,
              work_root: Path = WORK_ROOT) -> int:
    """Build the event, register it, run the full pipeline, optionally copy Report → ``out``."""
    from src import main as main_mod, report as report_mod
    event = build_adhoc_event(source)
    if profile:
        event.meta = {**(event.meta or {}), "profile": profile}
    append_event(event, work_root=work_root)
    print(f"[adhoc] {source} → event {event.event_id}", flush=True)
    # ad-hoc enriches by default (request #3 is the whole point for new sources); degrades
    # to a skip-stub when offline.
    rc = main_mod.pipeline_cmd(event.event_id, all_flag=False, profile=profile, references=True)
    if rc == 0 and out is not None:
        report_mod.assemble_report(event.event_id, work_root=work_root, dest_dir=Path(out))
    return rc


# ── RUNEASY: the one-command multi-video front door ────────────────────────────────────────────

def _parse_links(text: str) -> list[str]:
    """links.txt template: one URL per line (comma-separated URLs on a line are tolerated —
    observed in Alex's real list); blank lines and ``#`` comments ignored; duplicates dropped
    (the same URL twice is one cached event anyway). A function, not a module (CR4)."""
    urls: list[str] = []
    for raw in text.replace(",", "\n").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line not in urls:
            urls.append(line)
    return urls


def _slug(title: str, max_len: int = 60) -> str:
    """Filesystem-safe subject slug for the output folder name."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", title or "").strip("_")
    return s[:max_len].rstrip("_")


def run_adhoc_list(list_file: Path, *, out: Path, profile: str = "lecture",
                   redo: bool = False, work_root: Path = WORK_ROOT,
                   run_one: Optional[Callable] = None,
                   meta_fetcher: Callable = fetch_youtube_meta) -> int:
    """The ONE list loop (CR1) — this same code runs locally and, in remote mode, ON the VM
    (`--source-list … --local`). Per-URL no-drop (a failing video logs ❌ and the loop
    continues — FIX semantics); **skip-completed resume** (a subfolder with notes.md is done;
    ``redo`` overrides); writes ``PROGRESS`` (`n/total <folder>`) as it goes and a
    ``BATCH_DONE`` sentinel at the end — the remote poller's whole interface (CR2/CR3).
    The output subfolder is named by the video's SUBJECT (`<title-slug>__<video_id>` — Alex
    2026-07-05; a one-probe metadata fetch, and the id suffix keeps resume deterministic even
    if the probe fails offline: resume matches any `*<video_id>` folder). Exit is 0 with
    failures reported in the tally, never a batch-aborting code."""
    run_one = run_one or run_adhoc
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    urls = _parse_links(Path(list_file).read_text())
    if not urls:
        print(f"[run-all] no links found in {list_file}", flush=True)
        return 1
    total, results = len(urls), []          # results: (folder_name, "ok"|"skip"|"fail")
    for i, url in enumerate(urls, 1):
        meta = meta_fetcher(url) if is_youtube(url) else None
        vid = mint_event_id(meta, url, date.today())
        slug = _slug((meta or {}).get("title") or "")
        sub = out / (f"{slug}__{vid}" if slug else vid)
        (out / "PROGRESS").write_text(f"{i}/{total} {sub.name}\n")
        if not redo and any((d / "notes.md").exists() for d in out.glob(f"*{vid}")):
            print(f"[run-all] {i}/{total} {sub.name} … SKIP (already complete)", flush=True)
            results.append((sub.name, "skip"))
            continue
        print(f"[run-all] {i}/{total} {sub.name} ← {url}", flush=True)
        try:
            rc = run_one(url, out=sub, profile=profile, work_root=work_root)
        except Exception as e:              # no-drop: one bad video never kills the batch
            print(f"[run-all] ❌ {sub.name} ({type(e).__name__}: {e})", flush=True)
            rc = 1
        results.append((sub.name, "ok" if rc == 0 else "fail"))
    _print_batch_summary(out, results)
    (out / "BATCH_DONE").write_text("done\n")
    return 0


def _gates_of(sub: Path) -> str:
    """EVAL gate column for the tally — reported, not enforced (Q2)."""
    try:
        g = json.loads((sub / "coverage_report.json").read_text())["gates"]
        return f"{sum(g.values())}/{len(g)}"
    except Exception:
        return "-"


def _print_batch_summary(out: Path, results: list[tuple[str, str]]) -> None:
    mark = {"ok": "✅", "skip": "⏭", "fail": "❌"}
    n = {s: sum(1 for _, r in results if r == s) for s in ("ok", "skip", "fail")}
    print(f"[run-all] done — ✅ {n['ok']} ok · ⏭ {n['skip']} skipped · ❌ {n['fail']} failed",
          flush=True)
    for vid, r in results:
        print(f"  {mark[r]} {vid}  gates {_gates_of(out / vid)}", flush=True)
