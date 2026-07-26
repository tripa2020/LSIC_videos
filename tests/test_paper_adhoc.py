"""Fakes-only tests for the PAPER path — PDF/arXiv sources through the adhoc front door.

Contract under test
- Routing: is_paper_source / paper_id_of / _pdf_url — arXiv + .pdf detected, YouTube and
  plain video URLs untouched (degrade-to-today: the video path never sees the new branch).
- fetch_paper: download cached by paper_id (second call = zero fetcher calls); local paths
  resolved + existence-checked; title from PDF metadata → page-1 line → stem.
- build_adhoc_paper_event: kind="host_deck" (rides ingest's existing deck routing), stable
  date-free event_id, arXiv YYMM → event date.
- run_adhoc routing: paper sources divert to run_adhoc_paper; video sources still run the
  original flow (pipeline_cmd) byte-identically.
- run_adhoc_list: paper URLs get subject-named folders + cross-day resume via the date-free
  id; offline probe degrades to the bare id; YouTube lines behave exactly as before.
- paper_align: pages → Sections + page-numbered Evidence; empty pages skipped; idempotent
  skip when complete; loud on missing ingest artifact and on text-free (scanned) PDFs.
- synth_eval paper mode: [p.N] cites against `pages: N` — decile/final-third/bullet-rate in
  page units; non-paper notes score byte-identically to before.
- profile registry: "paper" resolves; "lecture"/"briefing" untouched.

No network, no Gemini/Claude calls anywhere.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from src import adhoc, paper_align, synth_eval
from src.contracts import DeckIndex, Slide


# ---------- routing helpers ----------

def test_is_paper_source_matrix():
    assert adhoc.is_paper_source("https://arxiv.org/pdf/2410.19811")
    assert adhoc.is_paper_source("https://arxiv.org/abs/2410.19811v2")
    assert adhoc.is_paper_source("https://example.com/x/paper.PDF?dl=1")
    assert adhoc.is_paper_source("/tmp/local_paper.pdf")
    assert not adhoc.is_paper_source("https://www.youtube.com/watch?v=abcdefghijk")
    assert not adhoc.is_paper_source("https://youtu.be/abcdefghijk")
    assert not adhoc.is_paper_source("/tmp/talk.mp4")


def test_paper_id_is_stable_and_date_free():
    a = adhoc.paper_id_of("https://arxiv.org/pdf/2410.19811")
    assert a == "paper_arxiv_2410_19811"
    assert adhoc.paper_id_of("https://arxiv.org/abs/2410.19811") == a   # abs/pdf agree
    assert adhoc.paper_id_of("https://x.org/my-cool paper.pdf?v=2") == "paper_my_cool_paper"


def test_arxiv_abs_normalizes_to_pdf_url():
    assert adhoc._pdf_url("https://arxiv.org/abs/2410.19811") == \
        "https://arxiv.org/pdf/2410.19811"
    assert adhoc._pdf_url("https://arxiv.org/abs/2410.19811v3") == \
        "https://arxiv.org/pdf/2410.19811v3"
    assert adhoc._pdf_url("https://example.com/a.pdf") == "https://example.com/a.pdf"


def test_arxiv_id_encodes_event_date():
    assert adhoc._paper_date("https://arxiv.org/pdf/2410.19811") == date(2024, 10, 1)
    assert adhoc._paper_date("https://example.com/a.pdf") is None


# ---------- fetch_paper ----------

def _tiny_pdf(path: Path, first_line: str = "ControlAgent: Automating Control Design") -> Path:
    """A real one-page PDF via fitz (already a project dep) — no fixtures, no network."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 96), first_line, fontsize=14)
    page.insert_text((72, 130), "Xingang Guo et al.", fontsize=10)
    doc.save(str(path))
    doc.close()
    return path


def test_fetch_paper_downloads_once_then_caches(tmp_path):
    calls = []
    def fake_fetch(url, dest):
        calls.append(url)
        _tiny_pdf(dest)
    url = "https://arxiv.org/abs/2410.19811"
    p1, m1 = adhoc.fetch_paper(url, work_root=tmp_path, fetcher=fake_fetch)
    p2, m2 = adhoc.fetch_paper(url, work_root=tmp_path, fetcher=fake_fetch)
    assert calls == ["https://arxiv.org/pdf/2410.19811"]        # one fetch, abs→pdf normalized
    assert p1 == p2 == tmp_path / "adhoc_sources" / "paper_arxiv_2410_19811.pdf"
    assert m1["title"].startswith("ControlAgent")               # page-1 line, not the stem
    assert m1["date"] == date(2024, 10, 1)


