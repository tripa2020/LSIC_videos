"""Fakes-only, no-network unit tests for src/batch_gemini.py (Part 1 transport).

The transport is the untested core of the batch path. The live BatchJob field shapes are
verified on the VM at plan milestone M-C2; everything below is pure logic or client-injected
orchestration driven by in-memory fakes (CLAUDE.md Engineering Discipline).

Contract under test
- Intent: deliver a batch of LLM requests to Gemini and return {custom_id: response}.
- Invariants: custom_id is the only handle back to the caller; failed ids are NEVER in the
  result (R4 — resume re-enqueues them); transport holds no stage-cache knowledge (R1).
- Equivalence classes: empty / inline (≤ threshold) / file (> threshold); response entries
  good / None / error; job states terminal / non-terminal.
- Oracles: explicit JSON parse, src-type captured by a fake client, dict equality, raised
  ValueError.
"""
import json

import pytest

from src import batch_gemini as bg


# --- fakes (seams: client.batches, client.files) ---

class FakeJob:
    def __init__(self, name="batches/job-1", state="JOB_STATE_RUNNING", dest=None):
        self.name = name
        self.state = state
        self.dest = dest


class FakeDest:
    def __init__(self, inlined_responses=None, file_name=None):
        if inlined_responses is not None:
            self.inlined_responses = inlined_responses
        if file_name is not None:
            self.file_name = file_name


class FakeBatches:
    def __init__(self, get_job=None):
        self.created = []
        self._get_job = get_job

    def create(self, *, model, src):
        self.created.append({"model": model, "src": src})
        return FakeJob(name="batches/created")

    def get(self, *, name):
        return self._get_job


class FakeFiles:
    def __init__(self, upload_name="files/up-1", download_blob=b""):
        self.uploads = []
        self._upload_name = upload_name
        self._download_blob = download_blob

    def upload(self, *, file, config=None):
        self.uploads.append({"config": config})
        return type("Up", (), {"name": self._upload_name})()

    def download(self, *, file):
        return self._download_blob


class FakeClient:
    def __init__(self, get_job=None, upload_name="files/up-1", download_blob=b""):
        self.batches = FakeBatches(get_job=get_job)
        self.files = FakeFiles(upload_name=upload_name, download_blob=download_blob)


def _reqs(n, model="m"):
    return [bg.BatchRequest(f"c{i}", model, [f"hi{i}"], {"temperature": 0.0}) for i in range(n)]


# --- build_jsonl: shape + key embedding ---

def test_build_jsonl_one_keyed_line_per_request():
    out = bg.build_jsonl(_reqs(3))
    lines = out.splitlines()
    assert len(lines) == 3
    rows = [json.loads(l) for l in lines]
    assert [r["key"] for r in rows] == ["c0", "c1", "c2"]
    assert rows[0]["request"]["model"] == "m"
    assert rows[0]["request"]["contents"] == ["hi0"]
    assert rows[0]["request"]["config"] == {"temperature": 0.0}


def test_request_payload_omits_config_when_none():
    body = bg._request_payload(bg.BatchRequest("c", "m", ["x"], None))
    assert "config" not in body
    assert body == {"model": "m", "contents": ["x"]}


# --- submit: hybrid threshold + empty guard ---

def test_submit_inline_when_at_or_below_threshold():
    client = FakeClient()
    name = bg.submit(client, _reqs(2), inline_threshold=2)
    assert name == "batches/created"
    src = client.batches.created[0]["src"]
    assert isinstance(src, list) and len(src) == 2     # inline list, not a file ref
    assert src[0]["key"] == "c0"
    assert client.files.uploads == []                  # no file lifecycle


def test_submit_uploads_jsonl_file_above_threshold():
    client = FakeClient(upload_name="files/big")
    name = bg.submit(client, _reqs(3), inline_threshold=2)
    assert name == "batches/created"
    src = client.batches.created[0]["src"]
    assert src == "files/big"                           # file ref, not an inline list
    assert len(client.files.uploads) == 1               # JSONL uploaded once


def test_submit_empty_raises():
    with pytest.raises(ValueError):
        bg.submit(FakeClient(), [])


# --- state normalization + terminal detection (state-machine) ---

@pytest.mark.parametrize("state,expected", [
    ("JOB_STATE_SUCCEEDED", True),
    ("JOB_STATE_FAILED", True),
    ("JOB_STATE_CANCELLED", True),
    ("JOB_STATE_EXPIRED", True),
    ("JOB_STATE_RUNNING", False),
    ("JOB_STATE_PENDING", False),
])
def test_is_terminal(state, expected):
    assert bg.is_terminal(state) is expected


def test_norm_state_handles_enum_like_and_dotted():
    enum_like = type("S", (), {"name": "JOB_STATE_SUCCEEDED"})()
    assert bg._norm_state(enum_like) == "JOB_STATE_SUCCEEDED"
    assert bg._norm_state("JobState.JOB_STATE_FAILED") == "JOB_STATE_FAILED"


def test_poll_returns_normalized_state():
    client = FakeClient(get_job=FakeJob(state="JOB_STATE_RUNNING"))
    assert bg.poll(client, "batches/job-1") == "JOB_STATE_RUNNING"


# --- map_inline_responses: omit failures, unwrap response (R4) ---

def test_map_inline_omits_none_and_error_and_unwraps():
    keys = ["a", "b", "c", "d"]
    responses = [
        {"response": {"text": "A"}},
        None,                       # failed → omitted
        {"error": {"code": 500}},   # error → omitted
        {"text": "D"},              # no 'response' wrapper → passed through
    ]
    out = bg.map_inline_responses(keys, responses)
    assert out == {"a": {"text": "A"}, "d": {"text": "D"}}
    assert "b" not in out and "c" not in out


# --- parse_jsonl_output: omit error/keyless/blank lines (R4) ---

def test_parse_jsonl_output_skips_errors_and_blanks():
    text = "\n".join([
        json.dumps({"key": "a", "response": {"text": "A"}}),
        "",
        json.dumps({"key": "b", "error": {"code": 500}}),
        json.dumps({"response": {"text": "no key"}}),
        json.dumps({"key": "c", "response": {"text": "C"}}),
    ])
    out = bg.parse_jsonl_output(text)
    assert out == {"a": {"text": "A"}, "c": {"text": "C"}}


# --- resolve: inline / file / neither ---

def test_resolve_inline_job():
    dest = FakeDest(inlined_responses=[
        {"key": "a", "response": {"text": "A"}},
        {"key": "b", "error": {"code": 1}},
    ])
    client = FakeClient(get_job=FakeJob(state="JOB_STATE_SUCCEEDED", dest=dest))
    out = bg.resolve(client, "batches/job-1")
    assert out == {"a": {"text": "A"}}          # b omitted (error)


def test_resolve_file_job_downloads_and_parses():
    blob = (json.dumps({"key": "a", "response": {"text": "A"}}) + "\n"
            + json.dumps({"key": "b", "response": {"text": "B"}})).encode("utf-8")
    dest = FakeDest(file_name="files/out")
    client = FakeClient(get_job=FakeJob(state="JOB_STATE_SUCCEEDED", dest=dest),
                        download_blob=blob)
    out = bg.resolve(client, "batches/job-1")
    assert out == {"a": {"text": "A"}, "b": {"text": "B"}}


def test_resolve_no_dest_returns_empty():
    client = FakeClient(get_job=FakeJob(state="JOB_STATE_SUCCEEDED", dest=None))
    assert bg.resolve(client, "batches/job-1") == {}
