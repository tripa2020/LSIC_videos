"""Fakes-only, no-network tests for the ad-hoc input adapter (src/adhoc.py).

Contract under test
- Intent: turn one YouTube URL / local file into an Event, register it WITHOUT disturbing
  existing (LSIC) events, then run the pipeline; optionally copy the bundle to --out.
- Invariants: event_id is deterministic (idempotent re-runs); append never drops/corrupts
  existing events or papers; a missing local file raises BEFORE any events.json write;
  absent --out, report behavior is byte-identical to today.
- Equivalence classes: youtube (with/without fetched meta) · local-file (present/missing) ·
  metadata probe (ok/error) · events.json (empty/seeded) · --out (set/None).
- Oracles: explicit event_id strings, raised exceptions, reloaded events.json contents,
  files present on disk.
"""
import json
import subprocess
from datetime import date

import pytest

from src import adhoc, ingest, report

D = date(2026, 6, 11)


# ---------- event_id minting ----------

@pytest.mark.parametrize("url", [
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxyz",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
])
def test_mint_event_id_youtube_from_url(url):
    assert adhoc.mint_event_id(None, url, D) == "yt_dQw4w9WgXcQ"


def test_mint_event_id_youtube_prefers_meta():
    assert adhoc.mint_event_id({"yt_video_id": "abc12345678"}, "https://youtu.be/zzzzzzzzzzz", D) \
        == "yt_abc12345678"


def test_mint_event_id_local_is_clean_slug():
    eid = adhoc.mint_event_id(None, "/tmp/My Talk (Final).mp4", D)
    assert eid == "adhoc_my_talk_final_2026-06-11"
    assert " " not in eid and "(" not in eid


# ---------- build_adhoc_event ----------

def test_build_youtube_with_fake_fetcher():
    meta = {"yt_video_id": "abc12345678", "title": "T", "upload_date": "20260115"}
    ev = adhoc.build_adhoc_event("https://youtu.be/abc12345678",
                                 meta_fetcher=lambda u: meta, on_date=D)
    assert ev.event_id == "yt_abc12345678"
    assert len(ev.assets) == 1
    a = ev.assets[0]
    assert a.kind == "video" and a.source_url == "https://youtu.be/abc12345678" and a.path is None
    assert ev.meta["title"] == "T"
    assert ev.date == date(2026, 1, 15)          # from upload_date


def test_build_youtube_meta_none_degrades():
    ev = adhoc.build_adhoc_event("https://youtu.be/dQw4w9WgXcQ",
                                 meta_fetcher=lambda u: None, on_date=D)
    assert ev.event_id == "yt_dQw4w9WgXcQ"       # URL-regex fallback
    assert ev.assets[0].source_url.endswith("dQw4w9WgXcQ")
    assert ev.assets[0].meta["yt_video_id"] == "dQw4w9WgXcQ"
    assert ev.date == D                          # no upload_date → on_date


def test_build_local_file(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00\x00")
    ev = adhoc.build_adhoc_event(str(f), on_date=D)
    assert ev.event_id == "adhoc_clip_2026-06-11"
    assert ev.assets[0].path is not None and ev.assets[0].source_url is None


def test_build_local_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        adhoc.build_adhoc_event(str(tmp_path / "nope.mp4"), on_date=D)


# ---------- fetch_youtube_meta (injected runner) ----------

def test_fetch_youtube_meta_parses_stdout():
    payload = {"id": "abc12345678", "title": "T", "duration": 42, "upload_date": "20260115"}
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload))
    meta = adhoc.fetch_youtube_meta("https://youtu.be/abc12345678", runner=lambda *a, **k: fake)
    assert meta["yt_video_id"] == "abc12345678" and meta["title"] == "T" and meta["duration"] == 42


def test_fetch_youtube_meta_error_returns_none():
    def boom(*a, **k):
        raise subprocess.CalledProcessError(1, "yt-dlp")
    assert adhoc.fetch_youtube_meta("https://youtu.be/x", runner=boom) is None


# ---------- append_event (non-clobber) ----------

def _seed_events_json(work_root):
    (work_root).mkdir(parents=True, exist_ok=True)
    (work_root / "events.json").write_text(json.dumps({
        "events": [{"event_id": "lsic_2026-03-26", "date": "2026-03-26", "assets": [],
                    "duration_sec": None, "meta": {"event_name": "LSIC"}}],
        "papers": [{"kind": "paper", "lsic_id": 99}],
    }))


def test_append_preserves_existing_lsic(tmp_path):
    _seed_events_json(tmp_path)
    ev = adhoc.build_adhoc_event("https://youtu.be/abc12345678",
                                 meta_fetcher=lambda u: {"yt_video_id": "abc12345678"}, on_date=D)
    adhoc.append_event(ev, work_root=tmp_path)
    events, papers = ingest.load_events_json(work_root=tmp_path)
    ids = {e.event_id for e in events}
    assert ids == {"lsic_2026-03-26", "yt_abc12345678"}      # LSIC event preserved
    assert len(papers) == 1 and papers[0].lsic_id == 99       # papers untouched


def test_append_idempotent_replace(tmp_path):
    _seed_events_json(tmp_path)
    ev = adhoc.build_adhoc_event("https://youtu.be/abc12345678",
                                 meta_fetcher=lambda u: {"yt_video_id": "abc12345678"}, on_date=D)
    adhoc.append_event(ev, work_root=tmp_path)
    adhoc.append_event(ev, work_root=tmp_path)               # twice
    events, _ = ingest.load_events_json(work_root=tmp_path)
    assert [e.event_id for e in events].count("yt_abc12345678") == 1


def test_append_creates_when_absent(tmp_path):
    ev = adhoc.build_adhoc_event("https://youtu.be/abc12345678",
                                 meta_fetcher=lambda u: {"yt_video_id": "abc12345678"}, on_date=D)
    adhoc.append_event(ev, work_root=tmp_path)               # no pre-existing events.json
    events, papers = ingest.load_events_json(work_root=tmp_path)
    assert [e.event_id for e in events] == ["yt_abc12345678"] and papers == []


# ---------- report --out copy ----------

def _seed_briefing(work_root, event_id, names):
    d = work_root / "events" / event_id / "05_briefing"
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_text(f"# {n}\n")


def test_assemble_report_out_copies_bundle(tmp_path):
    _seed_briefing(tmp_path, "yt_x", ["notes.md", "slides.pdf"])   # equations/captions missing
    out = tmp_path / "delivered"
    report.assemble_report("yt_x", work_root=tmp_path, dest_dir=out)
    assert (tmp_path / "events" / "yt_x" / "Report" / "notes.md").exists()
    assert (out / "notes.md").exists() and (out / "slides.pdf").exists()
    assert not (out / "equations.md").exists()                     # missing skipped, not fatal


def test_assemble_report_no_dest_unchanged(tmp_path):
    _seed_briefing(tmp_path, "yt_x", ["notes.md"])
    report.assemble_report("yt_x", work_root=tmp_path)             # dest_dir=None
    # only the in-tree Report/ exists; no stray delivery folder created
    assert (tmp_path / "events" / "yt_x" / "Report" / "notes.md").exists()
    assert list(tmp_path.glob("delivered*")) == []
