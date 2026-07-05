"""Fakes-only tests for FIX: the corpus driver's no-drop contract and the ingest fetch retry.

Contract under test
- Driver (run_corpus.sh): a FAILING event does NOT drop the rest — every event runs, the
  failure is logged ❌, and the end-of-run tally counts the driver's own ✅/❌ records
  (not a log grep). The script exits 0 so batch supervisors don't abort.
- Ingest: a transient non-zero fetch exit retries (bounded) then succeeds; first-try
  success is byte-identical to a bare call (zero sleeps); a dead URL still raises.
The driver test runs the REAL bash script with a stub $PY (no pipeline, no network).
"""
import os
import stat
import subprocess
from pathlib import Path

import pytest

from src import ingest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "download_lsic" / "run_corpus.sh"

_FAKE_PY = """#!/usr/bin/env bash
# Stub "$PY" for run_corpus.sh: no network, no pipeline. lsic_b is the poisoned event.
case "$*" in
  *group_manifest*)            exit 0 ;;
  -c*events.json*)             printf 'lsic_a\\nlsic_b\\nlsic_c\\n' ;;
  -\\ *)                       echo "" ;;      # the DOC_IDS heredoc call: no decks
  *src.main*--event\\ lsic_b*) echo "boom: fake ingest 503" >&2; exit 1 ;;
  *src.main*)                  echo "report OK"; exit 0 ;;
  *)                           exit 0 ;;
esac
"""


def _run_driver(tmp_path, conc="2"):
    fake_py = tmp_path / "fakepy"
    fake_py.write_text(_FAKE_PY)
    fake_py.chmod(fake_py.stat().st_mode | stat.S_IEXEC)
    ids = tmp_path / "ids.txt"
    ids.write_text("evt1\nevt2\nevt3\n")           # driver re-resolves via events.json stub
    return subprocess.run(
        ["bash", str(SCRIPT), str(ids)],
        cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "PY": str(fake_py), "CONC": conc, "GCS_BUCKET": ""},
    )


def test_failing_event_does_not_drop_the_rest(tmp_path):
    cp = _run_driver(tmp_path)
    assert cp.returncode == 0, cp.stderr                       # supervisor-safe exit
    assert "✅ lsic_a" in cp.stdout and "✅ lsic_c" in cp.stdout   # the rest still ran
    assert "❌ lsic_b" in cp.stdout                             # the failure is loud


def test_tally_counts_the_drivers_own_records(tmp_path):
    cp = _run_driver(tmp_path)
    assert "✅ 2 ok · ❌ 1 failed" in cp.stdout                 # counted, not log-grepped
    assert "failed events:" in cp.stdout and "❌ lsic_b" in cp.stdout
    assert (tmp_path / "logs" / "_fail.txt").read_text().strip() == "lsic_b"


def test_all_green_run_tallies_clean(tmp_path):
    fake_py = tmp_path / "fakepy"
    fake_py.write_text(_FAKE_PY.replace("exit 1", "exit 0"))   # nothing poisoned
    fake_py.chmod(fake_py.stat().st_mode | stat.S_IEXEC)
    ids = tmp_path / "ids.txt"
    ids.write_text("x\n")
    cp = subprocess.run(["bash", str(SCRIPT), str(ids)], cwd=tmp_path,
                        capture_output=True, text=True,
                        env={**os.environ, "PY": str(fake_py), "CONC": "1", "GCS_BUCKET": ""})
    assert cp.returncode == 0
    assert "✅ 3 ok · ❌ 0 failed" in cp.stdout
    assert "failed events:" not in cp.stdout


# --- ingest fetch retry ---

def test_fetch_retries_transient_exit_then_succeeds(monkeypatch, tmp_path):
    slept, calls = [], {"n": 0}
    monkeypatch.setattr(ingest.time, "sleep", slept.append)
    def flaky(url, dest):
        calls["n"] += 1
        if calls["n"] < 3:
            raise subprocess.CalledProcessError(1, ["yt-dlp"])   # 503/throttle burst
    ingest._fetch_with_retry(flaky, "http://u", tmp_path / "v.mp4")
    assert calls["n"] == 3 and len(slept) == 2                  # bounded backoff, then success


def test_fetch_first_try_success_is_zero_cost(monkeypatch, tmp_path):
    slept = []
    monkeypatch.setattr(ingest.time, "sleep", slept.append)
    ingest._fetch_with_retry(lambda u, d: None, "http://u", tmp_path / "v.mp4")
    assert slept == []                                          # degrade-to-today


def test_fetch_dead_url_still_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest.time, "sleep", lambda *_: None)
    def dead(url, dest):
        raise subprocess.CalledProcessError(22, ["curl"])
    with pytest.raises(subprocess.CalledProcessError):
        ingest._fetch_with_retry(dead, "http://gone", tmp_path / "v.mp4")
