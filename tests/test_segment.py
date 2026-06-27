"""Fakes-only tests for src.segment — size-bounded windowing of evidence into map-units (MAPRED).

Contract under test
- ALWAYS ≥1 window (R5): empty / non-transcript-only input still yields one window.
- Single window when total transcript text ≤ budget (this is the degrade-to-today gate: <2 windows
  ⇒ caller uses today's single call).
- Splits into ≥2 windows when text exceeds budget; windows time-ordered, NO evidence dropped, each
  window's text ≤ budget (except a lone oversize item, which still gets its own window).
- Non-transcript evidence (slide/asset/metadata) is excluded.
- WINDOW_BUDGET env overrides the default at call time.
"""
from src import segment
from src.contracts import Evidence


def _ev(i, text, t, kind="transcript"):
    return Evidence(evidence_id=f"ev_{i}", kind=kind, source_id="s",
                    timestamp_start=float(t), timestamp_end=float(t) + 1.0, text=text)


def test_always_at_least_one_window_when_empty():
    out = segment.segment([])
    assert len(out) == 1 and out[0].evidence == []


def test_non_transcript_only_yields_one_empty_window():
    ev = [_ev(1, "x" * 100, 0, kind="slide"), _ev(2, "y" * 100, 5, kind="asset")]
    out = segment.segment(ev)
    assert len(out) == 1 and out[0].evidence == []


def test_single_window_under_budget():
    ev = [_ev(i, "word " * 10, i * 10) for i in range(5)]          # ~250 chars total
    out = segment.segment(ev, budget_chars=10_000)
    assert len(out) == 1
    assert [e.evidence_id for e in out[0].evidence] == [f"ev_{i}" for i in range(5)]


def test_splits_over_budget_no_drop_time_ordered():
    ev = [_ev(i, "x" * 100, i) for i in range(10)]                 # 10×100 = 1000 chars
    out = segment.segment(ev, budget_chars=250)                   # ~2 items/window
    assert len(out) >= 2
    # no evidence dropped, original time order preserved across the union
    flat = [e.evidence_id for w in out for e in w.evidence]
    assert flat == [f"ev_{i}" for i in range(10)]
    # each window's text within budget (or a single oversize item alone)
    for w in out:
        assert sum(len(e.text) for e in w.evidence) <= 250 or len(w.evidence) == 1
    # windows are emitted in increasing start time
    assert [w.start for w in out] == sorted(w.start for w in out)


def test_oversize_single_item_gets_own_window_never_dropped():
    ev = [_ev(1, "a" * 50, 0), _ev(2, "b" * 500, 1), _ev(3, "c" * 50, 2)]
    out = segment.segment(ev, budget_chars=100)
    assert any(len(w.evidence) == 1 and w.evidence[0].evidence_id == "ev_2" for w in out)
    flat = [e.evidence_id for w in out for e in w.evidence]
    assert flat == ["ev_1", "ev_2", "ev_3"]


def test_window_budget_env_override(monkeypatch):
    ev = [_ev(i, "x" * 100, i) for i in range(6)]
    monkeypatch.setenv("WINDOW_BUDGET", "150")
    many = segment.segment(ev)            # 150 budget → 1 item/window (2nd would be 200 > 150)
    monkeypatch.setenv("WINDOW_BUDGET", "100000")
    one = segment.segment(ev)
    assert len(many) > len(one) == 1
