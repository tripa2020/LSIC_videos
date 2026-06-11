"""Fakes-only tests for on-demand remote orchestration (src/remote.py).

Contract under test
- Intent: ensure→start→sync→run→fetch→stop the VM for an ad-hoc job; auto-stop in a finally.
- Invariants: the gcloud/ssh sequence runs in order; the VM is stopped even when a step raises;
  --keep-up skips the stop; a missing VM triggers provisioning; an already-RUNNING VM is not
  re-started/re-provisioned.
- Oracles: the ordered list of classified operations a fake runner records (NO network).
"""
import subprocess

import pytest

from src import remote


def _classify(cmd) -> str:
    s = " ".join(map(str, cmd))
    if "provision_gcp.sh" in s:        return "provision"
    if "instances describe" in s:      return "describe"
    if "instances start" in s:         return "start"
    if "instances stop" in s:          return "stop"
    if "scp" in s:                     return "scp"
    if "git fetch" in s:               return "sync"
    if "--source" in s:                return "run"
    return "other"


class FakeRunner:
    """Records each gcloud call as a classified op; returns canned describe status."""
    def __init__(self, status="RUNNING", fail_on=None):
        self.status = status
        self.fail_on = fail_on
        self.ops: list[str] = []

    def __call__(self, cmd, **kw):
        op = _classify(cmd)
        self.ops.append(op)
        if op == self.fail_on:
            raise RuntimeError("boom")
        out = self.status if op == "describe" else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")


def test_remote_run_full_sequence_running_vm():
    r = FakeRunner(status="RUNNING")
    rc = remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert rc == 0
    # RUNNING vm → no provision, no start; ssh sync, ssh run, then auto-stop (out=None → no scp)
    assert "provision" not in r.ops and "start" not in r.ops
    assert r.ops.index("sync") < r.ops.index("run") < r.ops.index("stop")


def test_remote_run_scp_when_out_set(tmp_path):
    r = FakeRunner(status="RUNNING")
    remote.remote_run("https://youtu.be/x", out=tmp_path / "rep", runner=r)
    assert r.ops.index("run") < r.ops.index("scp") < r.ops.index("stop")


def test_auto_stop_on_failure():
    r = FakeRunner(status="RUNNING", fail_on="run")     # job raises
    with pytest.raises(RuntimeError):
        remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert r.ops[-1] == "stop"                          # finally still stopped the VM


def test_keep_up_skips_stop():
    r = FakeRunner(status="RUNNING")
    remote.remote_run("https://youtu.be/x", out=None, keep_up=True, runner=r)
    assert "stop" not in r.ops


def test_missing_vm_triggers_provision():
    r = FakeRunner(status="")           # describe returns empty → VM absent
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert "provision" in r.ops and r.ops.index("provision") < r.ops.index("sync")


def test_terminated_vm_is_started():
    r = FakeRunner(status="TERMINATED")
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert "start" in r.ops and "provision" not in r.ops
