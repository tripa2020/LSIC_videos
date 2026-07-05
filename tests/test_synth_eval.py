"""Fakes-only tests for EVAL (src/synth_eval.py) — the pure deterministic scorer.

Contract under test
- Purity: metrics computed from strings/dicts only; deterministic on fixtures (R2/R3).
- Notes-only mode scores ANY bundle (old goldens included); full mode adds quote
  verification (normalized substring vs the transcript), evidence resolution, and the
  cross-window ratio (OQ4) — cites spanning 1 vs ≥2 windows.
- evaluate_briefing is read-only: writes coverage_report.{md,json} beside notes.md, returns
  None (never raises) when there is nothing to score; the synthesize hook swallows failures.
"""
import json

from src import synth_eval, synthesize


def _notes(dur="120:00", moves_block="", extra=""):
    return (f'---\nduration: "{dur}"\n---\n# T\n\n## Summary\nS\n\n'
            f"## Cognitive Moves\n{moves_block}\n\n{extra}## Speakers\n- **A** — x\n")


def _move(mm, quote="the exact words", n=1):
    return "\n".join(
        f"- **m{i} at {mm}** — *Mechanism* — w w w `[{mm}:00]`\n"
        f"  > “{quote}”\n  ↳ *fails when:* f\n  ↳ *ask yourself:* q" for i in range(n))


# ---------- notes-only mode ----------

def test_decile_coverage_spread_vs_clustered():
    spread = _notes(moves_block="\n".join(f"- **m** — *T* — w `[{m}:00]`" for m in
                                          (5, 20, 35, 50, 65, 80, 95, 110)))
    clustered = _notes(moves_block="\n".join(f"- **m** — *T* — w `[{m}:00]`" for m in
                                             (1, 2, 3, 4, 5)))
    assert synth_eval.score_notes(spread)["decile_coverage"] >= 0.7
    assert synth_eval.score_notes(clustered)["decile_coverage"] <= 0.1


def test_v3_gates_pass_on_compliant_notes():
    md = _notes(
        moves_block=_move("10", n=9) + "\n" + _move("100", n=2),   # 11 moves, 2 in final third
        extra=("## Founder Lens — To Market\n### i1 `[10:00]`\n- **Wedge:** w\n"
               "### i2\n- **Wedge:** w\n### i3\n- **Wedge:** w\n\n"
               "## How to Learn It (So It Sticks)\n**First-order terms:** a · b\n\n"
               + "\n".join(f"- Q: q{i} `[5:00]`\n  A: a{i}" for i in range(5))
               + "\n\n**Build to internalize:** build X\n\n"))
    s = synth_eval.score_notes(md)
    assert s["moves"] == 11 and s["final_third_cites"] == 2
    assert s["moves_with_quote"] == 11 and s["moves_with_fails_when"] == 11
    assert s["founder_plays"] == 3 and s["retrieval_prompts"] == 5
    assert s["gates"] == {k: True for k in s["gates"]}


def test_gates_fail_on_pre_v3_bundle_and_degraded_status():
    old = _notes(moves_block=_move("10", n=4))                     # v2-era: 4 moves, no sections
    s = synth_eval.score_notes(old)
    assert not s["gates"]["moves_floor"] and not s["gates"]["founder_lens"]
    degraded = _notes().replace("# T", "# T\n\n> ⚠️ *cognition degraded:* extract pass FAILED")
    assert synth_eval.score_notes(degraded)["gates"]["status_clean"] is False


def test_duration_absent_degrades_metrics_to_none():
    s = synth_eval.score_notes("# T\n\n## Summary\nS `[10:00]`\n")
    assert s["duration_sec"] is None and s["decile_coverage"] is None
    assert s["final_third_cites"] == 0                             # no dur → can't place cites


# ---------- full mode ----------

_EV = [{"evidence_id": f"ev_{i}", "kind": "transcript", "source_id": "a1",
        "timestamp_start": i * 60.0, "timestamp_end": i * 60.0 + 30,
        "text": f"segment {i} says the exact words here"}
       for i in range(8)]


def test_quote_verification_normalized_and_hallucination_caught():
    them = {"cognitive_moves": [
        {"quote": "The EXACT words, here"},                        # matches modulo case/punct
        {"quote": "words that were never spoken at all"},          # hallucinated
    ]}
    s = synth_eval.score_full(_notes(), them, _EV)
    assert s["quotes_verified"] == 0.5
    assert s["gates"]["quotes_verified"] is False                  # < 0.9 floor


def test_cross_window_ratio_single_vs_spanning(monkeypatch):
    monkeypatch.setenv("WINDOW_BUDGET", "80")                      # force multiple windows
    single = {"key_points": [{"evidence_id": "ev_0"}, {"evidence_id": "ev_1"}]}
    multi = {"key_points": [{"evidence_id": "ev_0"}, {"evidence_id": "ev_7"}]}
    lo = synth_eval.score_full(_notes(), single, _EV)["cross_window_ratio"]
    hi = synth_eval.score_full(_notes(), multi, _EV)["cross_window_ratio"]
    assert lo == 0.0 and hi == 1.0


def test_evidence_resolution_counts_unknown_ids():
    them = {"key_points": [{"evidence_id": "ev_0"}, {"evidence_id": "ev_bogus"}]}
    s = synth_eval.score_full(_notes(), them, _EV)
    assert s["evidence_resolution"] == 0.5


# ---------- evaluate_briefing + the synthesize hook ----------

def test_evaluate_briefing_writes_reports_read_only(tmp_path):
    b = tmp_path / "05_briefing"
    b.mkdir()
    (b / "notes.md").write_text(_notes(moves_block=_move("10", n=3)))
    before = (b / "notes.md").read_text()
    out = synth_eval.evaluate_briefing(b)
    assert out is not None and out.name == "coverage_report.md"
    assert (b / "coverage_report.json").exists()
    assert (b / "notes.md").read_text() == before                  # read-only contract
    assert "moves" in json.loads((b / "coverage_report.json").read_text())


def test_evaluate_briefing_none_when_nothing_to_score(tmp_path):
    assert synth_eval.evaluate_briefing(tmp_path) is None          # no notes.md → no report


def test_synthesize_hook_swallows_eval_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(synth_eval, "evaluate_briefing",
                        lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
    synthesize._run_eval(tmp_path, "ev_x")                         # must NOT raise
    assert "skipped" in capsys.readouterr().out


def test_cli_table_over_bundles(tmp_path, capsys):
    b = tmp_path / "some_bundle"
    b.mkdir()
    (b / "notes.md").write_text(_notes(moves_block=_move("10", n=2)))
    rc = synth_eval.main([str(b), str(tmp_path / "missing")])
    out = capsys.readouterr().out
    assert rc == 0 and "some_bundle" in out and "(no notes.md)" in out
