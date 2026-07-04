"""Fakes-only tests for the cognition SEAM after DEPTH v3: `lecture_synthesize` builds the
full-context cognition input and merges `cognition.run`'s output; `briefing_synthesize` makes
NO cognition call (byte-identical LSIC path); the scoped Anthropic caller parses, sets params,
reports actual usage→$, and retries. The core's own behavior (two-pass, retry-then-status,
prompts) lives in test_cognition_v3.py. No network, no SDK install.
"""
import types

import pytest

from src import anthropic_caller, cognition, synthesize

_COG = {
    "operating_algorithm": {"arrow_chain": "a → b → c", "tags": ["Mechanism"]},
    "cognitive_moves": [{"move": "m", "tag": "Mechanism", "work": "w", "evidence_id": "ev_1"}],
    "claim_epistemics": [{"evidence_id": "ev_1", "status": "his bet", "when_it_fails": "x"}],
    "what_doesnt_transfer": "y",
}


def _ctx(client=None, reader_domain="", current_work=""):
    al = types.SimpleNamespace(sections=[], event_id="yt_x")
    return synthesize.SynthesisContext(client=client, alignment=al, evidence=[],
                                       guest_pres=[], deck_text_by_asset={},
                                       reader_domain=reader_domain, current_work=current_work)


# ---------- the seam ----------

def test_lecture_synthesize_descriptive_plus_cognition(monkeypatch):
    got = {}
    monkeypatch.setattr(synthesize, "_call_thematic",
                        lambda *a, **k: {"title": "T", "notable_claims": [{"text": "c", "evidence_id": "ev_1"}]})
    def fake_run(context, claims=None, **kw):
        got["claims"] = claims
        return dict(_COG)
    monkeypatch.setattr(cognition, "run", fake_run)
    thematic, pres = synthesize.lecture_synthesize(_ctx(client=object()))
    assert pres == []
    assert thematic["title"] == "T"                                   # descriptive preserved
    assert thematic["notable_claims"][0]["text"] == "c"               # claims stay descriptive
    assert thematic["operating_algorithm"]["arrow_chain"] == "a → b → c"  # cognition merged in
    # the descriptive claims are handed to the cognition layer (so it tags them by evidence_id)
    assert got["claims"] == [{"text": "c", "evidence_id": "ev_1"}]


def test_lecture_reader_context_flows_from_ctx(monkeypatch):
    seen = {}
    monkeypatch.setattr(synthesize, "_call_thematic", lambda *a, **k: {"title": "T"})
    monkeypatch.setattr(cognition, "run",
                        lambda context, claims=None, reader_domain="", current_work="", **kw:
                        seen.update(rd=reader_domain, cw=current_work) or {})
    synthesize.lecture_synthesize(_ctx(client=object(), reader_domain="robotics",
                                       current_work="tripp"))
    assert seen == {"rd": "robotics", "cw": "tripp"}


def test_lecture_cognition_context_is_uncapped(monkeypatch):
    # the cognition context must be built with cognition.CONTEXT_CAP (the ~900k-token sanity
    # guard), NOT the descriptive 140k default that hid the last hour of long talks
    caps = []
    real = synthesize._build_event_context
    monkeypatch.setattr(synthesize, "_build_event_context",
                        lambda al, ev, cap=140_000: caps.append(cap) or real(al, ev, cap=cap))
    monkeypatch.setattr(synthesize, "_call_thematic", lambda *a, **k: {"title": "T"})
    monkeypatch.setattr(cognition, "run", lambda context, claims=None, **kw: {})
    synthesize.lecture_synthesize(_ctx(client=object()))
    assert cognition.CONTEXT_CAP in caps
    assert cognition.CONTEXT_CAP > 3_000_000


def test_briefing_synthesize_makes_no_cognition_call(monkeypatch):
    monkeypatch.setattr(synthesize, "_load_role_pool", lambda p: [])
    monkeypatch.setattr(synthesize, "_call_thematic", lambda *a, **k: {"title": "B"})
    monkeypatch.setattr(cognition, "run",
                        lambda *a, **k: pytest.fail("briefing must NOT call cognition"))
    thematic, pres = synthesize.briefing_synthesize(_ctx(client=object()))
    assert thematic == {"title": "B"} and pres == []


# ---------- the Anthropic caller (fakes-only) ----------

class _FakeAnthropic:
    """Records the create() kwargs; returns a canned [thinking, text] response."""
    def __init__(self, text, usage=None):
        self._text = text
        self._usage = usage
        self.kw = None
    @property
    def messages(self):
        outer = self
        class _M:
            def create(self_inner, **kw):
                outer.kw = kw
                return types.SimpleNamespace(content=[
                    types.SimpleNamespace(type="thinking", thinking="…"),
                    types.SimpleNamespace(type="text", text=outer._text),
                ], usage=outer._usage)
        return _M()


def test_anthropic_caller_parses_and_sets_params():
    fc = _FakeAnthropic('```json\n{"operating_algorithm": {"arrow_chain": "z"}}\n```')
    out = anthropic_caller.call_json("sys", "usr", model="claude-opus-4-8", client=fc)
    assert out["operating_algorithm"]["arrow_chain"] == "z"           # fences stripped + parsed
    assert fc.kw["model"] == "claude-opus-4-8"
    assert fc.kw["thinking"] == {"type": "adaptive"}                  # valid on Fable AND Opus
    assert fc.kw["output_config"] == {"effort": "high"}
    assert fc.kw["system"] == "sys"


def test_anthropic_caller_reports_actual_cost(capsys):
    # OQ9 (revised): observe REAL cost — usage→$ from the response, priced only here
    usage = types.SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000)
    fc = _FakeAnthropic('{"a": 1}', usage=usage)
    anthropic_caller.call_json("s", "u", model="claude-fable-5", client=fc)
    outp = capsys.readouterr().out
    assert "claude-fable-5" in outp and "$15.00" in outp   # 1M×$10 + 0.1M×$50


def test_anthropic_caller_silent_on_missing_usage(capsys):
    fc = _FakeAnthropic('{"a": 1}')                        # fakes carry no usage
    anthropic_caller.call_json("s", "u", model="claude-fable-5", client=fc)
    assert "$" not in capsys.readouterr().out


def test_anthropic_caller_retries_then_raises():
    calls = {"n": 0}
    class Boom:
        @property
        def messages(self):
            class _M:
                def create(self_inner, **kw):
                    calls["n"] += 1
                    raise RuntimeError("503")
            return _M()
    with pytest.raises(RuntimeError):
        anthropic_caller.call_json("s", "u", client=Boom(), attempts=3, sleep=lambda *_: None)
    assert calls["n"] == 3
