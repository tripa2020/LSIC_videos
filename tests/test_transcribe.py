"""Fakes-only, no-network unit tests for the ASR crash-fix + parsing logic.

The live API call is the only un-tested boundary; everything below is pure and
exercised with in-memory fakes (CLAUDE.md Engineering Discipline).
"""
from pathlib import Path

import pytest

from src.contracts import Segment
from src.transcribe import (
    _opus_cmd, _parse_segments, _reassemble, _transcribe_segment, _transient,
)


# --- #6 inline/Opus encode command ---

def test_opus_cmd_is_32k_mono_ogg_to_stdout():
    cmd = _opus_cmd(Path("chunk_000.wav"))
    assert cmd[0] == "ffmpeg" and cmd[-1] == "pipe:1"
    assert "libopus" in cmd and "32k" in cmd and "ogg" in cmd
    assert cmd[cmd.index("-ac") + 1] == "1"          # mono
    assert "chunk_000.wav" in cmd                    # reads the given source


# --- #2 structured parse ---

def test_parse_segments_offset_and_skips_malformed():
    rows = [
        {"start": 0.0, "end": 1.0, "text": "hi", "speaker_id": "A", "language": "en"},
        {"start": 1.0, "end": 2.0, "text": "  spaced  "},   # missing optionals → None
        {"start": "bad", "end": 2.0, "text": "x"},          # bad type → skipped
        {"end": 2.0, "text": "no start"},                   # missing required → skipped
    ]
    segs = _parse_segments(rows, offset=100.0)
    assert len(segs) == 2
    assert segs[0].start == 100.0 and segs[0].end == 101.0 and segs[0].speaker_id == "A"
    assert segs[1].text == "spaced" and segs[1].speaker_id is None


def test_parse_segments_none_is_empty():
    assert _parse_segments(None, 0.0) == []


# --- #3 parallel reassembly ---

def test_reassemble_sorts_clamps_drops():
    by_idx = {
        1: [Segment(start=5.0, end=6.0, text="b")],
        0: [Segment(start=0.0, end=1.0, text="a"),
            Segment(start=2.0, end=2.0, text="zero")],     # zero-dur → dropped
        2: [Segment(start=9.0, end=12.0, text="c")],        # end clamped to duration
    }
    out = _reassemble(by_idx, duration=10.0)
    assert [s.text for s in out] == ["a", "b", "c"]
    assert out[-1].end == 10.0


# --- #4 transient classifier ---

def test_transient_classifier():
    assert _transient(RuntimeError("503 UNAVAILABLE"))
    assert _transient(Exception("Server disconnected without sending a response"))
    assert _transient(Exception("The read operation timed out"))
    # DNS blips on flaky networks must be retryable too (the synth-stage gap)
    assert _transient(Exception("[Errno 8] nodename nor servname provided, or not known"))
    assert _transient(Exception("[Errno -2] Name or service not known"))
    assert not _transient(ValueError("bad value"))
    assert not _transient(KeyError("start"))


# --- #1 the crash fix: split-on-overflow recursion ---

def _fake_split(audio, offset):
    """Halve a string marker; second half's offset advances by the first half's length."""
    half = len(audio) // 2
    return [(audio[:half], offset), (audio[half:], offset + half)]


def test_transcribe_segment_splits_on_max_tokens():
    def fake_call(audio):
        if len(audio) > 2:                       # "too dense" → output overflow
            return None, "MAX_TOKENS"
        return [{"start": 0.0, "end": 1.0, "text": audio}], "STOP"

    segs = _transcribe_segment("ABCD", 0.0, fake_call, _fake_split)
    # ABCD→MAX → AB@0, CD@2 → both fit → texts AB,CD at local 0 lifted by offset
    assert [s.text for s in segs] == ["AB", "CD"]
    assert segs[0].start == 0.0 and segs[1].start == 2.0


def test_transcribe_segment_no_split_when_ok():
    def ok_call(audio):
        return [{"start": 0.0, "end": 1.0, "text": "fine"}], "STOP"
    segs = _transcribe_segment("anything", 7.0, ok_call, _fake_split)
    assert len(segs) == 1 and segs[0].start == 7.0


def test_transcribe_segment_depth_cap_raises():
    def always_overflow(audio):
        return None, "MAX_TOKENS"
    with pytest.raises(RuntimeError, match="overflow"):
        _transcribe_segment("XXXXXXXX", 0.0, always_overflow, _fake_split)
