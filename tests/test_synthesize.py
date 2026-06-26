"""Fakes-only unit test for the synthesize resume-gate.

Finding from the DeMattia verify run: synthesize_full had no is_complete gate, so a second
pipeline run re-spent Gemini-Pro on an already-finished event. The fix returns the existing
notes.md when its manifest is complete, WITHOUT building the LLM client.
"""
import pytest

from src import synthesize, util


def test_synthesize_full_skips_when_complete(tmp_path, monkeypatch):
    event_id = "lsic_test"
    briefing = tmp_path / "events" / event_id / util.STAGE_BRIEFING
    briefing.mkdir(parents=True)
    out = briefing / "notes.md"
    util.write_with_manifest(out, "# already synthesized\n", stage="synthesize")

    # If the gate works, the client is never constructed — make it explode if it is.
    def explode():
        raise AssertionError("LLM client built despite a complete cache")

    monkeypatch.setattr(synthesize, "_gemini_client", explode)

    result = synthesize.synthesize_full(event_id, work_root=tmp_path)
    assert result == out
    assert out.read_text().startswith("# already synthesized")   # untouched


def test_synthesize_full_proceeds_when_incomplete(tmp_path, monkeypatch):
    """With no prior notes.md the gate must fall through (we stop it at client build)."""
    event_id = "lsic_fresh"
    (tmp_path / "events" / event_id / util.STAGE_BRIEFING).mkdir(parents=True)

    def explode():
        raise RuntimeError("reached client build")     # proves the gate did NOT short-circuit

    monkeypatch.setattr(synthesize, "_gemini_client", explode)
    with pytest.raises(RuntimeError, match="reached client build"):
        synthesize.synthesize_full(event_id, work_root=tmp_path)


def test_synthesize_full_lecture_end_to_end(tmp_path, monkeypatch):
    """DEPTH v2 glue (fakes-only): synthesize_full(profile='lecture') builds the ctx, runs the
    Profile.synthesize seam (descriptive + cognition), merges, persists thematic.json, and renders
    notes.md with the cognition sections + the epistemic overlay landed on the descriptive claim."""
    import datetime
    import json as _json

    from src import contracts as c, ingest as ingest_mod

    eid = "yt_e2e"
    wd = tmp_path / "events" / eid
    (wd / util.STAGE_INGEST).mkdir(parents=True)
    (wd / util.STAGE_ALIGNED).mkdir(parents=True)
    (wd / util.STAGE_INGEST / "manifest.json").write_text(
        c.IngestResult(event_id=eid, workdir=wd, duration_sec=600.0).model_dump_json())
    (wd / util.STAGE_ALIGNED / "aligned.json").write_text(
        c.AlignmentResult(event_id=eid, duration_sec=600.0, sections=[], presentations=[]).model_dump_json())
    (wd / util.STAGE_ALIGNED / "evidence.json").write_text("[]")

    ev = c.Event(event_id=eid, date=datetime.date(2026, 6, 11), assets=[c.Asset(kind="video")])
    monkeypatch.setattr(ingest_mod, "load_events_json", lambda root: ([ev], None))
    monkeypatch.setattr(synthesize, "_gemini_client", lambda: object())
    monkeypatch.setattr(synthesize, "_load_deck_text", lambda w, assets: {})
    monkeypatch.setattr(synthesize, "_count_speakers", lambda w: 1)
    # the seam's two LLM calls — faked
    monkeypatch.setattr(synthesize, "_call_thematic",
                        lambda *a, **k: {"title": "E2E Talk", "summary": "S",
                                         "notable_claims": [{"text": "claim X", "evidence_id": "ev_1"}]})
    monkeypatch.setattr(synthesize, "_call_cognition", lambda ctx, claims=None, model=None: {
        "operating_algorithm": {"arrow_chain": "p → q", "tags": ["Mechanism"]},
        "cognitive_moves": [{"move": "m", "tag": "Mechanism", "work": "w", "evidence_id": "ev_1"}],
        "claim_epistemics": [{"evidence_id": "ev_1", "status": "his bet", "when_it_fails": "z"}],
        "what_doesnt_transfer": "the bets", "transfer_questions": [],
    })

    out = synthesize.synthesize_full(eid, work_root=tmp_path, profile="lecture")
    md = out.read_text()
    assert out.name == "notes.md"
    assert "# E2E Talk" in md and "## Operating Algorithm" in md and "p → q" in md
    assert "## Cognitive Moves" in md
    assert "claim X" in md and "`[his bet]`" in md           # cognition overlay landed on the claim
    # thematic.json persisted with the merged cognition fields
    thematic = _json.loads((wd / util.STAGE_BRIEFING / "thematic.json").read_text())
    assert thematic["operating_algorithm"]["arrow_chain"] == "p → q"
    assert thematic["notable_claims"][0]["text"] == "claim X"