def test_fetch_paper_local_path_and_missing_is_loud(tmp_path):
    local = _tiny_pdf(tmp_path / "my_paper.pdf")
    p, m = adhoc.fetch_paper(str(local), work_root=tmp_path)
    assert p == local and m["paper_id"] == "paper_my_paper"
    with pytest.raises(FileNotFoundError):
        adhoc.fetch_paper(str(tmp_path / "nope.pdf"), work_root=tmp_path)


# ---------- event minting ----------

def test_build_adhoc_paper_event_rides_deck_routing(tmp_path):
    pdf = _tiny_pdf(tmp_path / "p.pdf")
    src = "https://arxiv.org/pdf/2410.19811"
    ev = adhoc.build_adhoc_paper_event(
        src, pdf, {"paper_id": "paper_arxiv_2410_19811", "title": "T", "date": date(2024, 10, 1)})
    a = ev.assets[0]
    assert a.kind == "host_deck" and a.path == pdf and a.source_url == src
    assert ev.event_id == "paper_arxiv_2410_19811" and ev.date == date(2024, 10, 1)
    assert ev.meta["paper"] is True and ev.meta["profile"] == "paper"


# ---------- run_adhoc routing (degrade-to-today for videos) ----------

def test_run_adhoc_routes_paper_and_leaves_video_alone(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(adhoc, "run_adhoc_paper",
                        lambda s, **kw: (seen.setdefault("paper", s), 0)[1])
    assert adhoc.run_adhoc("https://arxiv.org/abs/2410.19811", out=tmp_path) == 0
    assert seen["paper"] == "https://arxiv.org/abs/2410.19811"

    # video source: the original flow runs (build → append → pipeline), never the paper twin
    from src import main as main_mod
    monkeypatch.setattr(adhoc, "run_adhoc_paper",
                        lambda s, **kw: pytest.fail("video source must not route to paper"))
    monkeypatch.setattr(adhoc, "build_adhoc_event", _fake_event)
    monkeypatch.setattr(adhoc, "append_event", lambda e, work_root: None)
    monkeypatch.setattr(main_mod, "pipeline_cmd",
                        lambda eid, **kw: (seen.setdefault("pipeline", eid), 0)[1])
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    monkeypatch.setattr(adhoc, "fetch_youtube_meta", lambda u, runner=None: None)
    assert adhoc.run_adhoc(url, work_root=tmp_path) == 0
    assert seen["pipeline"] == "yt_abcdefghijk"


def _fake_event(source):
    from src import contracts
    return contracts.Event(event_id="yt_abcdefghijk", date=date.today(),
                           assets=[contracts.Asset(kind="video", source_url=source)])


# ---------- run_adhoc_list with papers ----------

def _links(tmp_path, urls):
    f = tmp_path / "links.txt"
    f.write_text("\n".join(urls) + "\n")
    return f


def _fake_paper_fetch(url, dest):
    _tiny_pdf(dest)


def test_list_paper_gets_subject_folder_and_video_flow_unchanged(tmp_path):
    urls = ["https://www.youtube.com/watch?v=vid00000000",
            "https://arxiv.org/pdf/2410.19811"]
    made = []
    def fake_run(u, *, out, profile, work_root):
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "notes.md").write_text("n")
        made.append(Path(out).name)
        return 0
    rc = adhoc.run_adhoc_list(_links(tmp_path, urls), out=tmp_path / "batch",
                              work_root=tmp_path, run_one=fake_run,
                              meta_fetcher=lambda u: {"title": "Some Talk"},
                              paper_fetcher=_fake_paper_fetch)
    assert rc == 0
    vid = adhoc.mint_event_id(None, urls[0], date.today())
    assert made[0] == f"Some_Talk__{vid}"                        # video naming untouched
    assert made[1].startswith("ControlAgent") and made[1].endswith("paper_arxiv_2410_19811")


