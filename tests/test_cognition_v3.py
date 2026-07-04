"""Fakes-only tests for the DEPTH v3 cognitive core (src/cognition.py).

Contract under test
- Two-pass: EXTRACT then CONVERT; the convert user message carries the extracted moves; the
  halves merge into ONE downstream dict (single contract) with a clean cognition_status.
- Failure semantics: a thin pass gets a plain re-issue then keeps the thin result with a
  VISIBLE status note; a raising pass falls back to FALLBACK_MODEL; a fully dead layer returns
  ONLY a cognition_status (never a silent {}).
- Reader context: no-domain prompts are GENERIC, never "return an empty list" (the v2 rule
  that silently erased Transfer Questions when the VM lacked READER_DOMAIN).
- Claims flow into the extract prompt keyed by evidence_id.
No network, no SDK install.
"""
import pytest

from src import cognition

_EXTRACT_OK = {
    "operating_algorithm": {"arrow_chain": "a → b", "tags": ["Mechanism"]},
    "cognitive_moves": [
        {"move": f"m{i}", "quote": f"q{i}", "tag": "Mechanism", "work": "w w w",
         "fails_when": "f", "self_question": "s", "evidence_id": f"ev_{i}"}
        for i in range(10)
    ],
    "claim_epistemics": [{"evidence_id": "ev_0", "status": "his bet", "when_it_fails": "x"}],
    "what_doesnt_transfer": "y",
}
_CONVERT_OK = {
    "founder_lens": [{"idea": "idea1", "from_moves": ["m0"], "wedge": "w", "action": "a",
                      "learn": "l", "deeper": "d", "evidence_id": "ev_0"}],
    "learn_it": {"retrieval_prompts": [{"q": "q?", "a": "a.", "evidence_id": "ev_0"}],
                 "first_order_terms": ["t1"], "buildable_artifact": "build X"},
}


def _fake(calls):
    """A healthy two-pass fake: the CONVERT pass is recognizable by the fed-forward moves."""
    def call_json(system, user, *, model, **kw):
        calls.append({"system": system, "user": user, "model": model})
        return dict(_CONVERT_OK) if "EXTRACTED MOVES" in user else dict(_EXTRACT_OK)
    return call_json


def test_two_pass_merges_halves_with_clean_status():
    calls = []
    out = cognition.run("CTX", call_json=_fake(calls))
    assert len(calls) == 2                                        # one call per pass
    assert len(out["cognitive_moves"]) == 10                      # extract half
    assert out["founder_lens"][0]["idea"] == "idea1"              # convert half
    assert out["learn_it"]["buildable_artifact"] == "build X"
    assert out["cognition_status"] == ""                          # healthy → empty status
    assert "CTX" in calls[0]["user"] and "CTX" in calls[1]["user"]


def test_convert_receives_extracted_moves():
    calls = []
    cognition.run("CTX", call_json=_fake(calls))
    convert_user = calls[1]["user"]
    assert "EXTRACTED MOVES" in convert_user
    assert "m0" in convert_user and "m9" in convert_user          # moves fed forward


def test_default_model_is_fable_env_overrides(monkeypatch):
    monkeypatch.delenv("COGNITION_MODEL", raising=False)
    calls = []
    cognition.run("CTX", call_json=_fake(calls))
    assert {c["model"] for c in calls} == {"claude-fable-5"}
    calls.clear()
    monkeypatch.setenv("COGNITION_MODEL", "claude-opus-4-8")
    cognition.run("CTX", call_json=_fake(calls))
    assert {c["model"] for c in calls} == {"claude-opus-4-8"}


def test_thin_extract_reissued_then_kept_with_visible_status():
    thin = {**_EXTRACT_OK, "cognitive_moves": _EXTRACT_OK["cognitive_moves"][:3]}
    calls = []
    def call_json(system, user, *, model, **kw):
        calls.append(model)
        return dict(_CONVERT_OK) if "EXTRACTED MOVES" in user else dict(thin)
    out = cognition.run("CTX", call_json=call_json)
    # plain re-issue on the model, then the fallback attempt — thin result KEPT, not dropped
    assert len(out["cognitive_moves"]) == 3
    assert "extract: below floor after retry" in out["cognition_status"]
    assert calls.count("claude-fable-5") >= 2                     # the re-issue happened
    assert "claude-opus-4-8" in calls                             # and the fallback attempt


def test_fable_failure_falls_back_to_opus():
    calls = []
    def call_json(system, user, *, model, **kw):
        calls.append(model)
        if model == "claude-fable-5":
            raise RuntimeError("refusal")
        return dict(_CONVERT_OK) if "EXTRACTED MOVES" in user else dict(_EXTRACT_OK)
    out = cognition.run("CTX", call_json=call_json)
    assert len(out["cognitive_moves"]) == 10                      # rescued by the fallback
    assert out["founder_lens"]
    assert out["cognition_status"] == ""                          # rescue is not a degrade
    assert calls.count("claude-opus-4-8") == 2                    # one rescue per pass


def test_dead_layer_returns_visible_status_never_silent_empty():
    def boom(*a, **k):
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    out = cognition.run("CTX", call_json=boom)
    assert set(out) == {"cognition_status"}                       # nothing fabricated
    assert "extract pass FAILED" in out["cognition_status"]
    assert "convert pass FAILED" in out["cognition_status"]


def test_one_dead_pass_keeps_the_other_half():
    def call_json(system, user, *, model, **kw):
        if "EXTRACTED MOVES" in user:
            raise RuntimeError("boom")                            # convert dies
        return dict(_EXTRACT_OK)
    out = cognition.run("CTX", call_json=call_json)
    assert len(out["cognitive_moves"]) == 10                      # extract half survives
    assert "convert pass FAILED" in out["cognition_status"]
    assert "founder_lens" not in out                              # absent ⇒ render omits


def test_claims_reach_extract_prompt():
    calls = []
    cognition.run("CTX", claims=[{"text": "RL is terrible", "evidence_id": "ev_7"}],
                  call_json=_fake(calls))
    assert "CLAIMS TO TAG" in calls[0]["user"]
    assert "[ev_7] RL is terrible" in calls[0]["user"]
    assert "CLAIMS TO TAG" not in calls[1]["user"]                # convert doesn't re-tag


def test_reader_domain_threads_into_both_passes():
    calls = []
    cognition.run("CTX", reader_domain="robotics founder", current_work="Tripp arm",
                  call_json=_fake(calls))
    for c in calls:
        assert "READER DOMAIN: robotics founder" in c["system"]
        assert "Tripp arm" in c["system"]


def test_extract_prompt_demands_v3_floor_and_probes():
    p = cognition.extract_prompt("", "")
    assert "AT LEAST 10" in p                                     # the ≥10 floor
    assert "final third" in p                                     # late-talk coverage
    assert "2-3 substantive sentences" in p                       # verbosity floor
    assert "anomalies" in p and "workarounds" in p                # ACTA probes
    assert "Perception" in p and "Taste" in p and "Incentives" in p   # 15-tag taxonomy
    assert "exact substring" in p                                 # verbatim-quote grounding


def test_convert_prompt_carries_wedge_rubric_and_matuschak_rules():
    p = cognition.convert_prompt("", "")
    assert "3-5 entries" in p and "do NOT force one entry per move" in p
    assert "wish, not a wedge" in p                               # the one-sentence wedge test
    assert "never yes/no" in p                                    # retrieval-prompt rules
    assert "buildable_artifact" in p
