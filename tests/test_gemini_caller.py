"""Fakes-only tests for src/gemini_caller.py — the ONE Gemini seam (refactor Reduction 1).

Contract under test
- generate_json: transient error → retry (linear backoff); bad/partial JSON → retry on the SAME
  budget; non-transient error → raise at once; MAX_TOKENS finish → Truncated at once (no retry);
  ``expect`` guards the parsed type; an empty body is [] only when a list is expected.
- generate: rides util.retry_transient (transient retried, other errors propagate).
- make_client: the only key lookup — loud when unset.
- Stage wiring: transcribe._call_api maps Truncated → the (None, "MAX_TOKENS") split signal;
  visual/slide_book/synthesize parse through the seam. No network anywhere.
"""
from __future__ import annotations

import types as _types
from pathlib import Path

import pytest

from src import gemini_caller, util


class _Resp:
    def __init__(self, text, finish="STOP"):
        self.text = text
        self.candidates = [_types.SimpleNamespace(finish_reason=finish)]


class _Client:
    """Scripted fake: each entry is an Exception (raised) or a _Resp (returned)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.models = _types.SimpleNamespace(generate_content=self._gen)

    def _gen(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(gemini_caller.time, "sleep", slept.append)
    monkeypatch.setattr(util.time, "sleep", slept.append)
    return slept


# ---------- generate_json ----------

def test_transient_then_ok_retries_with_backoff(_no_sleep):
    c = _Client([RuntimeError("503 UNAVAILABLE"), _Resp('{"a": 1}')])
    out = gemini_caller.generate_json(c, model="m", contents=["x"], expect=dict, base_delay=2.0)
    assert out == {"a": 1}
    assert len(c.calls) == 2
    assert _no_sleep == [2.0]                      # base_delay * (attempt + 1)


def test_bad_json_retries_on_same_budget_then_ok():
    c = _Client([_Resp("{not json"), _Resp("```json\n{\"a\": 2}\n```")])
    assert gemini_caller.generate_json(c, model="m", contents=["x"], expect=dict) == {"a": 2}
    assert len(c.calls) == 2


def test_bad_json_exhausts_budget_loud_with_head():
    c = _Client([_Resp("nope")] * 3)
    with pytest.raises(RuntimeError, match="invalid JSON after 3 tries.*nope"):
        gemini_caller.generate_json(c, model="m", contents=["x"], attempts=3)
    assert len(c.calls) == 3


def test_non_transient_raises_immediately():
    c = _Client([ValueError("INVALID_ARGUMENT bad schema"), _Resp("{}")])
    with pytest.raises(ValueError):
        gemini_caller.generate_json(c, model="m", contents=["x"])
    assert len(c.calls) == 1


def test_transient_exhausts_budget_reraises_last():
    c = _Client([RuntimeError(f"503 try {i}") for i in range(4)])
    with pytest.raises(RuntimeError, match="503 try 3"):
        gemini_caller.generate_json(c, model="m", contents=["x"], attempts=4)


def test_max_tokens_raises_truncated_without_retry():
    c = _Client([_Resp('{"partial": ', finish="FinishReason.MAX_TOKENS"), _Resp("{}")])
    with pytest.raises(gemini_caller.Truncated):
        gemini_caller.generate_json(c, model="m", contents=["x"])
    assert len(c.calls) == 1                       # never re-issued at full price


def test_expect_guard_treats_wrong_type_as_bad_json():
    c = _Client([_Resp("[1, 2]"), _Resp('{"ok": true}')])
    assert gemini_caller.generate_json(c, model="m", contents=["x"], expect=dict) == {"ok": True}


def test_empty_body_is_list_only_when_list_expected():
    assert gemini_caller.generate_json(_Client([_Resp("")]), model="m", contents=["x"],
                                       expect=list) == []
    c = _Client([_Resp(""), _Resp('{"a": 1}')])
    assert gemini_caller.generate_json(c, model="m", contents=["x"], expect=dict) == {"a": 1}
    assert len(c.calls) == 2                       # empty dict body → retried


def test_config_none_is_omitted_from_kwargs():
    c = _Client([_Resp("{}")])
    gemini_caller.generate_json(c, model="m", contents=["x"])
    assert c.calls[0] == {"model": "m", "contents": ["x"]}
    c2 = _Client([_Resp("{}")])
    gemini_caller.generate_json(c2, model="m", contents=["x"], config="CFG")
    assert c2.calls[0]["config"] == "CFG"


# ---------- generate (raw) ----------

def test_generate_retries_transient_returns_raw_response():
    r = _Resp("hello")
    c = _Client([RuntimeError("429 RESOURCE_EXHAUSTED"), r])
    assert gemini_caller.generate(c, model="m", contents=["x"]) is r


def test_generate_non_transient_propagates():
    c = _Client([KeyError("boom")])
    with pytest.raises(KeyError):
        gemini_caller.generate(c, model="m", contents=["x"])


# ---------- make_client / key lookup ----------

def test_make_client_loud_when_key_unset(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        gemini_caller.api_key()


def test_google_api_key_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    assert gemini_caller.api_key() == "g-key"


# ---------- stage wiring ----------

def test_transcribe_call_api_maps_truncated_to_split_signal(monkeypatch, tmp_path):
    from src import transcribe
    monkeypatch.setattr(transcribe, "_to_opus_bytes", lambda p: b"ogg")
    t = transcribe.GeminiTranscriber.__new__(transcribe.GeminiTranscriber)
    t.model = "m"
    t.client = _Client([_Resp("[", finish="MAX_TOKENS")])
    assert t._call_api(tmp_path / "c.wav") == (None, "MAX_TOKENS")
    t.client = _Client([_Resp('[{"start": 0, "end": 1, "text": "hi"}]')])
    rows, finish = t._call_api(tmp_path / "c.wav")
    assert rows == [{"start": 0, "end": 1, "text": "hi"}] and "MAX_TOKENS" not in finish


def test_visual_caption_parses_through_seam(tmp_path):
    from src import visual
    png = tmp_path / "f.jpg"
    png.write_bytes(b"jpg")
    d = visual.GeminiDescriber.__new__(visual.GeminiDescriber)
    d.model, d.client = "m", _Client([RuntimeError("503"), _Resp('{"visible_text": "T"}')])
    assert d.caption(png) == {"visible_text": "T"}


def test_synthesize_call_gemini_json_fails_fast_on_truncation():
    from src import synthesize
    c = _Client([_Resp("{", finish="MAX_TOKENS"), _Resp("{}")])
    with pytest.raises(gemini_caller.Truncated):
        synthesize._call_gemini_json(c, "sys", "user", max_tokens=10)
    assert len(c.calls) == 1
    assert c.calls[0]["config"].system_instruction == "sys"


def test_sync_caller_rides_retry_policy():
    from src.llm_caller import LLMRequest, SyncCaller
    r = _Resp("ok")
    c = _Client([RuntimeError("Server disconnected"), r])
    assert SyncCaller(c).generate_many([LLMRequest("id", "m", ["x"], None)]) == {"id": r}
