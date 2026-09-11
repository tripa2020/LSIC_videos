"""Fakes-only tests for URL-input media (src/url_media.py) and its manifest-state selection.

Contract under test
- url_parts: URL mode ⇔ no audio AND every part is a YouTube URL with no local path; a
  downloaded manifest, a notes-only manifest, or a mixed one ⇒ [] (today's path).
- windows: ≥1 window, covers [0, duration], last is the remainder.
- URLTranscriber: clip-relative timestamps get the window offset added back and are clamped
  to the window; per-window cache is honored (no call on rerun); a MAX_TOKENS window is split
  in half via the shared overflow logic; the spurious 400 is retried.
- URLDescriber: Caption rows with frame_path=None / trigger="url", absolute t; a failed
  window is logged, left uncached, and never sinks the stage.
- Stage selection: transcribe_one_event picks the URL backend from manifest state (no flag);
  extract_visual likewise; batch prefills are no-ops in URL mode.
- ingest URL mode: YT_INPUT=url ⇒ no fetch, model-probed duration in the manifest, no audio;
  unset ⇒ the download path is taken (byte-identical control).
- Downstream: _select_slide_highlights ignores frame-less captions; align evidence tags them.
"""
from __future__ import annotations

import json
import types as _t
from datetime import date
from pathlib import Path

import pytest

from src import gemini_caller, url_media, util
from src.contracts import Asset, Caption, Event, IngestResult, VideoPart

URL = "https://www.youtube.com/watch?v=abc123"


class _Resp:
    def __init__(self, text, finish="STOP"):
        self.text = text
        self.candidates = [_t.SimpleNamespace(finish_reason=finish)]


class _Client:
    """Scripted fake keyed by nothing — pops the next item; records call kwargs."""

    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.models = _t.SimpleNamespace(generate_content=self._gen)

    def _gen(self, **kw):
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(gemini_caller.time, "sleep", lambda s: None)
    monkeypatch.setattr(util.time, "sleep", lambda s: None)


def _part(dur=600.0, key="abc123", offset=0.0, path=None, url=URL):
    return VideoPart(key=key, path=path, source_url=url, duration_sec=dur, offset_sec=offset)


def _ing(tmp_path, parts, audio=None):
    return IngestResult(event_id="yt_abc123", workdir=tmp_path, audio_path=audio,
                        video_path=None, duration_sec=sum(p.duration_sec for p in parts),
                        video_parts=parts)


# ---------- selection + windows ----------

def test_url_parts_selects_only_pure_url_manifests(tmp_path):
    assert url_media.url_parts(_ing(tmp_path, [_part()])) == [_part()]
    assert url_media.url_parts(_ing(tmp_path, [_part()], audio=tmp_path / "a.wav")) == []
    assert url_media.url_parts(_ing(tmp_path, [_part(path=tmp_path / "v.mp4")])) == []
    assert url_media.url_parts(_ing(tmp_path, [_part(), _part(key="z", url="https://zoom.us/x")])) == []
    assert url_media.url_parts(_ing(tmp_path, [])) == []


def test_windows_cover_duration_and_always_one():
    assert url_media.windows(0) == [(0.0, 0.0)]
    assert url_media.windows(100, 300) == [(0.0, 100.0)]
    assert url_media.windows(650, 300) == [(0.0, 300.0), (300.0, 600.0), (600.0, 650.0)]


def test_url_part_offsets_are_whole_seconds():
    p = url_media.url_part(URL, 600, 900)
    assert p.file_data.file_uri == URL
    assert p.video_metadata.start_offset == "600s" and p.video_metadata.end_offset == "900s"
    assert url_media.url_part(URL).video_metadata is None


# ---------- URLTranscriber ----------

