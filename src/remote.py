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
import time
from datetime import date
from pathlib import Path

from src import util

VM = os.environ.get("LSIC_VM", "lsic-batch")
ZONE = os.environ.get("LSIC_ZONE", "us-central1-a")
SSH_USER = os.environ.get("LSIC_SSH_USER", "user")
REPO_URL = os.environ.get("LSIC_REPO_URL", "https://github.com/tripa2020/LSIC_videos.git")
REMOTE_REPO = f"/home/{SSH_USER}/LSIC_videos"
REMOTE_OUT = f"/home/{SSH_USER}/_lsic_out"
REMOTE_LOG = f"/home/{SSH_USER}/_lsic_run.log"
REMOTE_LINKS = f"/home/{SSH_USER}/_lsic_links.txt"
REMOTE_TMP_ENV = "/tmp/.lsic_env"
POLL_SECS = 60      # between job-status polls (each poll is its own short-lived ssh)
POLL_LIMIT = 90     # give a job ≤ 90 polls (~90 min) before declaring it hung
LOCAL_ENV = Path(__file__).resolve().parent.parent / ".env"

# Keys topped-up onto an already-provisioned VM's .env (append-only; one mechanism for all —
# per the complexity review, no per-key copy-paste blocks). ANTHROPIC drives the cognition
# calls; READER_DOMAIN/CURRENT_WORK steer the reader-facing sections (DEPTH v3).
TOPUP_KEYS = ("ANTHROPIC_API_KEY", "READER_DOMAIN", "CURRENT_WORK")


def _local_env_has(key: str) -> bool:
    """True if the local .env defines ``key`` — so we only try to ship keys we actually hold."""
    return LOCAL_ENV.is_file() and any(
        ln.strip().startswith(f"{key}=") for ln in LOCAL_ENV.read_text().splitlines())


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


def wait_for_ssh(runner, attempts: int = 20, delay: int = 6) -> None:
    """Poll a trivial ssh until the freshly-started VM accepts connections (sshd + IAP tunnel + key
    propagation all ready). `gcloud ssh` returns 255 for ~30-90s after `instances start` while the
    guest boots — without this gate the first bootstrap ssh races the boot and aborts the whole run
    (the cold-start failure mode). A warm VM passes on the first probe (~1s)."""
    for i in range(attempts):
        try:
            _ssh(runner, "echo ok")
            return
        except Exception:
            if i == attempts - 1:
                raise
            print(f"[remote] waiting for {VM} ssh to come up… ({i + 1}/{attempts})", flush=True)
            time.sleep(delay)


def bootstrap_vm(runner) -> None:
    """Make the VM ready, idempotently: clone the repo if absent, build the venv if absent, and
    ensure the VM's .env carries the keys the pipeline needs — GEMINI (ASR/VLM/synth) via a cold
    whole-file push when the VM has no .env, and every ``TOPUP_KEYS`` entry (cognition key +
    DEPTH v3 reader context) via an append-only top-up when the VM has a .env but lacks it.
    Never clobbers a VM .env that already has a key; a fully-provisioned VM does no work."""
    print(f"[remote] bootstrapping {SSH_USER}@{VM} (repo/venv/.env if missing)…", flush=True)
    _ssh(runner,
         f"test -d {REMOTE_REPO} || git clone {REPO_URL} {REMOTE_REPO}; "
         f"git config --global --add safe.directory {REMOTE_REPO}; "
         f"test -x {REMOTE_REPO}/.venv/bin/python || (cd {REMOTE_REPO} && ./infra/vm_setup.sh)")
    # GEMINI (cold start): push the whole local .env only if the VM has none (don't clobber).
    cp = _ssh(runner,
              f"grep -q GEMINI_API_KEY {REMOTE_REPO}/.env 2>/dev/null && echo HAVE_ENV || echo NO_ENV")
    if "NO_ENV" in (cp.stdout or "") and LOCAL_ENV.is_file():
        print("[remote] pushing local .env (VM had none)…", flush=True)
        _run(runner, ["gcloud", "compute", "scp", "--tunnel-through-iap", "--zone", ZONE,
                      str(LOCAL_ENV), f"{SSH_USER}@{VM}:{REMOTE_REPO}/.env"])
    # Warm top-up (append-only, generalized — DEPTH v3): keys the pipeline needs beyond GEMINI.
    # A VM provisioned earlier has a .env missing newer keys → the whole local .env travels ONCE
    # in an scp'd file (values never in an ssh argv) and each missing key is grep-appended.
    # Skipped per key when the VM already has it or the local .env lacks it. This is how the
    # v3 Transfer Questions vanished: READER_DOMAIN never reached the VM (env-parity bug class).
    missing = []
    for key in TOPUP_KEYS:
        cp = _ssh(runner, f"grep -q '^{key}=' {REMOTE_REPO}/.env 2>/dev/null "
                          f"&& echo HAVE_{key} || echo NO_{key}")
        if f"NO_{key}" in (cp.stdout or "") and _local_env_has(key):
            missing.append(key)
    if missing:
        print(f"[remote] appending {', '.join(missing)} to VM .env…", flush=True)
        _run(runner, ["gcloud", "compute", "scp", "--tunnel-through-iap", "--zone", ZONE,
                      str(LOCAL_ENV), f"{SSH_USER}@{VM}:{REMOTE_TMP_ENV}"])
        appends = " && ".join(f'grep "^{k}=" {REMOTE_TMP_ENV} >> {REMOTE_REPO}/.env'
                              for k in missing)
        _ssh(runner, f"{appends} && rm -f {REMOTE_TMP_ENV}")


