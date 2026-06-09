"""Fakes-only, no-network unit tests for src/llm_caller.py (Part 1 Caller seam).

The seam is where the batch ON/OFF decision lives (R2). The two contracts that matter:
- SyncCaller reproduces today's per-request generate_content call (degrade-to-today).
- BatchCaller buffers the fan-out, polls until terminal, resolves {custom_id: response},
  and never returns a failed id (R4).

Seams controlled: the genai client (faked) and time.sleep (injected). No network, no clock.
"""
import pytest

from src import batch_gemini as bg
from src.llm_caller import BatchCaller, LLMRequest, SyncCaller, _gen_kwargs


# --- SyncCaller: byte-for-byte today's call, keyed by custom_id ---

class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        # echo a marker the test can trace back to the request
        return {"echo": kwargs["contents"]}


class FakeSyncClient:
    def __init__(self):
        self.models = FakeModels()


def test_sync_caller_calls_per_request_keyed_by_custom_id():
    client = FakeSyncClient()
    reqs = [
        LLMRequest("c0", "m", ["a"], {"temperature": 0.0}),
        LLMRequest("c1", "m", ["b"], None),
    ]
    out = SyncCaller(client).generate_many(reqs)
    assert out == {"c0": {"echo": ["a"]}, "c1": {"echo": ["b"]}}
    # order preserved, model + contents forwarded
    assert [c["contents"] for c in client.models.calls] == [["a"], ["b"]]
    assert client.models.calls[0]["model"] == "m"


def test_sync_caller_omits_config_kwarg_when_none():
    client = FakeSyncClient()
    SyncCaller(client).generate_many([LLMRequest("c", "m", ["x"], None)])
    assert "config" not in client.models.calls[0]


def test_sync_caller_forwards_config_when_present():
    cfg = {"temperature": 0.0}
    assert _gen_kwargs(LLMRequest("c", "m", ["x"], cfg))["config"] is cfg


def test_sync_caller_empty_is_empty():
    assert SyncCaller(FakeSyncClient()).generate_many([]) == {}


# --- BatchCaller: poll-until-terminal then resolve, failed id omitted (R4) ---

class FakeBatchesSeq:
    """batches.get returns a scripted sequence of states; resolve reads dest at the end."""

    def __init__(self, states, dest):
        self._states = list(states)
        self._dest = dest
        self.created = []
        self.get_calls = 0

    def create(self, *, model, src):
        self.created.append({"model": model, "src": src})
        return type("Job", (), {"name": "batches/seq"})()

    def get(self, *, name):
        self.get_calls += 1
        # advance through states; hold on the last (terminal) one for resolve
        state = self._states[0] if len(self._states) == 1 else self._states.pop(0)
        return type("Job", (), {"name": name, "state": state, "dest": self._dest})()


class FakeBatchClient:
    def __init__(self, states, dest):
        self.batches = FakeBatchesSeq(states, dest)


def test_batch_caller_polls_until_terminal_then_resolves():
    dest = type("D", (), {"inlined_responses": [
        {"key": "c0", "response": {"text": "A"}},
        {"key": "c1", "error": {"code": 500}},   # failed → omitted (R4)
    ]})()
    client = FakeBatchClient(
        states=["JOB_STATE_RUNNING", "JOB_STATE_RUNNING", "JOB_STATE_SUCCEEDED"],
        dest=dest,
    )
    slept = []
    caller = BatchCaller(client, poll_interval=7.0, sleep=slept.append)
    out = caller.generate_many([
        LLMRequest("c0", "m", ["a"], None),
        LLMRequest("c1", "m", ["b"], None),
    ])
    assert out == {"c0": {"text": "A"}}            # c1 omitted (R4)
    assert slept == [7.0, 7.0]                      # slept once per non-terminal poll
    assert client.batches.created[0]["model"] == "m"


def test_batch_caller_empty_skips_submit():
    client = FakeBatchClient(states=["JOB_STATE_SUCCEEDED"], dest=None)
    assert BatchCaller(client, sleep=lambda _: None).generate_many([]) == {}
    assert client.batches.created == []            # no job created for an empty fan-out


def test_batch_caller_succeeds_immediately_no_sleep():
    dest = type("D", (), {"inlined_responses": [{"key": "c0", "response": 1}]})()
    client = FakeBatchClient(states=["JOB_STATE_SUCCEEDED"], dest=dest)
    slept = []
    out = BatchCaller(client, sleep=slept.append).generate_many(
        [LLMRequest("c0", "m", ["a"], None)])
    assert out == {"c0": 1}
    assert slept == []                             # terminal on first poll → no wait
