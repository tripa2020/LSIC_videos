"""Fakes-only tests for RUNEASY — the one-command multi-video front door.

Contract under test
- _parse_links: strict template (one URL/line, # comments, blanks ignored, dupes dropped).
- run_adhoc_list (CR1 — the ONE loop): per-URL no-drop; skip-completed resume (notes.md in
  the subfolder = done; --redo overrides); PROGRESS as it goes + BATCH_DONE at the end;
  tally with the EVAL gate column reported-not-enforced; exit 0 despite failures.
- main dispatch: --source-list defaults to links.txt, routes remote by default and local
  with --local, bakes the lecture profile and the Report_all default out.
- remote batch (CR2/CR6): links travel as a PUSHED FILE (never ssh argv); the VM runs the
  SAME loop (--source-list --local); done-test is the BATCH_DONE sentinel; the deadline
  scales with list length; REMOTE_OUT is not wiped (resume needs it).
"""
import json
import sys
from pathlib import Path

import pytest

from src import adhoc


# ---------- _parse_links ----------

def test_parse_links_strict_template():
    text = ("# my ten talks\n"
            "https://youtu.be/aaa\n"
            "\n"
            "  https://youtu.be/bbb  \n"
            "https://youtu.be/aaa\n"          # duplicate → dropped
            "# trailing comment\n")
    assert adhoc._parse_links(text) == ["https://youtu.be/aaa", "https://youtu.be/bbb"]


def test_parse_links_empty_doc():
    assert adhoc._parse_links("# nothing here\n\n") == []


def test_parse_links_tolerates_commas_on_one_line():
    # observed in Alex's real list.txt: two URLs comma-separated on one line
    text = "https://youtu.be/aaa\nhttps://youtu.be/bbb, https://youtu.be/ccc\n"
    assert adhoc._parse_links(text) == [
        "https://youtu.be/aaa", "https://youtu.be/bbb", "https://youtu.be/ccc"]


def test_subject_slug():
    assert adhoc._slug("How I Use LLMs! (2026)") == "How_I_Use_LLMs_2026"
    assert adhoc._slug("") == ""


# ---------- the loop ----------

def _links(tmp_path, urls):
    f = tmp_path / "links.txt"
    f.write_text("\n".join(urls) + "\n")
    return f


def test_loop_no_drop_and_tally(tmp_path, capsys):
    urls = [f"https://www.youtube.com/watch?v=vid{i}0000000" for i in range(3)]
    calls = []
    def fake_run(url, *, out, profile, work_root):
        calls.append(url)
        if "vid1" in url:
            raise RuntimeError("boom")       # poisoned middle video
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "notes.md").write_text("n")
        return 0
    rc = adhoc.run_adhoc_list(_links(tmp_path, urls), out=tmp_path / "batch",
                              run_one=fake_run, meta_fetcher=lambda u: None)
    outp = capsys.readouterr().out
    assert rc == 0                                          # failures live in the tally
    assert len(calls) == 3                                  # no-drop: all three attempted
    assert "✅ 2 ok" in outp and "❌ 1 failed" in outp
    assert (tmp_path / "batch" / "BATCH_DONE").exists()


def test_loop_skip_completed_resume(tmp_path, capsys):
    urls = ["https://www.youtube.com/watch?v=vid00000000", "https://www.youtube.com/watch?v=vid11111111"]
    from datetime import date
    done_vid = adhoc.mint_event_id(None, urls[0], date.today())
    pre = tmp_path / "batch" / done_vid
    pre.mkdir(parents=True)
    (pre / "notes.md").write_text("already done")
    calls = []
    def fake_run(url, *, out, profile, work_root):
        calls.append(url)
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "notes.md").write_text("n")
        return 0
    adhoc.run_adhoc_list(_links(tmp_path, urls), out=tmp_path / "batch", run_one=fake_run, meta_fetcher=lambda u: None)
    assert calls == [urls[1]]                               # completed one skipped
    assert "SKIP" in capsys.readouterr().out
    assert (pre / "notes.md").read_text() == "already done"  # untouched


def test_loop_redo_overrides_skip(tmp_path):
    url = "https://www.youtube.com/watch?v=vid00000000"
    from datetime import date
    vid = adhoc.mint_event_id(None, url, date.today())
    pre = tmp_path / "batch" / vid
    pre.mkdir(parents=True)
    (pre / "notes.md").write_text("stale")
    calls = []
    adhoc.run_adhoc_list(_links(tmp_path, [url]), out=tmp_path / "batch", redo=True,
                         run_one=lambda u, **kw: calls.append(u) or 0, meta_fetcher=lambda u: None)
    assert calls == [url]                                   # --redo re-runs it