def sync_code(runner) -> None:
    """Fast-forward the VM's clone to ``origin/<branch>`` and refresh deps (picks up new
    requirements). ``branch`` = env ``LSIC_BRANCH`` (default ``main``) — the knob that lets a
    feature branch be verified on the VM before it merges to main."""
    branch = os.environ.get("LSIC_BRANCH", "main")
    _ssh(runner, f"cd {REMOTE_REPO} && git fetch -q origin {branch} "
                 f"&& git reset -q --hard origin/{branch} "
                 f"&& ./.venv/bin/pip install -q -r requirements.txt")


def run_remote_job(runner, source: str, profile: str | None = None) -> None:
    prof = f" --profile {profile}" if profile else ""
    # LSIC_REDO_BRIEFING: clear the briefing stage for THIS event so synthesis re-runs with the
    # freshly-synced code — the stage is idempotent, so a cached notes.md would otherwise skip it.
    # Upstream (ingest/transcribe/visual/align) stays cached ⇒ only the cheap synth re-runs.
    prep = ""
    if os.environ.get("LSIC_REDO_BRIEFING"):
        from src.adhoc import mint_event_id
        eid = mint_event_id(None, source, date.today())
        stage_dir = f"work/events/{eid}/{util.STAGE_BRIEFING}"
        prep = f"rm -rf {stage_dir} && "
        print(f"[remote] redo: clearing {stage_dir} so synth re-runs…", flush=True)
    launch = (f"cd {REMOTE_REPO} && {prep}rm -rf {REMOTE_OUT} && "
              f"nohup env PY=./.venv/bin/python ./.venv/bin/python -m src.main "
              f"--source '{source}'{prof} --out {REMOTE_OUT}")
    _launch_and_poll(runner, launch, f"test -f {REMOTE_OUT}/notes.md", POLL_LIMIT)


def run_remote_batch(runner, source_list: Path, profile: str = "lecture",
                     redo: bool = False, n_links: int = 1) -> None:
    """RUNEASY remote: push the links FILE to the VM (never URL-in-ssh-argv — the quoting/
    injection surface, Q6) and run the SAME list loop there (`--source-list … --local`, CR1).
    The loop's PROGRESS/BATCH_DONE files are the whole poll interface (CR2); the deadline
    scales with list length (CR3). REMOTE_OUT is NOT wiped — skip-completed resume needs the
    finished subfolders; only stale sentinels are cleared."""
    _run(runner, ["gcloud", "compute", "scp", "--tunnel-through-iap", "--zone", ZONE,
                  str(source_list), f"{SSH_USER}@{VM}:{REMOTE_LINKS}"])
    redo_flag = " --redo" if redo else ""
    launch = (f"cd {REMOTE_REPO} && rm -f {REMOTE_OUT}/BATCH_DONE {REMOTE_OUT}/PROGRESS && "
              f"nohup env PY=./.venv/bin/python ./.venv/bin/python -m src.main "
              f"--source-list {REMOTE_LINKS} --local{redo_flag} --profile {profile} "
              f"--out {REMOTE_OUT}")
    _launch_and_poll(runner, launch, f"test -f {REMOTE_OUT}/BATCH_DONE",
                     POLL_LIMIT * max(1, n_links), progress_path=f"{REMOTE_OUT}/PROGRESS")


