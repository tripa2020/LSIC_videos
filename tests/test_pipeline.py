"""Fakes-only test for the --keep-going resilience (#5): run_event_stages must
treat a raised exception as a stage failure and never propagate it."""
from src.main import run_event_stages


def test_all_stages_ok():
    calls = []

    def a():
        calls.append("a"); return 0

    def b():
        calls.append("b"); return 0

    ok, failed = run_event_stages("evt", [("a", a), ("b", b)])
    assert ok and failed is None and calls == ["a", "b"]


def test_stops_at_first_nonzero():
    calls = []

    def a():
        calls.append("a"); return 0

    def b():
        calls.append("b"); return 1          # failure

    def c():
        calls.append("c"); return 0          # must not run

    ok, failed = run_event_stages("evt", [("a", a), ("b", b), ("c", c)])
    assert not ok and failed == "b" and "c" not in calls


def test_exception_is_caught_not_propagated():
    def a():
        return 0

    def boom():
        raise RuntimeError("kaboom")         # the crash class

    ok, failed = run_event_stages("evt", [("a", a), ("boom", boom)])  # must NOT raise
    assert not ok and failed == "boom"
