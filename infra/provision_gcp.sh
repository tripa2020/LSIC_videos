#!/usr/bin/env bash
# Provision the GCP resources for the LSIC cloud batch. RUN IN YOUR OWN GCP PROJECT —
# I supply the script + steps; I cannot access your account. Everything here is idempotent
# and parameterised; override any var inline, e.g.  MACHINE_TYPE=e2-standard-16 ./provision_gcp.sh
set -euo pipefail

# --- knobs (override via env) ---
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
ZONE="${ZONE:-us-central1-a}"
MACHINE_TYPE="${MACHINE_TYPE:-e2-standard-8}"   # 8 vCPU, no GPU — pipeline is I/O+API bound
SPOT="${SPOT:-true}"                            # Spot ≈ 70% cheaper; pipeline is resumable
DISK_GB="${DISK_GB:-100}"                       # transient videos (deleted as processed); 100 GB
                                                # stays under a fresh project's 500 GB SSD quota
VM="${VM:-lsic-batch}"
BUCKET="${BUCKET:-gs://${PROJECT}-lsic-reports}"
SA="${SA:-lsic-batch-sa}"

echo "project=$PROJECT zone=$ZONE machine=$MACHINE_TYPE spot=$SPOT bucket=$BUCKET"

# --- 1. GCS bucket for the Report bundles ---
gsutil ls -b "$BUCKET" >/dev/null 2>&1 || gsutil mb -l "${ZONE%-*}" "$BUCKET"

# --- 2. service account (Gemini via API key at runtime; SA just needs GCS write) ---
gcloud iam service-accounts describe "${SA}@${PROJECT}.iam.gserviceaccount.com" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$SA" --display-name="LSIC batch"
gsutil iam ch "serviceAccount:${SA}@${PROJECT}.iam.gserviceaccount.com:roles/storage.objectAdmin" "$BUCKET"

# --- 3. the VM (Ubuntu + Docker via startup script) ---
SPOT_FLAGS=""
[ "$SPOT" = "true" ] && SPOT_FLAGS="--provisioning-model=SPOT --instance-termination-action=STOP"
gcloud compute instances describe "$VM" --zone="$ZONE" >/dev/null 2>&1 || \
gcloud compute instances create "$VM" \
  --zone="$ZONE" --machine-type="$MACHINE_TYPE" $SPOT_FLAGS \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size="${DISK_GB}GB" --boot-disk-type=pd-ssd \
  --service-account="${SA}@${PROJECT}.iam.gserviceaccount.com" \
  --scopes=storage-rw \
  --metadata=startup-script='#!/bin/bash
    apt-get update && apt-get install -y docker.io git
    systemctl enable --now docker'

cat <<EOF

✅ Provisioned. Next steps (run these):

  # ssh in
  gcloud compute ssh $VM --zone=$ZONE

  # on the VM: clone + build the image (~10-30 min; libreoffice layer is the slow part)
  git clone <your-repo-or-scp-the-tree> lsic && cd lsic
  sudo docker build -t lsic-pipeline .

  # SLICE (sync = same output as local): the 5 batch-1 events → GCS
  sudo docker run --rm \\
    -e GEMINI_API_KEY="\$GEMINI_API_KEY" \\
    -e GCS_BUCKET="$BUCKET" \\
    -v \$PWD/work:/app/work \\
    --entrypoint bash lsic-pipeline \\
    download_lsic/run_corpus.sh slice

  # FULL 122 (Gemini Batch, cheaper/async): EXTRA=--batch ... run_corpus.sh filter
EOF
