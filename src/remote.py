"""On-demand remote execution — run an ad-hoc job on the standard VM, then auto-stop it.

``--remote`` collapses the manual RUNBOOK dance (start → ssh → tmux → run → sync → stop) into
one flag: ensure the VM exists → start it → sync code → run the pipeline → scp the bundle back
to the local ``--out`` → **stop the VM in a `finally`** (so it auto-stops even on failure;
``--keep-up`` skips it for back-to-back jobs). The VM is the standard (non-preemptible)
``lsic-batch`` from the cloud-batch work; its disk/venv/.env persist between jobs.

Every gcloud/ssh call goes through an injectable ``runner`` (defaults to ``subprocess.run``) so
the orchestration is unit-tested with a fake recorder — zero network in CI.

NOTE: the remote job runs in the foreground of the ssh call (the laptop idle-waits for the
result). It does NOT compute locally. A tmux-detached variant that survives laptop disconnect
is a future enhancement.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

VM = os.environ.get("LSIC_VM", "lsic-batch")
ZONE = os.environ.get("LSIC_ZONE", "us-central1-a")
REMOTE_REPO = "~/LSIC_videos"
REMOTE_OUT = "~/_lsic_out"


def _run(runner, cmd: list[str], **kw):
    return runner(cmd, **{"check": True, "capture_output": True, "text": True, **kw})


def _ssh(runner, remote_cmd: str, **kw):
    return _run(runner, ["gcloud", "compute", "ssh", VM, "--zone", ZONE,
                         "--tunnel-through-iap", "--command", remote_cmd], **kw)


def vm_status(runner) -> str | None:
    """RUNNING / TERMINATED / … or None if the VM does not exist (describe fails)."""
    try:
        cp = _run(runner, ["gcloud", "compute", "instances", "describe", VM,
                           "--zone", ZONE, "--format=value(status)"])
        return (cp.stdout or "").strip() or None
    except Exception:
        return None


def ensure_vm(runner) -> None:
    """Create the VM (+ bucket/SA/firewall) via the idempotent provisioner if it's missing."""
    if vm_status(runner) is None:
        print(f"[remote] {VM} not found — provisioning…", flush=True)
        _run(runner, ["bash", "infra/provision_gcp.sh"])


def start_vm(runner) -> None:
    if vm_status(runner) != "RUNNING":
        print(f"[remote] starting {VM}…", flush=True)
        _run(runner, ["gcloud", "compute", "instances", "start", VM, "--zone", ZONE])


def sync_code(runner) -> None:
    """Fast-forward the VM's clone to origin/main and refresh deps (picks up new requirements)."""
    _ssh(runner, f"cd {REMOTE_REPO} && git fetch -q origin main && git reset -q --hard origin/main "
                 f"&& ./.venv/bin/pip install -q -r requirements.txt")


def run_remote_job(runner, source: str, profile: str | None = None) -> None:
    prof = f" --profile {profile}" if profile else ""
    _ssh(runner,
         f"cd {REMOTE_REPO} && rm -rf {REMOTE_OUT} && "
         f"PY=./.venv/bin/python ./.venv/bin/python -m src.main "
         f"--source '{source}'{prof} --out {REMOTE_OUT}",
         timeout=None)


def fetch_report(runner, out) -> None:
    """scp the bundle from the VM back to the local --out folder (flattened)."""
    out = Path(out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    _run(runner, ["gcloud", "compute", "scp", "--recurse", "--tunnel-through-iap",
                  "--zone", ZONE, f"{VM}:{REMOTE_OUT}", str(out)])
    landed = out / "_lsic_out"          # scp --recurse lands the dir as out/_lsic_out/ → flatten
    if landed.is_dir():
        for f in landed.iterdir():
            f.replace(out / f.name)
        landed.rmdir()


def stop_vm(runner) -> None:
    print(f"[remote] stopping {VM} (cost control)…", flush=True)
    _run(runner, ["gcloud", "compute", "instances", "stop", VM, "--zone", ZONE])


def remote_run(source: str, *, out=None, profile: str | None = None,
               keep_up: bool = False, runner=subprocess.run) -> int:
    """Orchestrate ensure → start → sync → run → fetch → (finally) stop. Returns the rc; the
    VM is auto-stopped even if a step raises (unless keep_up)."""
    try:
        ensure_vm(runner)
        start_vm(runner)
        sync_code(runner)
        print(f"[remote] running {source} on {VM}…", flush=True)
        run_remote_job(runner, source, profile)
        if out is not None:
            fetch_report(runner, out)
            print(f"[remote] bundle → {Path(out).expanduser()}", flush=True)
        return 0
    finally:
        if not keep_up:
            stop_vm(runner)