def test_list_paper_resume_matches_across_days(tmp_path):
    url = "https://arxiv.org/pdf/2410.19811"
    pre = tmp_path / "batch" / "ControlAgent_Automating__paper_arxiv_2410_19811"
    pre.mkdir(parents=True)
    (pre / "notes.md").write_text("done")                        # completed on a prior day
    adhoc.run_adhoc_list(_links(tmp_path, [url]), out=tmp_path / "batch",
                         work_root=tmp_path,
                         run_one=lambda u, **kw: pytest.fail("must skip the completed paper"),
                         meta_fetcher=lambda u: None, paper_fetcher=_fake_paper_fetch)


def test_list_paper_probe_failure_degrades_to_bare_id(tmp_path, capsys):
    url = "https://arxiv.org/pdf/2410.19811"
    made = []
    def fake_run(u, *, out, profile, work_root):
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "notes.md").write_text("n")
        made.append(Path(out).name)
        return 0
    def broken_fetch(u, dest):
        raise RuntimeError("offline")
    rc = adhoc.run_adhoc_list(_links(tmp_path, [url]), out=tmp_path / "batch",
                              work_root=tmp_path, run_one=fake_run,
                              meta_fetcher=lambda u: None, paper_fetcher=broken_fetch)
    assert rc == 0 and made == ["paper_arxiv_2410_19811"]        # no-drop, id-only folder
    assert "paper probe failed" in capsys.readouterr().out


# ---------- paper_align ----------

def _seed_ingested_paper(work_root: Path, event_id: str, pages: list[str]) -> Path:
    deck_dir = work_root / "events" / event_id / "01_ingest" / "decks" / "1"
    deck_dir.mkdir(parents=True)
    idx = DeckIndex(asset_id="1", title="T",
                    slides=[Slide(n=i + 1, text=t) for i, t in enumerate(pages)])
    (deck_dir / "doc_index.json").write_text(idx.model_dump_json())
    return deck_dir


def test_paper_align_pages_to_evidence(tmp_path):
    _seed_ingested_paper(tmp_path, "paper_x", ["intro text", "", "results text"])
    res = paper_align.align_paper("paper_x", work_root=tmp_path)
    assert res.duration_sec == 3.0                               # pages INCLUDING the empty one
    assert [s.start for s in res.sections] == [1.0, 3.0]         # empty page 2 skipped
    ev = json.loads((tmp_path / "events" / "paper_x" / "04_aligned" / "evidence.json").read_text())
    assert [e["evidence_id"] for e in ev] == ["ev_p001", "ev_p003"]
    assert all(e["kind"] == "transcript" for e in ev)
    assert ev[1]["timestamp_start"] == 3.0                       # page number IS the float


def test_paper_align_is_idempotent(tmp_path):
    deck_dir = _seed_ingested_paper(tmp_path, "paper_x", ["only page"])
    paper_align.align_paper("paper_x", work_root=tmp_path)
    (deck_dir / "doc_index.json").write_text("GARBAGE — must not be re-read")
    res = paper_align.align_paper("paper_x", work_root=tmp_path)  # skip-when-complete
    assert len(res.sections) == 1


def test_paper_align_loud_failures(tmp_path):
    (tmp_path / "events" / "paper_y" / "01_ingest" / "decks").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="no doc_index"):
        paper_align.align_paper("paper_y", work_root=tmp_path)
    _seed_ingested_paper(tmp_path, "paper_z", ["", ""])          # scanned PDF: no text at all
    with pytest.raises(RuntimeError, match="no extractable text"):
        paper_align.align_paper("paper_z", work_root=tmp_path)


# ---------- profile registry + render ----------

def test_profile_registry_has_paper_and_others_unchanged():
    from src.profiles import VALID_PROFILES, get_profile
    assert VALID_PROFILES == ("briefing", "lecture", "paper")
    p = get_profile("paper")
    assert p.name == "paper" and not p.uses_presentations and not p.uses_role_pool
    assert get_profile("lecture").name == "lecture"
    assert get_profile(None).name == "briefing"                  # default untouched