def test_transcriber_offsets_clamps_and_caches(tmp_path):
    rows = [{"start": 10.0, "end": 12.0, "text": "hi", "speaker_id": "A"},
            {"start": 298.0, "end": 340.0, "text": "overshoot", "speaker_id": "B"}]
    c = _Client([_Resp(json.dumps(rows)), _Resp("[]")])          # 2 windows of a 400 s part
    tr = url_media.URLTranscriber([_part(400.0)], client=c, concurrency=1)
    segs = tr.transcribe(None, 400.0, tmp_path)
    assert [(s.start, s.end, s.text) for s in segs] == [(10.0, 12.0, "hi"), (298.0, 300.0, "overshoot")]
    assert len(c.calls) == 2
    # offsets rode in the request; second window starts at 300
    vm = c.calls[1]["contents"][1].video_metadata
    assert (vm.start_offset, vm.end_offset) == ("300s", "400s")
    # rerun: every window cached → zero calls
    c2 = _Client([])
    tr2 = url_media.URLTranscriber([_part(400.0)], client=c2, concurrency=1)
    assert [s.text for s in tr2.transcribe(None, 400.0, tmp_path)] == ["hi", "overshoot"]
    assert c2.calls == []


def test_transcriber_second_part_gets_event_offset(tmp_path):
    rows = [{"start": 1.0, "end": 2.0, "text": "p2"}]
    c = _Client([_Resp("[]"), _Resp(json.dumps(rows))])
    parts = [_part(100.0, key="a"), _part(100.0, key="b", offset=100.0)]
    segs = url_media.URLTranscriber(parts, client=c, concurrency=1).transcribe(None, 200.0, tmp_path)
    assert [(s.start, s.end) for s in segs] == [(101.0, 102.0)]


def test_transcriber_max_tokens_window_splits_in_half(tmp_path):
    c = _Client([_Resp("[", finish="MAX_TOKENS"),
                 _Resp(json.dumps([{"start": 1.0, "end": 2.0, "text": "L"}])),
                 _Resp(json.dumps([{"start": 1.0, "end": 2.0, "text": "R"}]))])
    segs = url_media.URLTranscriber([_part(300.0)], client=c, concurrency=1).transcribe(None, 300.0, tmp_path)
    assert [(s.start, s.text) for s in segs] == [(1.0, "L"), (151.0, "R")]
    vms = [k["contents"][1].video_metadata for k in c.calls]
    assert [(v.start_offset, v.end_offset) for v in vms] == [("0s", "300s"), ("0s", "150s"), ("150s", "300s")]


def _collapsed_rows(n=20):
    return [{"start": 65.0 + k * 0.01, "end": 65.0 + k * 0.01, "text": f"w{k}"} for k in range(n)]


def test_collapsed_window_is_reissued_then_spread(tmp_path):
    good = [{"start": 3.0, "end": 4.0, "text": "fine"}]
    # 1) collapsed once, good on re-issue → the re-issued rows win, exactly 2 calls
    c = _Client([_Resp(json.dumps(_collapsed_rows())), _Resp(json.dumps(good))])
    segs = url_media.URLTranscriber([_part(300.0)], client=c, concurrency=1).transcribe(None, 300.0, tmp_path)
    assert [(s.start, s.text) for s in segs] == [(3.0, "fine")] and len(c.calls) == 2
    # 2) collapsed twice → spread evenly across the window, text + order intact
    c = _Client([_Resp(json.dumps(_collapsed_rows())), _Resp(json.dumps(_collapsed_rows()))])
    segs = url_media.URLTranscriber([_part(300.0, key="k2")], client=c, concurrency=1).transcribe(None, 300.0, tmp_path)
    assert len(segs) == 20 and [s.text for s in segs] == [f"w{k}" for k in range(20)]
    assert segs[0].start == 0.0 and segs[-1].end == 300.0 and segs[10].start == 150.0
    # 3) a short/sparse window is never 'collapsed' (no spurious re-issue)
    c = _Client([_Resp(json.dumps(_collapsed_rows(5)))])
    url_media.URLTranscriber([_part(300.0, key="k3")], client=c, concurrency=1).transcribe(None, 300.0, tmp_path)
    assert len(c.calls) == 1


