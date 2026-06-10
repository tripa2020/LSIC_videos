"""Fakes-only, no-network tests for the shared Gemini retry policy.

Covers `util.retry_transient` (new shared backoff helper) and its wiring into
`slide_book._vlm_curate` — the image/VLM call that previously had NO retry and
silently dropped slides on Gemini's intermittent multimodal 503s.

Contract under test — util.retry_transient
- Intent: call fn(); retry transient (is_transient) errors with linear backoff; raise the rest.
- Invariants:
    * success-first adds ZERO latency — sleep never called (degrade-to-today, byte-identical to fn()).
    * non-transient errors propagate on the FIRST failure (no retry).
    * transient errors retry up to `attempts`, then re-raise the LAST error.
    * backoff schedule is base_delay*(n+1): 5,10,15,20 for the defaults.
- Equivalence classes: success-first / transient-then-success / non-transient / always-transient.
- Oracles: returned value, fn call-count (spy), recorded sleep args, raised-exception identity.
"""
import pytest

from src import util


class _Boom(Exception):
    """A stand-in API error; transience is decided purely by str(e) markers."""


def _transient(msg="503 UNAVAILABLE: model is experiencing high demand"):
    return _Boom(msg)


def _make_fn(side_effects):
    """fn() consumes side_effects in order: Exception → raise it, else → return it.
    Returns (fn, calls) where calls grows by one per invocation."""
    calls = []
    seq = iter(side_effects)

    def fn():
        calls.append(1)
        item = next(seq)
        if isinstance(item, Exception):
            raise item
        return item

    return fn, calls


# ---------- util.retry_transient ----------

def test_success_first_call_no_retry_no_sleep():
    """Degrade-to-today: a fn that works first time returns immediately, sleep never fires."""
    fn, calls = _make_fn(["VALUE"])
    slept = []
    out = util.retry_transient(fn, sleep=slept.append)
    assert out == "VALUE"
    assert len(calls) == 1
    assert slept == []


def test_retries_transient_then_succeeds():
    """Two 503s then a value → returns the value; fn called 3x; backoff 5,10."""
    fn, calls = _make_fn([_transient(), _transient(), "OK"])
    slept = []
    out = util.retry_transient(fn, sleep=slept.append)
    assert out == "OK"
    assert len(calls) == 3
    assert slept == [5.0, 10.0]   # base_delay*(n+1) for n=0,1


def test_non_transient_raises_immediately():
    """A non-transient error (no marker in its message) is NOT retried."""
    fn, calls = _make_fn([ValueError("malformed json from model")])
    slept = []
    with pytest.raises(ValueError):
        util.retry_transient(fn, sleep=slept.append)
    assert len(calls) == 1
    assert slept == []


def test_exhausts_attempts_then_reraises_last():
    """Always-transient → after `attempts` tries, re-raise the LAST error; sleep attempts-1 times."""
    errs = [_transient(f"503 high demand attempt {i}") for i in range(5)]
    fn, calls = _make_fn(errs)
    slept = []
    with pytest.raises(_Boom) as ei:
        util.retry_transient(fn, attempts=5, sleep=slept.append)
    assert len(calls) == 5
    assert slept == [5.0, 10.0, 15.0, 20.0]   # attempts-1 backoffs
    assert "attempt 4" in str(ei.value)        # the final error surfaced, not the first


@pytest.mark.parametrize("attempts,base,expected_sleeps", [
    (3, 2.0, [2.0, 4.0]),
    (1, 5.0, []),            # attempts=1 → no retry window at all
])
def test_backoff_schedule_parametrized(attempts, base, expected_sleeps):
    """Backoff = base*(n+1); attempts=1 means a single try, no sleep, immediate re-raise."""
    fn, calls = _make_fn([_transient() for _ in range(attempts)])
    slept = []
    with pytest.raises(_Boom):
        util.retry_transient(fn, attempts=attempts, base_delay=base, sleep=slept.append)
    assert len(calls) == attempts
    assert slept == expected_sleeps


# ---------- slide_book._vlm_curate wiring ----------

class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, effects):
        self._fn, self.calls = _make_fn(effects)

    def generate_content(self, **_kw):   # ignores args; transience driven by effects
        return self._fn()


class _FakeClient:
    def __init__(self, effects):
        self.models = _FakeModels(effects)


class _FakeDescriber:
    def __init__(self, effects):
        self.client = _FakeClient(effects)
        self.model = "gemini-2.5-flash"


def test_vlm_curate_retries_transient_then_parses(tmp_path, monkeypatch):
    """A 503 then a valid 200 JSON → _vlm_curate rides the retry and parses the result."""
    pytest.importorskip("google.genai")
    from src import slide_book
    monkeypatch.setattr(util.time, "sleep", lambda _s: None)   # no real backoff wait
    png = tmp_path / "slide.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n fake-bytes")
    describer = _FakeDescriber([
        _transient(),
        _FakeResp('{"is_informative": true, "kind": "chart", "topic": "thermal"}'),
    ])
    out = slide_book._vlm_curate(describer, png)
    assert out["is_informative"] is True
    assert out["kind"] == "chart"
    assert describer.client.models.calls == [1, 1]   # called exactly twice (1 retry)


def test_vlm_curate_does_not_retry_non_transient(tmp_path, monkeypatch):
    """A 200 that yields malformed JSON is a non-transient parse error — NOT retried."""
    pytest.importorskip("google.genai")
    from src import slide_book
    monkeypatch.setattr(util.time, "sleep", lambda _s: None)
    png = tmp_path / "slide.png"
    png.write_bytes(b"\x89PNG fake")
    describer = _FakeDescriber([_FakeResp("not json at all {{{")])
    with pytest.raises(Exception):   # json.loads raises; classifier sees no marker → no retry
        slide_book._vlm_curate(describer, png)
    assert describer.client.models.calls == [1]   # exactly one call, no retry
