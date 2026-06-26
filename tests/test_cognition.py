"""Fakes-only tests for DEPTH v2: the Profile.synthesize seam, the dedicated cognition call's
model routing, the scoped Anthropic caller, and degrade-to-today. No network, no SDK install.

Contract under test
- Seam (R1): `lecture_synthesize` = descriptive thematic call + cognition call, merged; `pres_outputs`
  stays []. `briefing_synthesize` makes NO cognition call (byte-identical LSIC path).
- Routing: `_call_cognition` sends `claude-*` to the Anthropic caller and anything else to Gemini.
- Robustness: a cognition failure degrades to `{}` (descriptive notes still render); the schema
  validation drops junk keys and defaults missing ones.
- Anthropic caller: parses a fake client's response (adaptive thinking + high effort in the call);
  retries then re-raises.
"""
import types

import pytest

from src import anthropic_caller, synthesize

_COG_JSON = {
    "operating_algorithm": {"arrow_chain": "a → b → c", "tags": ["Mechanism"]},
    "cognitive_moves": [{"move": "m", "tag": "Mechanism", "work": "w", "evidence_id": "ev_1"}],
    "claim_epistemics": [{"evidence_id": "ev_1", "status": "his bet", "when_it_fails": "x"}],
    "what_doesnt_transfer": "y",
    "transfer_questions": [{"prompt": "q", "from_move": "m", "evidence_id": "ev_1"}],
}


def _ctx(client=None):
    al = types.SimpleNamespace(sections=[], event_id="yt_x")
    return synthesize.SynthesisContext(client=client, alignment=al, evidence=[],
                                       guest_pres=[], deck_text_by_asset={})


# ---------- model routing ----------

def test_cognition_routes_to_anthropic_for_claude(monkeypatch):
    seen = {}
    def fake_anth(system, user, *, model, **kw):
        seen.update(model=model, where="anthropic"); return dict(_COG_JSON)
    monkeypatch.setattr(anthropic_caller, "call_json", fake_anth)
    monkeypatch.setattr(synthesize, "_call_gemini_json",
                        lambda *a, **k: pytest.fail("claude model must NOT hit Gemini"))
    out = synthesize._call_cognition(_ctx(), model="claude-opus-4-8")
    assert seen == {"model": "claude-opus-4-8", "where": "anthropic"}
    assert out["operating_algorithm"]["arrow_chain"] == "a → b → c"
    assert out["claim_epistemics"][0]["status"] == "his bet"


def test_cognition_routes_to_gemini_for_non_claude(monkeypatch):
    seen = {}
    def fake_gem(client, system, user, max_tokens=0, model=""):
        seen.update(model=model); return dict(_COG_JSON)
    monkeypatch.setattr(synthesize, "_call_gemini_json", fake_gem)
    monkeypatch.setattr(anthropic_caller, "call_json",
                        lambda *a, **k: pytest.fail("gemini model must NOT hit Anthropic"))
    out = synthesize._call_cognition(_ctx(client=object()), model="gemini-2.5-pro")
    assert seen["model"] == "gemini-2.5-pro"
    assert out["transfer_questions"][0]["prompt"] == "q"


# ---------- robustness ----------

def test_cognition_degrades_to_empty_on_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    monkeypatch.setattr(anthropic_caller, "call_json", boom)
    out = synthesize._call_cognition(_ctx(), model="claude-opus-4-8")
    assert out == {}                       # degrade-to-today: descriptive notes still render


def test_cognition_validates_schema_drops_junk(monkeypatch):
    monkeypatch.setattr(anthropic_caller, "call_json",
                        lambda *a, **k: {"operating_algorithm": {"arrow_chain": "x"}, "junk": 1})
    out = synthesize._call_cognition(_ctx(), model="claude-opus-4-8")
    assert out["operating_algorithm"]["arrow_chain"] == "x"
    assert out["cognitive_moves"] == [] and out["claim_epistemics"] == []
    assert "junk" not in out


