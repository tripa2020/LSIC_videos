"""Tests for the deterministic Energy ∪ ISRU filter (Part 2, M-C3).

Two layers: a hand-built mini fixture pins the set algebra exactly, and a no-network read of
the real selected_manifest pins the locked counts (130 events / 122 with video) so a catalog
or filter change can't silently move the batch.
"""
import json

from src import topic_filter as tf


def _write(tmp_path, rows):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(rows))
    return p


def test_filter_selects_only_energy_or_isru(tmp_path):
    rows = [
        {"event_id": "A", "topics": ["Surface Power"], "kind": "youtube"},
        {"event_id": "B", "topics": ["In Situ Resource Utilization"], "yt_video_id": "x"},
        {"event_id": "C", "topics": ["Dust Mitigation"], "kind": "youtube"},   # neither → out
        {"event_id": "D", "topics": ["Excavation and Construction", "Surface Power"]},  # has SP → in
    ]
    p = _write(tmp_path, rows)
    assert tf.energy_isru_event_ids(p) == {"A", "B", "D"}


def test_no_event_rows_excluded(tmp_path):
    rows = [
        {"event_id": "", "topics": ["Surface Power"]},
        {"event_id": "0", "topics": ["Surface Power"]},
        {"event_id": None, "topics": ["Surface Power"]},
        {"event_id": "A", "topics": ["Surface Power"]},
    ]
    assert tf.energy_isru_event_ids(_write(tmp_path, rows)) == {"A"}


def test_with_video_is_subset_and_detects_sources(tmp_path):
    rows = [
        {"event_id": "A", "topics": ["Surface Power"], "kind": "youtube"},        # video
        {"event_id": "B", "topics": ["Surface Power"], "target_filename": "x.mp4"},  # video
        {"event_id": "C", "topics": ["Surface Power"], "target_filename": "x.pdf"},  # no video
    ]
    p = _write(tmp_path, rows)
    all_ids = tf.energy_isru_event_ids(p)
    vid = tf.with_video(p, all_ids)
    assert all_ids == {"A", "B", "C"}
    assert vid == {"A", "B"}                      # subset, deck/paper-only C dropped


def test_deterministic(tmp_path):
    rows = [{"event_id": "A", "topics": ["Surface Power"], "kind": "youtube"}]
    p = _write(tmp_path, rows)
    assert tf.energy_isru_event_ids(p) == tf.energy_isru_event_ids(p)


def test_real_manifest_locked_counts():
    """No-network read of the curated manifest — pins the batch size (CLOUD_BATCH_PLAN.md)."""
    all_ids = tf.energy_isru_event_ids()          # default: download_lsic/selected_manifest.json
    vid_ids = tf.with_video(ids=all_ids)
    assert len(all_ids) == 129, f"Energy∪ISRU events drifted: {len(all_ids)}"
    assert len(vid_ids) == 122, f"with-video count drifted: {len(vid_ids)}"
    assert vid_ids <= all_ids