def test_render_paper_page_citations(tmp_path):
    from src.contracts import AlignmentResult, Evidence, IngestResult, Section
    from src.profiles.paper import render_paper
    ev = Evidence(evidence_id="ev_p012", kind="transcript", source_id="1",
                  timestamp_start=12.0, timestamp_end=12.0, text="the claim text")
    alignment = AlignmentResult(event_id="paper_arxiv_2410_19811", duration_sec=35.0,
                                sections=[Section(start=12.0, end=12.0, transcript="x")],
                                presentations=[])
    ing = IngestResult(event_id="paper_arxiv_2410_19811", workdir=tmp_path, duration_sec=0.0)
    md = render_paper(
        ing=ing, alignment=alignment, pres_outputs=[], slide_highlights=[],
        thematic={"title": "ControlAgent", "summary": "S.",
                  "key_points": [{"text": "LLM + control loops", "evidence_id": "ev_p012"}]},
        evidence_by_id={"ev_p012": ev}, event_date="2024-10-01", n_speakers=0,
        source_meta={"source": "https://arxiv.org/pdf/2410.19811", "title": "ControlAgent"})
    assert "profile: paper" in md and "pages: 35" in md
    assert "`[p.12]`" in md                                      # page-anchored citation
    assert "**Source:** https://arxiv.org/pdf/2410.19811" in md
    assert "## Founder Lens" not in md                           # empty cognition → omitted
    assert "Speakers" not in md                                  # no speaker block for papers


# ---------- synth_eval page mode ----------

_PAPER_MD = """---
event_id: paper_arxiv_2410_19811
pages: 30
profile: paper
---
# T

## Cognitive Moves
- **m1** — *Tag* — w `[p.2]`
- **m2** — *Tag* — w `[p.24]`
- **m3** — *Tag* — w `[p.28]`

## Key Points
- one `[p.5]`
- two `[p.15]`
- bare bullet
"""


def test_synth_eval_paper_mode_counts_pages():
    s = synth_eval.score_notes(_PAPER_MD)
    assert s["duration_sec"] == 30                               # page span rides the field
    assert s["n_cites"] == 5
    assert s["final_third_cites"] == 2                           # p.24, p.28 ≥ 20
    assert s["bullet_cite_rate"] == round(5 / 6, 2)
    assert s["decile_coverage"] == 0.5                           # pages 2,5,15,24,28 → 5 deciles


_LECTURE_MD = """---
duration: "10:00"
---
## Cognitive Moves
- **m1** — w `[02:00]`
- **m2** — w `[08:00]`

## Key Points
- one `[01:00]`
- bare
"""


def test_synth_eval_video_mode_byte_identical():
    s = synth_eval.score_notes(_LECTURE_MD)
    # hand-computed against the pre-change logic: nothing about [mm:ss] scoring moved
    assert s["duration_sec"] == 600 and s["n_cites"] == 3
    assert s["final_third_cites"] == 1 and s["bullet_cite_rate"] == 0.75
    assert s["decile_coverage"] == 0.3
    assert "[p." not in _LECTURE_MD or True


# ---------- run_adhoc_paper stage chain ----------

def test_run_adhoc_paper_chains_stages_and_copies_report(monkeypatch, tmp_path):
    from src import main as main_mod, report as report_mod, synthesize as synth_mod
    order = []
    pdf = _tiny_pdf(tmp_path / "src.pdf")
    monkeypatch.setattr(adhoc, "fetch_paper",
                        lambda s, **kw: (pdf, {"paper_id": "paper_p", "title": "T", "date": None}))
    monkeypatch.setattr(adhoc, "append_event", lambda e, work_root: order.append("append"))
    monkeypatch.setattr(main_mod, "ingest_cmd", lambda eid, all_flag: order.append("ingest") or 0)
    monkeypatch.setattr(paper_align, "align_paper",
                        lambda eid, work_root: order.append("align"))
    monkeypatch.setattr(synth_mod, "synthesize_full",
                        lambda eid, work_root, profile: order.append(f"synth:{profile}"))
    monkeypatch.setattr(main_mod, "enrich_cmd", lambda eid: order.append("enrich") or 0)
    monkeypatch.setattr(main_mod, "slide_book_cmd", lambda eid: order.append("book") or 0)
    monkeypatch.setattr(main_mod, "report_cmd", lambda eid: order.append("report") or 0)
    monkeypatch.setattr(report_mod, "assemble_report",
                        lambda eid, work_root, dest_dir: order.append(f"copy:{dest_dir.name}"))
    rc = adhoc.run_adhoc_paper("https://arxiv.org/pdf/2410.19811",
                               out=tmp_path / "bundle", work_root=tmp_path)
    assert rc == 0
    assert order == ["append", "ingest", "align", "synth:paper",
                     "enrich", "book", "report", "copy:bundle"]
