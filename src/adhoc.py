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
_ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(v\d+)?", re.I)


def is_youtube(s: str) -> bool:
    """Match ingest's own substring test so acquisition and id-minting agree."""
    return "youtu.be" in s or "youtube.com" in s


def is_paper_source(s: str) -> bool:
    """Any arXiv link, or a .pdf URL / local .pdf path → the paper flow."""
    if "arxiv.org" in s:
        return True
    return s.split("?", 1)[0].split("#", 1)[0].lower().endswith(".pdf")


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


# ── papers: PDF / arXiv sources ────────────────────────────────────────────────────────────────

def paper_id_of(source: str) -> str:
    """Deterministic, date-free event_id for a paper (stable → idempotent re-runs and
    cross-day resume). arXiv → ``paper_arxiv_<id>``; anything else → ``paper_<slug(stem)>``."""
    m = _ARXIV_ID_RE.search(source)
    if m:
        return f"paper_arxiv_{m.group(1).replace('.', '_')}"
    stem = Path(source.split("?", 1)[0].split("#", 1)[0]).stem
    return f"paper_{util.slugify(stem)[:40]}"


def _paper_date(source: str) -> Optional[date]:
    """arXiv ids encode YYMM — a truer event date than 'today'. Non-arXiv → None."""
    m = _ARXIV_ID_RE.search(source)
    if m and 1 <= int(m.group(1)[2:4]) <= 12:
        return date(2000 + int(m.group(1)[:2]), int(m.group(1)[2:4]), 1)
    return None


def _pdf_url(source: str) -> str:
    """Normalize arXiv abs/html links to the PDF endpoint; other URLs pass through."""
    m = _ARXIV_ID_RE.search(source)
    if m:
        return f"https://arxiv.org/pdf/{m.group(1)}{m.group(2) or ''}"
    return source


def _pdf_title(path: Path) -> str:
    """Title for the output-folder slug: PDF metadata, else the first plausible line of page 1
    (arXiv PDFs rarely set metadata). Any failure → "" (caller falls back to the stem)."""
    try:
        import fitz
        doc = fitz.open(str(path))
        try:
            t = ((doc.metadata or {}).get("title") or "").strip()
            first_page = doc[0].get_text() if len(doc) else ""
        finally:
            doc.close()
        if t:
            return t
        for line in first_page.splitlines():
            s = line.strip()
            if len(s) >= 8 and not s.lower().startswith("arxiv:"):
                return s[:120]
    except Exception:
        pass
    return ""


def _fetch_pdf_http(url: str, dest: Path) -> None:
    from src import ingest
    ingest._fetch_http(url, dest)


def fetch_paper(source: str, *, work_root: Path = WORK_ROOT,
                fetcher: Optional[Callable] = None) -> tuple[Path, dict]:
    """PDF URL or local path → (local pdf, {paper_id, title, date}). The download is cached
    under ``work/adhoc_sources/<paper_id>.pdf`` so the list-probe (folder naming) and the run
    itself share one fetch. ``fetcher`` is injectable — tests never touch the network."""
    pid = paper_id_of(source)
    if source.startswith(("http://", "https://")):
        dest = Path(work_root) / "adhoc_sources" / f"{pid}.pdf"
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            (fetcher or _fetch_pdf_http)(_pdf_url(source), dest)
    else:
        dest = Path(source).expanduser().resolve()
        if not dest.is_file():
            raise FileNotFoundError(f"ad-hoc paper not found: {source}")
    title = _pdf_title(dest) or dest.stem
    return dest, {"paper_id": pid, "title": title, "date": _paper_date(source)}


def build_adhoc_paper_event(source: str, pdf_path: Path, meta: dict) -> contracts.Event:
    """PDF → single-asset Event. The asset is minted ``kind="host_deck"`` (not ``"paper"``) so
    ingest extracts it into ``01_ingest/decks/`` — the directory ``paper_align`` and
    ``slide_book`` already read; zero edits to ingest routing."""
    asset = contracts.Asset(
        kind="host_deck", path=pdf_path, lsic_id=1,
        source_url=source if source.startswith("http") else None,
        meta={"source": source, "title": meta.get("title")})
    return contracts.Event(
        event_id=meta["paper_id"], date=meta.get("date") or date.today(), assets=[asset],
        meta={"adhoc": True, "paper": True, "source": source,
              "title": meta.get("title"), "profile": "paper"})


def run_adhoc_paper(source: str, *, out: Optional[Path] = None, work_root: Path = WORK_ROOT,
                    fetcher: Optional[Callable] = None) -> int:
    """Paper twin of ``run_adhoc``: fetch → ingest → page-anchored align → paper-profile
    synthesis (+eval) → references → slide_book → Report. Chains the stage functions directly
    because ``pipeline_cmd`` is (correctly) gated on events having video; every stage keeps
    its own skip-when-complete contract, so re-runs are cheap and crash-resumable."""
    from src import main as main_mod, paper_align, report as report_mod, synthesize as synth_mod
    pdf_path, meta = fetch_paper(source, work_root=work_root, fetcher=fetcher)
    event = build_adhoc_paper_event(source, pdf_path, meta)
    append_event(event, work_root=work_root)
    print(f"[adhoc] {source} → paper event {event.event_id} ({meta.get('title')})", flush=True)
    if (rc := main_mod.ingest_cmd(event.event_id, all_flag=False)) != 0:
        return rc
    paper_align.align_paper(event.event_id, work_root=work_root)
    synth_mod.synthesize_full(event.event_id, work_root=work_root, profile="paper")
    main_mod.enrich_cmd(event.event_id)      # related-paper references; skip-stub offline
    main_mod.slide_book_cmd(event.event_id)  # page curation → slides.pdf + equations.md
    if (rc := main_mod.report_cmd(event.event_id)) != 0:
        return rc
    if out is not None:
        report_mod.assemble_report(event.event_id, work_root=work_root, dest_dir=Path(out))
    return 0


def run_adhoc(source: str, *, out: Optional[Path] = None, profile: Optional[str] = None,
              work_root: Path = WORK_ROOT) -> int:
    """Build the event, register it, run the full pipeline, optionally copy Report → ``out``."""
    from src import main as main_mod, report as report_mod
    if is_paper_source(source):   # papers bake their own template; ``profile`` is video-only
        return run_adhoc_paper(source, out=out, work_root=work_root)
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
                   meta_fetcher: Callable = fetch_youtube_meta,
                   paper_fetcher: Optional[Callable] = None) -> int:
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
        if is_paper_source(url):
            # papers probe by downloading (cached — the run reuses the same file); the id is
            # date-free so resume matches across days even when the probe fails offline
            try:
                _, meta = fetch_paper(url, work_root=work_root, fetcher=paper_fetcher)
            except Exception as e:
                print(f"[run-all] paper probe failed for {url} "
                      f"({type(e).__name__}: {e})", flush=True)
                meta = {"paper_id": paper_id_of(url)}
            vid = meta["paper_id"]
        else:
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