def test_spurious_400_is_retried_on_url_calls(tmp_path):
    c = _Client([RuntimeError("400 INVALID_ARGUMENT. Request contains an invalid argument."),
                 _Resp(json.dumps([{"start": 0.0, "end": 1.0, "text": "ok"}]))])
    segs = url_media.URLTranscriber([_part(60.0)], client=c, concurrency=1).transcribe(None, 60.0, tmp_path)
    assert [s.text for s in segs] == ["ok"] and len(c.calls) == 2
    # …but NOT elsewhere: the plain caller still treats a 400 as fatal
    with pytest.raises(RuntimeError):
        gemini_caller.generate_json(_Client([RuntimeError("400 INVALID_ARGUMENT")]), model="m", contents=["x"])


def test_probe_duration_parses_and_is_loud_on_nonsense():
    c = _Client([_Resp('{"duration_sec": 4218, "speakers": 3}')])
    assert url_media.probe_duration(URL, client=c) == (4218.0, 3)
    assert c.calls[0]["contents"][1].video_metadata.fps == url_media.PROBE_FPS
    with pytest.raises(RuntimeError, match="no duration"):
        url_media.probe_duration(URL, client=_Client([_Resp('{"duration_sec": 0}')]))


# ---------- URLDescriber ----------

def test_describer_captions_are_frameless_absolute_and_failure_tolerant(tmp_path):
    rows = [{"t": 30.0, "visible_text": "E = mc^2", "description": "slide", "has_equation": True,
             "has_diagram": False}, {"t": 999.0, "visible_text": "late", "description": "x"}]
    c = _Client([_Resp(json.dumps(rows)), ValueError("INVALID_ARGUMENT: bad")])
    caps = url_media.URLDescriber([_part(600.0)], client=c, concurrency=1).captions(tmp_path)
    assert [c_.t for c_ in caps] == [30.0, 300.0]             # 999 clamped to the 300 s window
    assert all(c_.frame_path is None and c_.trigger == "url" for c_ in caps)
    assert caps[0].has_equation is True
    cached = sorted((tmp_path / "windows").glob("*.captions.json"))
    assert len(cached) == 1                                    # failed window left uncached
    assert cached[0].name == "abc123_000000.captions.json"


# ---------- stage selection from manifest state ----------

def test_transcribe_stage_selects_url_backend(monkeypatch, tmp_path):
    from src import transcribe
    ev = tmp_path / "events" / "yt_abc123"
    (ev / util.STAGE_INGEST).mkdir(parents=True)
    ing = _ing(tmp_path, [_part(60.0)])
    (ev / util.STAGE_INGEST / "manifest.json").write_text(ing.model_dump_json())
    used = {}

    class FakeURL:
        def __init__(self, parts, **kw):
            used["parts"] = parts
        def transcribe(self, audio_path, duration, workdir):
            return []
    monkeypatch.setattr(url_media, "URLTranscriber", FakeURL)
    monkeypatch.setattr(transcribe, "GeminiTranscriber", lambda *a, **k: pytest.fail("download backend used"))
    out, segs = transcribe.transcribe_one_event("yt_abc123", work_root=tmp_path)
    assert used["parts"] == [_part(60.0)] and segs == [] and out.exists()
    # slicing is refused in URL mode (loud, not silent)
    with pytest.raises(RuntimeError, match="URL mode"):
        transcribe.transcribe_one_event("yt_abc123", max_sec=10, work_root=tmp_path)
    # notes-only manifest still raises today's error
    ev2 = tmp_path / "events" / "notes_only"
    (ev2 / util.STAGE_INGEST).mkdir(parents=True)
    (ev2 / util.STAGE_INGEST / "manifest.json").write_text(_ing(tmp_path, []).model_dump_json())
    with pytest.raises(RuntimeError, match="no audio"):
        transcribe.transcribe_one_event("notes_only", work_root=tmp_path)


