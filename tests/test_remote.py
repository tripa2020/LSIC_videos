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
    if "echo ok" in s:                 return "sshprobe"   # post-start ssh-readiness poll
    if "scp" in s and ".lsic_env" in s: return "topupscp"   # key top-up file (before envpush)
    if "scp" in s and ".env" in s:     return "envpush"
    if "scp" in s:                     return "scp"
    if "GEMINI_API_KEY" in s:          return "envcheck"    # cold-start whole-file gate
    if "echo HAVE_" in s:              # generalized per-key presence probe (TOPUP_KEYS)
        return "keycheck:" + s.split("echo HAVE_", 1)[1].split()[0]
    if ">>" in s and ".env" in s:      return "keyappend"   # grep "^KEY=" tmp >> .env (chained)
    if "git clone" in s or "vm_setup.sh" in s: return "bootstrap"
    if "git fetch" in s:               return "sync"
    if "--source" in s:                return "run"
    return "other"


class FakeRunner:
    """Records each gcloud call as a classified op; returns canned describe status + env state.
    ``missing_keys`` = TOPUP_KEYS the fake VM's .env lacks (default: it has them all)."""
    def __init__(self, status="RUNNING", fail_on=None, have_env=True, missing_keys=(),
                 probe_fail=0):
        self.status = status
        self.fail_on = fail_on
        self.have_env = have_env
        self.missing_keys = set(missing_keys)
        self.probe_fail = probe_fail
        self._probes = 0
        self.ops: list[str] = []
        self.cmds: list[str] = []

    def __call__(self, cmd, **kw):
        op = _classify(cmd)
        self.ops.append(op)
        self.cmds.append(" ".join(map(str, cmd)))
        if op == self.fail_on:
            raise RuntimeError("boom")
        if op == "sshprobe" and self._probes < self.probe_fail:
            self._probes += 1
            raise subprocess.CalledProcessError(255, cmd)    # VM not ssh-ready yet
        if op == "describe":
            out = self.status
        elif op == "envcheck":
            out = "HAVE_ENV" if self.have_env else "NO_ENV"
        elif op.startswith("keycheck:"):
            key = op.split(":", 1)[1]
            out = f"NO_{key}" if key in self.missing_keys else f"HAVE_{key}"
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


# --- ssh-readiness gate (cold-start race) ---

def test_waits_for_ssh_before_bootstrap(monkeypatch):
    monkeypatch.setattr(remote.time, "sleep", lambda *_: None)
    r = FakeRunner(status="TERMINATED", probe_fail=2)   # first 2 ssh probes 255, 3rd succeeds
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert r.ops.count("sshprobe") >= 3                 # retried through the boot window
    assert r.ops.index("sshprobe") < r.ops.index("bootstrap")   # gate precedes bootstrap


def test_ssh_probe_exhaustion_still_stops_vm(monkeypatch):
    monkeypatch.setattr(remote.time, "sleep", lambda *_: None)
    r = FakeRunner(status="TERMINATED", probe_fail=999)  # never comes up
    with pytest.raises(Exception):
        remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert r.ops[-1] == "stop"                           # finally still stopped the VM


# --- .env key top-up (cognition key + DEPTH v3 reader context — one mechanism for all) ---

def test_missing_keys_appended_when_vm_lacks_them(monkeypatch):
    monkeypatch.setattr(remote, "_local_env_has", lambda k: True)   # local .env has them all
    r = FakeRunner(status="RUNNING", missing_keys=set(remote.TOPUP_KEYS))
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert "topupscp" in r.ops and "keyappend" in r.ops             # ONE scp, ONE chained append
    assert r.ops.count("topupscp") == 1 and r.ops.count("keyappend") == 1
    assert r.ops.index("keyappend") < r.ops.index("run")            # before the pipeline runs
    append_cmd = next(c for c, op in zip(r.cmds, r.ops) if op == "keyappend")
    for key in remote.TOPUP_KEYS:                                   # every missing key rides it
        assert f"^{key}=" in append_cmd


def test_keys_untouched_when_vm_has_them():
    r = FakeRunner(status="RUNNING")                                # nothing missing
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    assert "topupscp" not in r.ops and "keyappend" not in r.ops


def test_key_not_appended_when_local_lacks_it(monkeypatch):
    # only ship keys the local .env actually holds — a missing local key is skipped, the rest ride
    monkeypatch.setattr(remote, "_local_env_has", lambda k: k == "ANTHROPIC_API_KEY")
    r = FakeRunner(status="RUNNING",
                   missing_keys={"ANTHROPIC_API_KEY", "READER_DOMAIN"})
    remote.remote_run("https://youtu.be/x", out=None, runner=r)
    append_cmd = next(c for c, op in zip(r.cmds, r.ops) if op == "keyappend")
    assert "^ANTHROPIC_API_KEY=" in append_cmd
    assert "READER_DOMAIN" not in append_cmd


def test_reader_context_keys_are_topped_up():
    # the DEPTH v3 env-parity fix: the reader context is IN the top-up set (this absence is
    # exactly how the v3 Transfer Questions silently vanished on the VM)
    assert "READER_DOMAIN" in remote.TOPUP_KEYS
    assert "CURRENT_WORK" in remote.TOPUP_KEYS
    assert "ANTHROPIC_API_KEY" in remote.TOPUP_KEYS


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
