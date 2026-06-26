"""On-demand remote execution — run an ad-hoc job on the standard VM, then auto-stop it.

``--remote`` collapses the manual RUNBOOK dance (start → ssh → tmux → run → sync → stop) into
one flag: preflight gcloud → ensure the VM exists → start it → **bootstrap** (clone repo /
build venv / push .env if missing) → sync code → run the pipeline → scp the bundle back to the
local ``--out`` → **stop the VM in a `finally`** (so it auto-stops even on failure; ``--keep-up``
skips it for back-to-back jobs). The VM is the standard (non-preemptible) ``lsic-batch`` from
the cloud-batch work; its disk/venv/.env persist between jobs.

Machine-independent: ssh/scp go in as a **pinned remote user** (``LSIC_SSH_USER``, default
``user``) so a different laptop's local username doesn't land in an empty home. The bootstrap
step makes a fresh machine OR a wiped VM "just work" — each action is gated on an existence
check, so a ready VM is a no-op.

Every gcloud/ssh call goes through an injectable ``runner`` (defaults to ``subprocess.run``) so
the orchestration is unit-tested with a fake recorder — zero network in CI (preflight is skipped
when a fake runner is injected).

NOTE: the remote job runs in the foreground of the ssh call (the laptop idle-waits for the
result). It does NOT compute locally. A tmux-detached variant that survives laptop disconnect
is a future enhancement.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

VM = os.environ.get("LSIC_VM", "lsic-batch")
ZONE = os.environ.get("LSIC_ZONE", "us-central1-a")
SSH_USER = os.environ.get("LSIC_SSH_USER", "user")
REPO_URL = os.environ.get("LSIC_REPO_URL", "https://github.com/tripa2020/LSIC_videos.git")
REMOTE_REPO = f"/home/{SSH_USER}/LSIC_videos"
REMOTE_OUT = f"/home/{SSH_USER}/_lsic_out"
LOCAL_ENV = Path(__file__).resolve().parent.parent / ".env"


def _run(runner, cmd: list[str], **kw):
    return runner(cmd, **{"check": True, "capture_output": True, "text": True, **kw})


def _ssh(runner, remote_cmd: str, **kw):
    return _run(runner, ["gcloud", "compute", "ssh", f"{SSH_USER}@{VM}", "--zone", ZONE,
                         "--tunnel-through-iap", "--quiet", "--command", remote_cmd], **kw)


def preflight() -> None:
    """Fail fast with actionable instructions if gcloud isn't installed / authed (local check)."""
    if shutil.which("gcloud") is None:
        raise RuntimeError(
            "gcloud not found. Install + auth once:\n"
            "  brew install --cask google-cloud-sdk\n"
            "  gcloud init      # log in, pick the project that owns the VM")
    cp = subprocess.run(["gcloud", "auth", "list", "--filter=status:ACTIVE",
                         "--format=value(account)"], capture_output=True, text=True)
    if not (cp.stdout or "").strip():
        raise RuntimeError("No active gcloud account. Run:  gcloud init   (or: gcloud auth login)")


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


def bootstrap_vm(runner) -> None:
    """Make the VM ready, idempotently: clone the repo if absent, build the venv if absent, and
    push the local .env if the VM lacks a Gemini key. A ready VM does no work (all gated)."""
    print(f"[remote] bootstrapping {SSH_USER}@{VM} (repo/venv/.env if missing)…", flush=True)
    _ssh(runner,
         f"test -d {REMOTE_REPO} || git clone {REPO_URL} {REMOTE_REPO}; "
         f"git config --global --add safe.directory {REMOTE_REPO}; "
         f"test -x {REMOTE_REPO}/.venv/bin/python || (cd {REMOTE_REPO} && ./infra/vm_setup.sh)")
    # .env: push the local key up only if the VM doesn't already have one (don't clobber).
    cp = _ssh(runner,
              f"grep -q GEMINI_API_KEY {REMOTE_REPO}/.env 2>/dev/null && echo HAVE_ENV || echo NO_ENV")
    if "NO_ENV" in (cp.stdout or "") and LOCAL_ENV.is_file():
        print("[remote] pushing local .env (VM had none)…", flush=True)
        _run(runner, ["gcloud", "compute", "scp", "--tunnel-through-iap", "--zone", ZONE,
                      str(LOCAL_ENV), f"{SSH_USER}@{VM}:{REMOTE_REPO}/.env"])


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
                  "--zone", ZONE, f"{SSH_USER}@{VM}:{REMOTE_OUT}", str(out)])
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
    """Orchestrate preflight → ensure → start → bootstrap → sync → run → fetch → (finally) stop.
    Returns the rc; the VM is auto-stopped even if a step raises (unless keep_up). Preflight runs
    only on the real subprocess runner (skipped when a fake runner is injected for tests)."""
    if runner is subprocess.run:
        preflight()
    try:
        ensure_vm(runner)
        start_vm(runner)
        bootstrap_vm(runner)
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
