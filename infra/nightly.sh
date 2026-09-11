#!/usr/bin/env bash
# NIGHTLY — the unattended run. Installed as the VM's startup-script, so "start the instance"
# IS the trigger (Cloud Scheduler does exactly that, nothing more — see infra/README.md).
#
# Three moves, nothing else (the bootstrap — repo clone, venv, .env — is one-time via
# infra/vm_setup.sh / `--remote`; this script assumes a provisioned VM):
#   1. fast-forward the repo to origin/$LSIC_BRANCH
#   2. run the ONE list loop locally on the VM — in URL mode (no yt-dlp on a datacenter IP);
#      the loop itself pulls the Telegram inbox first and delivers each ✅ bundle
#   3. shut the VM down (cost control) unless NIGHTLY_KEEP_UP=1
#
# Everything is logged to $HOME/_lsic_nightly.log; the loop's PROGRESS/BATCH_DONE sentinels
# land in $OUT as usual. Safe to re-run: resume-skip makes a second start a no-op.
set -uo pipefail

USER_HOME="${NIGHTLY_HOME:-/home/${LSIC_SSH_USER:-user}}"
REPO="${NIGHTLY_REPO:-$USER_HOME/LSIC_videos}"
OUT="${NIGHTLY_OUT:-$USER_HOME/_lsic_out}"
LINKS="${NIGHTLY_LINKS:-$USER_HOME/_lsic_links.txt}"
BRANCH="${LSIC_BRANCH:-main}"
LOG="$USER_HOME/_lsic_nightly.log"

{
  echo "== nightly $(date -Is) =="
  cd "$REPO" || { echo "repo missing at $REPO — run infra/vm_setup.sh once"; exit 1; }
  git fetch -q origin "$BRANCH" && git reset -q --hard "origin/$BRANCH" \
    && ./.venv/bin/pip install -q -r requirements.txt
  touch "$LINKS"
  YT_INPUT=url PY=./.venv/bin/python ./.venv/bin/python -m src.main \
      --source-list "$LINKS" --local --profile lecture --out "$OUT"
  echo "== done $(date -Is) rc=$? =="
} >> "$LOG" 2>&1

[ "${NIGHTLY_KEEP_UP:-0}" = "1" ] || sudo shutdown -h now
