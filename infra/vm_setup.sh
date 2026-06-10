#!/usr/bin/env bash
# One-time NATIVE setup on the VM (no Docker) — the maximum-visibility path: pipeline runs
# stream live to your terminal exactly like a local run. Mirrors the Dockerfile's system deps.
# Run once from the repo root on the VM:  ./infra/vm_setup.sh
set -euo pipefail

sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    ffmpeg libreoffice libgl1 libglib2.0-0 curl fonts-dejavu-core git tmux

python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo
echo "✅ VM ready. Next:"
echo "   echo 'GEMINI_API_KEY=<your key>' > .env"
echo "   VERBOSE=1 CONC=1 GCS_BUCKET=gs://<bucket> ./download_lsic/run_corpus.sh slice"
