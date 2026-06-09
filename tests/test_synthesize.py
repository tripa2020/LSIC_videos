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