def test_loop_writes_progress_and_gate_column(tmp_path, capsys):
    url = "https://www.youtube.com/watch?v=vid00000000"
    from datetime import date
    vid = adhoc.mint_event_id(None, url, date.today())
    progress_seen = {}
    def fake_run(u, *, out, profile, work_root):
        progress_seen["during"] = (tmp_path / "batch" / "PROGRESS").read_text()
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "notes.md").write_text("n")
        (Path(out) / "coverage_report.json").write_text(
            json.dumps({"gates": {"a": True, "b": True, "c": False}}))
        return 0
    adhoc.run_adhoc_list(_links(tmp_path, [url]), out=tmp_path / "batch", run_one=fake_run, meta_fetcher=lambda u: None)
    assert progress_seen["during"].startswith(f"1/1 {vid}")
    assert f"✅ {vid}  gates 2/3" in capsys.readouterr().out   # reported, not enforced


def test_subject_becomes_folder_name(tmp_path):
    url = "https://www.youtube.com/watch?v=vid00000000"
    made = []
    def fake_run(u, *, out, profile, work_root):
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "notes.md").write_text("n")
        made.append(Path(out).name)
        return 0
    adhoc.run_adhoc_list(_links(tmp_path, [url]), out=tmp_path / "batch", run_one=fake_run,
                         meta_fetcher=lambda u: {"title": "Digital Ghosts: a talk!"})
    from datetime import date
    vid = adhoc.mint_event_id(None, url, date.today())
    assert made == [f"Digital_Ghosts_a_talk__{vid}"]        # subject IS the folder header


def test_resume_matches_titled_folder(tmp_path, capsys):
    url = "https://www.youtube.com/watch?v=vid00000000"
    from datetime import date
    vid = adhoc.mint_event_id(None, url, date.today())
    pre = tmp_path / "batch" / f"Some_Subject__{vid}"       # completed on a prior run
    pre.mkdir(parents=True)
    (pre / "notes.md").write_text("done")
    adhoc.run_adhoc_list(_links(tmp_path, [url]), out=tmp_path / "batch",
                         run_one=lambda u, **kw: pytest.fail("must skip the completed video"),
                         meta_fetcher=lambda u: {"title": "Some Subject"})
    assert "SKIP" in capsys.readouterr().out


def test_loop_empty_links_is_loud(tmp_path, capsys):
    f = tmp_path / "links.txt"
    f.write_text("# nothing\n")
    assert adhoc.run_adhoc_list(f, out=tmp_path / "batch", meta_fetcher=lambda u: None) == 1
    assert "no links" in capsys.readouterr().out


# ---------- main dispatch ----------

def test_main_source_list_defaults_to_remote_and_links_txt(monkeypatch, tmp_path):
    from src import main as main_mod, remote
    monkeypatch.chdir(tmp_path)
    (tmp_path / "links.txt").write_text("https://youtu.be/x\n")
    seen = {}
    monkeypatch.setattr(remote, "remote_run",
                        lambda source, **kw: seen.update(kw, source=source) or 0)
    monkeypatch.setattr(sys, "argv", ["prog", "--source-list"])
    assert main_mod.main() == 0
    assert seen["source"] is None
    assert seen["source_list"] == Path("links.txt")         # zero-arg default (run_all)
    assert seen["profile"] == "lecture"                     # baked default
    assert seen["out"] == Path("Report_all")


def test_main_missing_links_file_greets_not_tracebacks(monkeypatch, tmp_path, capsys):
    from src import main as main_mod
    monkeypatch.setattr(sys, "argv", ["prog", "--source-list", str(tmp_path / "nope.txt")])
    assert main_mod.main() == 1
    assert "links file not found" in capsys.readouterr().out


def test_main_source_list_local_routes_to_the_loop(monkeypatch, tmp_path):
    from src import main as main_mod
    f = _links(tmp_path, ["https://youtu.be/x"])
    seen = {}
    monkeypatch.setattr(adhoc, "run_adhoc_list",
                        lambda lf, **kw: seen.update(kw, list_file=lf) or 0)
    monkeypatch.setattr(sys, "argv",
                        ["prog", "--source-list", str(f), "--local", "--redo"])
    assert main_mod.main() == 0
    assert seen["list_file"] == Path(f) and seen["redo"] is True
