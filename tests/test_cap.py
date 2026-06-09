"""Tests for the 4h aggregate-video cap decision (Part 2, M-C4).

The cap is enforced once at ingest via the pure _within_cap predicate; these pin its
boundary behavior so the bounded manifest's spine stays ≤ cap at a whole-video boundary,
while never producing a zero-video event. Degrade-to-today: None cap ⇒ always include.
"""
import pytest

from src.ingest import _within_cap


def test_none_cap_always_includes():
    # degrade-to-today: no cap → every video included regardless of length
    assert _within_cap(offset=10_000.0, dur=9_999.0, max_total_sec=None, have_parts=True)


def test_first_video_always_included_even_if_over_cap():
    # never drop the only video, even if it alone exceeds the cap
    assert _within_cap(offset=0.0, dur=20_000.0, max_total_sec=14_400.0, have_parts=False)


@pytest.mark.parametrize("offset,dur,expected", [
    (0.0,      14_400.0, True),    # exactly fills the cap → included
    (10_000.0,  4_400.0, True),    # lands exactly on cap → included
    (10_000.0,  4_401.0, False),   # 1s over → excluded (stop here)
    (14_400.0,      1.0, False),   # already at cap → exclude the rest
    (12_741.0,  1_757.0, False),   # the 7-video workshop's last part (would hit 14498) → dropped
])
def test_cap_boundary(offset, dur, expected):
    assert _within_cap(offset, dur, max_total_sec=14_400.0, have_parts=True) is expected
