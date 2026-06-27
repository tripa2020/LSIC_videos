"""Fakes-only tests for on-demand remote orchestration (src/remote.py).

Contract under test
- Intent: preflight→ensure→start→bootstrap→sync→run→fetch→stop the VM for an ad-hoc job;
  auto-stop in a finally.
- Invariants: the gcloud/ssh sequence runs in order; the VM is stopped even when a step raises;
  --keep-up skips the stop; a missing VM triggers provisioning; an already-RUNNING VM is not
  re-started/re-provisioned; bootstrap runs before sync; the local .env is pushed only when the
  VM lacks a Gemini key; ssh/scp target the pinned remote user.
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
    if "scp" in s and ".lsic_env" in s: return "antscp"     # ANTHROPIC top-up file (before envpush)
    if "scp" in s and ".env" in s:     return "envpush"
    if "scp" in s:                     return "scp"
    if "ANTHROPIC_API_KEY" in s and ("HAVE_ANT" in s or "NO_ANT" in s): return "antcheck"
    if "ANTHROPIC_API_KEY" in s:       return "antappend"   # grep ANTHROPIC… >> .env
    if "GEMINI_API_KEY" in s:          return "envcheck"
    if "git clone" in s or "vm_setup.sh" in s: return "bootstrap"
    if "git fetch" in s:               return "sync"
    if "--source" in s:                return "run"
    return "other"


class FakeRunner:
    """Records each gcloud call as a classified op; returns canned describe status + env state."""
    def __init__(self, status="RUNNING", fail_on=None, have_env=True, have_ant=True):
        self.status = status
        self.fail_on = fail_on
        self.have_env = have_env
        self.have_ant = have_ant
        self.ops: list[str] = []
        self.cmds: list[str] = []

    def __call__(self, cmd, **kw):
        op = _classify(cmd)
        self.ops.append(op)
        self.cmds.append(" ".join(map(str, cmd)))
        if op == self.fail_on:
            raise RuntimeError("boom")
        if op == "describe":
            out = self.status
        elif op == "envcheck":
            out = "HAVE_ENV" if self.have_env else "NO_ENV"
        elif op == "antcheck":
            out = "HAVE_ANT" if self.have_ant else "NO_ANT"
        else:
            out = ""
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")


def test_remote_run_full_sequence_running_vm():
    r = FakeRunner(status="RUNNING")
    rc = remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert rc == 0
    # RUNNING vm → no provision, no start; bootstrap → sync → run → auto-stop (out=None → no scp)
    assert "provision" not in r.ops and "start" not in r.ops
    assert r.ops.index("bootstrap") < r.ops.index("sync") < r.ops.index("run") < r.ops.index("stop")


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


def test_bootstrap_runs_before_sync():
    r = FakeRunner(status="RUNNING")
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    # bootstrap (clone/venv) must precede the git-fetch sync that assumes the repo exists
    assert "bootstrap" in r.ops and r.ops.index("bootstrap") < r.ops.index("sync")


def test_env_pushed_only_when_vm_lacks_key():
    # VM already has a key → no push
    r_have = FakeRunner(status="RUNNING", have_env=True)
    remote.remote_run("https://youtu.be/x", out=None, runner=r_have)
    assert "envpush" not in r_have.ops
    # VM lacks a key → push the local .env (the repo root .env exists in this checkout)
    r_none = FakeRunner(status="RUNNING", have_env=False)
    remote.remote_run("https://youtu.be/x", out=None, runner=r_none)
    assert "envpush" in r_none.ops and r_none.ops.index("envpush") < r_none.ops.index("run")


def test_ssh_targets_pinned_user():
    r = FakeRunner(status="RUNNING")
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    target = f"{remote.SSH_USER}@{remote.VM}"
    ssh_cmds = [c for c in r.cmds if "compute ssh" in c]
    assert ssh_cmds and all(target in c for c in ssh_cmds)   # every ssh goes in as SSH_USER@VM
    # instance lifecycle ops use the bare instance name, never user@
    assert all(target not in c for c in r.cmds if "instances " in c)


# --- ANTHROPIC key top-up (Opus cognition) ---

def test_anthropic_key_appended_when_vm_lacks_it(monkeypatch):
    monkeypatch.setattr(remote, "_local_env_has", lambda k: True)   # local .env has the key
    r = FakeRunner(status="RUNNING", have_ant=False)                # VM lacks it
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert "antscp" in r.ops and "antappend" in r.ops               # scp file up, append the line
    assert r.ops.index("antappend") < r.ops.index("run")           # before the pipeline runs


def test_anthropic_key_untouched_when_vm_has_it():
    r = FakeRunner(status="RUNNING", have_ant=True)
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert "antscp" not in r.ops and "antappend" not in r.ops


def test_anthropic_not_appended_when_local_lacks_key(monkeypatch):
    monkeypatch.setattr(remote, "_local_env_has", lambda k: False)  # can't ship a key we don't have
    r = FakeRunner(status="RUNNING", have_ant=False)
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert "antappend" not in r.ops


# --- branch selection (verify a feature branch on the VM before merge) ---

def test_sync_uses_configured_branch(monkeypatch):
    monkeypatch.setenv("LSIC_BRANCH", "alex/mapred-windows")
    r = FakeRunner(status="RUNNING")
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    sync_cmd = next(c for c, op in zip(r.cmds, r.ops) if op == "sync")
    assert "origin/alex/mapred-windows" in sync_cmd


def test_sync_defaults_to_main(monkeypatch):
    monkeypatch.delenv("LSIC_BRANCH", raising=False)
    r = FakeRunner(status="RUNNING")
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    sync_cmd = next(c for c, op in zip(r.cmds, r.ops) if op == "sync")
    assert "origin/main" in sync_cmd


# --- redo-briefing (force synth to re-run with the synced code) ---

def test_redo_briefing_clears_stage_in_run_cmd(monkeypatch):
    monkeypatch.setenv("LSIC_REDO_BRIEFING", "1")
    r = FakeRunner(status="RUNNING")
    remote.remote_run("https://www.youtube.com/watch?v=lXUZvyajciY", out=None, runner=r)
    run_cmd = next(c for c, op in zip(r.cmds, r.ops) if op == "run")
    assert "rm -rf work/events/yt_lXUZvyajciY/05_briefing" in run_cmd


def test_redo_briefing_off_by_default(monkeypatch):
    monkeypatch.delenv("LSIC_REDO_BRIEFING", raising=False)
    r = FakeRunner(status="RUNNING")
    remote.remote_run("https://www.youtube.com/watch?v=lXUZvyajciY", out=None, runner=r)
    run_cmd = next(c for c, op in zip(r.cmds, r.ops) if op == "run")
    assert "05_briefing" not in run_cmd
