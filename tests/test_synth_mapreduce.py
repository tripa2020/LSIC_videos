"""Fakes-only tests for src.synth_mapreduce + the lecture_synthesize routing (MAPRED).

Contract under test
- single-producer: MAP emits LOCAL facts only (no summary/expert_lenses/takeaways/…); global
  sections come ONLY from the single REDUCE call. map_extract filters any global keys the model leaks.
- MAP runs once per window; REDUCE runs exactly once, over a context carrying evidence_ids from ALL
  windows; REDUCE uses the injected (profile) system prompt.
- a window whose extract call raises degrades to {} — REDUCE still runs (no crash).
- mapreduce_thematic returns REDUCE's dict verbatim (drop-in for _call_thematic).
- routing (degrade-to-today): lecture_synthesize uses map-reduce for ≥2 windows, today's single
  call for ≤1 window. The injected call_json keeps the module network-free.
"""
import types

from src import synth_mapreduce, synthesize
from src.contracts import Evidence
from src.segment import Window


def _ev(i, t, text=None):
    return Evidence(evidence_id=f"ev_{i}", kind="transcript", source_id="s",
                    timestamp_start=float(t), timestamp_end=float(t) + 1.0,
                    text=text or f"text {i}")


def _windows(n=3):
    return [Window(index=k, start=float(k * 100), end=float(k * 100 + 50),
                   evidence=[_ev(k, k * 100)]) for k in range(n)]


# ---------- single-producer ----------

def test_local_keys_exclude_every_global_section():
    forbidden = {"summary", "expert_lenses", "title", "takeaways",
                 "field_implications", "industry_outlook"}
    assert not (set(synth_mapreduce.LOCAL_KEYS) & forbidden)
    assert "Do NOT write a summary" in synth_mapreduce.MAP_SYSTEM_PROMPT


def test_map_extract_drops_leaked_global_keys():
    def fake(client, system, user, max_tokens=0):
        return {"key_points": [{"text": "p", "evidence_id": "ev_0"}],
                "summary": "SHOULD BE DROPPED", "expert_lenses": [{"role": "x"}]}
    out = synth_mapreduce.map_extract(None, _windows(1)[0], fake)
    assert "summary" not in out and "expert_lenses" not in out
    assert out["key_points"][0]["text"] == "p"
    assert set(out) == set(synth_mapreduce.LOCAL_KEYS)


# ---------- map-once / reduce-once over the union ----------

def test_map_once_per_window_reduce_once_over_union():
    calls = {"map": 0, "reduce": 0, "reduce_user": ""}
    def fake(client, system, user, max_tokens=0):
        if system == synth_mapreduce.MAP_SYSTEM_PROMPT:
            calls["map"] += 1
            return {"key_points": [{"text": f"p{calls['map']}",
                                    "evidence_id": f"ev_{calls['map'] - 1}"}]}
        calls["reduce"] += 1
        calls["reduce_user"] = user
        return {"title": "T", "summary": "S", "key_points": []}
    out = synth_mapreduce.mapreduce_thematic(None, _windows(3), "REDUCE_SYS", fake)
    assert calls["map"] == 3 and calls["reduce"] == 1
    for i in range(3):                          # REDUCE saw evidence from ALL windows
        assert f"ev_{i}" in calls["reduce_user"]
    assert out == {"title": "T", "summary": "S", "key_points": []}


def test_reduce_uses_injected_profile_prompt():
    seen = {}
    def fake(client, system, user, max_tokens=0):
        if system != synth_mapreduce.MAP_SYSTEM_PROMPT:
            seen["sys"] = system
        return {"ok": True}
    synth_mapreduce.mapreduce_thematic(None, _windows(2), "LECTURE_DESC_PROMPT", fake)
    assert seen["sys"] == "LECTURE_DESC_PROMPT"


def test_map_failure_degrades_reduce_still_runs():
    def fake(client, system, user, max_tokens=0):
        if system == synth_mapreduce.MAP_SYSTEM_PROMPT:
            raise RuntimeError("window LLM down")
        return {"title": "T"}
    out = synth_mapreduce.mapreduce_thematic(None, _windows(2), "SYS", fake)
    assert out == {"title": "T"}                # reduce ran despite every map failing


# ---------- lecture routing (degrade-to-today) ----------

def _lecture_ctx(evidence):
    return synthesize.SynthesisContext(
        client=object(), alignment=types.SimpleNamespace(sections=[], event_id="yt"),
        evidence=evidence, guest_pres=[], deck_text_by_asset={})


def test_lecture_long_talk_routes_to_mapreduce(monkeypatch):
    systems = []
    monkeypatch.setattr(synthesize, "_call_gemini_json",
                        lambda c, system, user, max_tokens=0, model="": systems.append(system) or {})
    monkeypatch.setattr(synthesize, "_call_cognition", lambda ctx, claims=None, model=None: {})
    monkeypatch.setenv("WINDOW_BUDGET", "5")    # any 2 items exceed 5 chars → ≥2 windows
    synthesize.lecture_synthesize(_lecture_ctx([_ev(i, i, "hello world") for i in range(3)]))
    assert synth_mapreduce.MAP_SYSTEM_PROMPT in systems


def test_lecture_short_talk_routes_to_single_call(monkeypatch):
    systems = []
    monkeypatch.setattr(synthesize, "_call_gemini_json",
                        lambda c, system, user, max_tokens=0, model="": systems.append(system) or {})
    monkeypatch.setattr(synthesize, "_call_cognition", lambda ctx, claims=None, model=None: {})
    monkeypatch.setenv("WINDOW_BUDGET", "100000")
    synthesize.lecture_synthesize(_lecture_ctx([_ev(0, 0, "hello world")]))
    assert synth_mapreduce.MAP_SYSTEM_PROMPT not in systems   # today's single descriptive call