# ---------- the seam ----------

def test_lecture_synthesize_descriptive_plus_cognition(monkeypatch):
    got = {}
    monkeypatch.setattr(synthesize, "_call_thematic",
                        lambda *a, **k: {"title": "T", "notable_claims": [{"text": "c", "evidence_id": "ev_1"}]})
    def fake_cog(ctx, claims=None, model=None):
        got["claims"] = claims; return dict(_COG_JSON)
    monkeypatch.setattr(synthesize, "_call_cognition", fake_cog)
    thematic, pres = synthesize.lecture_synthesize(_ctx(client=object()))
    assert pres == []
    assert thematic["title"] == "T"                                   # descriptive preserved
    assert thematic["notable_claims"][0]["text"] == "c"               # claims stay descriptive
    assert thematic["operating_algorithm"]["arrow_chain"] == "a → b → c"  # cognition merged in
    # the descriptive claims are handed to the cognition call (so it tags them by evidence_id)
    assert got["claims"] == [{"text": "c", "evidence_id": "ev_1"}]


def test_cognition_model_resolved_at_call_time_from_env(monkeypatch):
    # env set AFTER import must still take effect (call-time read) — the A/B isolation depends on it
    seen = {}
    monkeypatch.setattr(synthesize, "_call_gemini_json",
                        lambda client, system, user, max_tokens=0, model="": (seen.update(model=model) or dict(_COG_JSON)))
    monkeypatch.setattr(anthropic_caller, "call_json",
                        lambda *a, **k: pytest.fail("env override to gemini must NOT hit Anthropic"))
    monkeypatch.setenv("COGNITION_MODEL", "gemini-2.5-pro")
    out = synthesize._call_cognition(_ctx(client=object()))      # no explicit model → reads env
    assert seen["model"] == "gemini-2.5-pro"
    assert out["what_doesnt_transfer"] == "y"


def test_cognition_passes_claims_into_the_prompt(monkeypatch):
    captured = {}
    monkeypatch.setattr(anthropic_caller, "call_json",
                        lambda system, user, *, model, **k: captured.update(user=user) or dict(_COG_JSON))
    synthesize._call_cognition(_ctx(), claims=[{"text": "RL is terrible", "evidence_id": "ev_7"}],
                               model="claude-opus-4-8")
    assert "CLAIMS TO TAG" in captured["user"] and "[ev_7] RL is terrible" in captured["user"]


def test_briefing_synthesize_makes_no_cognition_call(monkeypatch):
    monkeypatch.setattr(synthesize, "_load_role_pool", lambda p: [])
    monkeypatch.setattr(synthesize, "_call_thematic", lambda *a, **k: {"title": "B"})
    monkeypatch.setattr(synthesize, "_call_cognition",
                        lambda *a, **k: pytest.fail("briefing must NOT call cognition"))
    thematic, pres = synthesize.briefing_synthesize(_ctx(client=object()))
    assert thematic == {"title": "B"} and pres == []


# ---------- the Anthropic caller (fakes-only) ----------

class _FakeAnthropic:
    """Records the create() kwargs; returns a canned [thinking, text] response."""
    def __init__(self, text):
        self._text = text
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
                ])
        return _M()


def test_anthropic_caller_parses_and_sets_params():
    fc = _FakeAnthropic('```json\n{"operating_algorithm": {"arrow_chain": "z"}}\n```')
    out = anthropic_caller.call_json("sys", "usr", model="claude-opus-4-8", client=fc)
    assert out["operating_algorithm"]["arrow_chain"] == "z"           # fences stripped + parsed
    assert fc.kw["model"] == "claude-opus-4-8"
    assert fc.kw["thinking"] == {"type": "adaptive"}                  # reasoning lever
    assert fc.kw["output_config"] == {"effort": "high"}
    assert fc.kw["system"] == "sys"


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