def test_visual_stage_selects_url_backend_and_prefill_noop(monkeypatch, tmp_path):
    from src import visual
    ev = tmp_path / "events" / "yt_abc123"
    (ev / util.STAGE_INGEST).mkdir(parents=True)
    (ev / util.STAGE_INGEST / "manifest.json").write_text(_ing(tmp_path, [_part(60.0)]).model_dump_json())
    cap = Caption(t=5.0, frame_path=None, trigger="url", description="d")

    class FakeDesc:
        def __init__(self, parts, **kw): ...
        def captions(self, cache_dir):
            return [cap]
    monkeypatch.setattr(url_media, "URLDescriber", FakeDesc)
    monkeypatch.setattr(visual, "_kept_frames", lambda *a, **k: pytest.fail("frame path used"))
    caps = visual.extract_visual("yt_abc123", work_root=tmp_path)
    assert caps == [cap]
    assert util.is_complete(ev / util.STAGE_KEYFRAMES / "captions.json")
    assert visual.batch_prefill_captions("yt_abc123", caller=object(), work_root=tmp_path) == 0


# ---------- ingest URL mode ----------

def _event(tmp_path):
    return Event(event_id="yt_abc123", date=date(2026, 9, 1),
                 assets=[Asset(kind="video", path=tmp_path / "missing.mp4", lsic_id=None,
                               source_url=URL, meta={"yt_video_id": "abc123"})])


def test_ingest_url_mode_records_url_and_probed_duration(monkeypatch, tmp_path):
    from src import ingest
    monkeypatch.setenv("YT_INPUT", "url")
    monkeypatch.setattr(url_media, "probe_duration", lambda url, client=None, model=None: (4218.0, 3))
    monkeypatch.setattr(ingest, "_resolve_video", lambda *a, **k: pytest.fail("downloaded in URL mode"))
    res = ingest.ingest_event(_event(tmp_path), work_root=tmp_path)
    assert res.audio_path is None and res.video_path is None
    assert res.duration_sec == 4218.0
    assert res.video_parts[0].source_url == URL and res.video_parts[0].path is None
    assert url_media.url_parts(res) == res.video_parts          # ⇒ downstream picks URL backends
    assert util.is_complete(tmp_path / "events" / "yt_abc123" / util.STAGE_INGEST / "manifest.json")


def test_ingest_unset_takes_download_path(monkeypatch, tmp_path):
    from src import ingest
    monkeypatch.delenv("YT_INPUT", raising=False)
    monkeypatch.setattr(url_media, "probe_duration", lambda *a, **k: pytest.fail("probed without URL mode"))
    seen = {}
    monkeypatch.setattr(ingest, "_resolve_video", lambda a, d: seen.setdefault("fetched", True) or (_ for _ in ()).throw(RuntimeError("stop here")))
    with pytest.raises(RuntimeError, match="all 1 videos failed"):
        ingest.ingest_event(_event(tmp_path), work_root=tmp_path)
    assert seen == {"fetched": True}


def test_ingest_url_mode_respects_cap(monkeypatch, tmp_path):
    from src import ingest
    monkeypatch.setenv("YT_INPUT", "url")
    monkeypatch.setattr(url_media, "probe_duration", lambda url, client=None, model=None: (5000.0, 1))
    ev = _event(tmp_path)
    ev.assets.append(Asset(kind="video", path=tmp_path / "m2.mp4", lsic_id=None,
                           source_url="https://youtu.be/def456", meta={"yt_video_id": "def456"}))
    res = ingest.ingest_event(ev, work_root=tmp_path, max_total_sec=6000)
    assert [p.key for p in res.video_parts] == ["abc123"]          # second dropped by the cap


# ---------- downstream consumers of frameless captions ----------

def test_frameless_captions_never_become_slide_highlights():
    from src import synthesize
    caps = [Caption(t=1.0, frame_path=None, trigger="url", visible_text="fig", has_diagram=True),
            Caption(t=2.0, frame_path=Path("f.jpg"), trigger="scene", visible_text="fig", has_diagram=True)]
    assert [c.t for c in synthesize._select_slide_highlights(caps)] == [2.0]
