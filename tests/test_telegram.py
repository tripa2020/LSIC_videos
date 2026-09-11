"""Fakes-only tests for src/telegram.py (inbox + delivery) and its run_adhoc_list wiring.

Contract under test
- Unconfigured (no token/chat) ⇒ every function is a no-op and the list loop is byte-identical.
- pull_links: URLs from the configured chat only; other chats ignored; pages past 100; the
  confirm call carries offset = last_update_id + 1 and happens AFTER links are returned.
- merge_into_links_file: append-only, dedup against the file, creates the file.
- send_bundle: sends the reader files that exist and are non-empty; skips missing/oversized;
  multipart carries chat_id + filename.
- run_adhoc_list: inbox merges before the loop; each ✅ delivers; delivery/inbox failures are
  logged and never change rc or the tally.
No network: ``http`` is injected everywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import adhoc, telegram


def _upd(uid, chat, text):
    return {"update_id": uid, "message": {"chat": {"id": chat}, "text": text}}


class _Http:
    def __init__(self, pages=None):
        self.pages, self.calls = list(pages or []), []

    def __call__(self, method, url, data=None, files=None):
        self.calls.append((url.rsplit("/", 1)[-1], data, files))
        if url.endswith("getUpdates") and self.pages:
            return {"ok": True, "result": self.pages.pop(0)}
        return {"ok": True, "result": []}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t0k")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")


def test_unconfigured_is_noop(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    h = _Http()
    assert telegram.pull_links(http=h) == []
    assert telegram.send_bundle(tmp_path, http=h) == []
    telegram.send_text("x", http=h)
    assert h.calls == [] and not telegram.configured()


def test_pull_links_filters_chat_pages_and_confirms(configured):
    page1 = [_upd(i, 42, f"https://youtu.be/v{i} please") for i in range(100)]
    page2 = [_upd(100, 99, "https://youtu.be/other"),          # wrong chat
             _upd(101, 42, "two: https://arxiv.org/abs/1 and https://youtu.be/v0")]  # v0 dup
    h = _Http([page1, page2])
    links = telegram.pull_links(http=h)
    assert links[:2] == ["https://youtu.be/v0", "https://youtu.be/v1"]
    assert "https://arxiv.org/abs/1" in links and "https://youtu.be/other" not in links
    assert len(links) == 101
    names = [c[0] for c in h.calls]
    assert names == ["getUpdates", "getUpdates", "getUpdates"]
    assert h.calls[1][1]["offset"] == 100                    # page 2 starts after page 1
    assert h.calls[2][1] == {"offset": 102, "limit": 1, "timeout": 0}   # confirm = last + 1


def test_pull_links_no_updates_no_confirm(configured):
    h = _Http([[]])
    assert telegram.pull_links(http=h) == [] and len(h.calls) == 1


def test_merge_into_links_file_append_only(tmp_path):
    f = tmp_path / "links.txt"
    assert telegram.merge_into_links_file(f, ["https://a/1", "https://a/2"]) == 2
    f.write_text(f.read_text().rstrip("\n"))                  # no trailing newline
    assert telegram.merge_into_links_file(f, ["https://a/2", "https://a/3"]) == 1
    assert adhoc._parse_links(f.read_text()) == ["https://a/1", "https://a/2", "https://a/3"]


def test_send_bundle_sends_existing_reader_files(configured, tmp_path):
    b = tmp_path / "Talk__yt_x"
    b.mkdir()
    (b / "notes.md").write_text("# notes")
    (b / "slides.pdf").write_bytes(b"%PDF")
    (b / "coverage_report.md").write_text("")                # empty → skipped
    h = _Http()
    assert telegram.send_bundle(b, caption="Talk", http=h) == ["notes.md", "slides.pdf"]
    name, data, files = h.calls[0]
    assert name == "sendDocument" and data["chat_id"] == "42" and data["caption"] == "Talk — notes.md"
    assert files["document"][0] == "Talk__yt_x__notes.md" and files["document"][1] == b"# notes"


def test_send_bundle_skips_oversized(configured, tmp_path, monkeypatch):
    b = tmp_path / "b"
    b.mkdir()
    (b / "notes.md").write_text("big")
    monkeypatch.setattr(telegram, "MAX_DOC_BYTES", 1)
    assert telegram.send_bundle(b, http=_Http()) == []


def test_list_loop_pulls_inbox_and_delivers_per_ok(configured, tmp_path, monkeypatch):
    calls = []
    NEW, OLD = "https://www.youtube.com/watch?v=new1new1new", "https://www.youtube.com/watch?v=old1old1old"
    monkeypatch.setattr(telegram, "pull_links", lambda **kw: [NEW])
    monkeypatch.setattr(telegram, "send_bundle", lambda sub, caption="", **kw: calls.append(("bundle", sub.name)) or ["notes.md"])
    monkeypatch.setattr(telegram, "send_text", lambda text, **kw: calls.append(("text", text)))
    links = tmp_path / "links.txt"
    links.write_text(f"{OLD}\n")
    out = tmp_path / "out"

    def run_one(url, out, profile, work_root):
        (out / "notes.md").parent.mkdir(parents=True, exist_ok=True)
        (out / "notes.md").write_text("n")
        return 0 if "new1" in url else 1
    rc = adhoc.run_adhoc_list(links, out=out, run_one=run_one,
                              meta_fetcher=lambda u, runner=None: None, work_root=tmp_path)
    assert rc == 0
    assert adhoc._parse_links(links.read_text()) == [OLD, NEW]
    assert ("bundle", "yt_new1new1new") in calls
    assert not any(c == ("bundle", "yt_old1old1old") for c in calls)
    assert calls[-1][0] == "text" and "✅ 1" in calls[-1][1] and "❌ 1" in calls[-1][1]


def test_list_loop_inbox_and_delivery_failures_never_change_result(configured, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(telegram, "pull_links", lambda **kw: (_ for _ in ()).throw(OSError("net down")))
    monkeypatch.setattr(telegram, "send_bundle", lambda *a, **kw: (_ for _ in ()).throw(OSError("net down")))
    monkeypatch.setattr(telegram, "send_text", lambda *a, **kw: (_ for _ in ()).throw(OSError("net down")))
    links = tmp_path / "links.txt"
    links.write_text("https://youtu.be/v1\n")

    def run_one(url, out, profile, work_root):
        out.mkdir(parents=True, exist_ok=True)
        (out / "notes.md").write_text("n")
        return 0
    rc = adhoc.run_adhoc_list(links, out=tmp_path / "out", run_one=run_one,
                              meta_fetcher=lambda u, runner=None: None, work_root=tmp_path)
    err = capsys.readouterr().out
    assert rc == 0 and "inbox pull failed" in err and "delivery FAILED" in err and "summary FAILED" in err
    assert (tmp_path / "out" / "BATCH_DONE").exists()


def test_list_loop_unconfigured_never_touches_telegram(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(telegram, "pull_links", lambda **kw: pytest.fail("inbox pulled"))
    monkeypatch.setattr(telegram, "send_bundle", lambda *a, **kw: pytest.fail("delivered"))
    links = tmp_path / "links.txt"
    links.write_text("https://youtu.be/v1\n")
    rc = adhoc.run_adhoc_list(links, out=tmp_path / "out",
                              run_one=lambda url, out, profile, work_root: 1,
                              meta_fetcher=lambda u, runner=None: None, work_root=tmp_path)
    assert rc == 0