def _launch_and_poll(runner, launch_body: str, done_test: str, poll_limit: int,
                     progress_path: str | None = None) -> None:
    """The ONE detached-launch + stateless-poll machine (FIX pattern; CR2) shared by the
    single-source job and the RUNEASY batch — callers differ only in launch command, done
    test, and deadline. Why detached: gcloud's IAP ssh drops on long silent stretches (a
    Fable cognition pass thinks for minutes with no output) — a blocking ssh killed the first
    v4.1 run mid-job and its stdout (incl. the cost lines) died with the channel. The only
    cross-poll state is the last-printed PROGRESS line (CR3 — no stall state machine)."""
    _ssh(runner, f"{launch_body} > {REMOTE_LOG} 2>&1 < /dev/null & echo LAUNCHED")
    probe = ((f"cat {progress_path} 2>/dev/null; " if progress_path else "")
             + f"{done_test} && echo POLL_DONE || "
               f"(pgrep -f '[s]rc.main' >/dev/null && echo POLL_RUNNING || echo POLL_DEAD)")
    last_progress = ""
    for _ in range(poll_limit):
        cp = _ssh(runner, probe)
        state = cp.stdout or ""
        if progress_path:
            prog = state.split("POLL_", 1)[0].strip()
            if prog and prog != last_progress:
                print(f"  [vm] {prog}", flush=True)
                last_progress = prog
        if "POLL_DONE" in state:
            break
        if "POLL_DEAD" in state:
            _print_remote_log(runner)
            raise RuntimeError("remote job died before finishing (log tail above)")
        time.sleep(POLL_SECS)
    else:
        raise RuntimeError(f"remote job exceeded its deadline (~{poll_limit * POLL_SECS // 60} "
                           f"min) — inspect {REMOTE_LOG} on the VM")
    _print_remote_log(runner)


def _print_remote_log(runner) -> None:
    """Surface the VM-side run log locally (cost lines + tail) — best-effort, never fatal."""
    try:
        cp = _ssh(runner, f"grep -E '\\[anthropic\\]|\\[cognition\\]' {REMOTE_LOG} | tail -12; "
                          f"echo ---; tail -n 6 {REMOTE_LOG}")
        for line in (cp.stdout or "").splitlines():
            print(f"  [vm] {line}", flush=True)
    except Exception:
        pass


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


def remote_run(source: str | None, *, out=None, profile: str | None = None,
               keep_up: bool = False, runner=subprocess.run,
               source_list=None, redo: bool = False) -> int:
    """Orchestrate preflight → ensure → start → bootstrap → sync → run → fetch → (finally) stop.
    ``source_list`` (RUNEASY) runs the batch loop ON the VM instead of a single ``source``.
    Returns the rc; the VM is auto-stopped even if a step raises (unless keep_up). Preflight runs
    only on the real subprocess runner (skipped when a fake runner is injected for tests)."""
    if runner is subprocess.run:
        preflight()
    try:
        ensure_vm(runner)
        start_vm(runner)
        wait_for_ssh(runner)
        bootstrap_vm(runner)
        sync_code(runner)
        if source_list is not None:
            from src.adhoc import _parse_links
            n = len(_parse_links(Path(source_list).read_text()))
            print(f"[remote] running {n} links from {source_list} on {VM}…", flush=True)
            run_remote_batch(runner, Path(source_list), profile=profile or "lecture",
                             redo=redo, n_links=n)
        else:
            print(f"[remote] running {source} on {VM}…", flush=True)
            run_remote_job(runner, source, profile)
        if out is not None:
            fetch_report(runner, out)
            print(f"[remote] bundle → {Path(out).expanduser()}", flush=True)
        return 0
    finally:
        if not keep_up:
            stop_vm(runner)
