# Cloud run — GCP (Part 2)

You run these in **your own GCP project** (I can't access it). The pipeline is CPU-only and
I/O+API-bound — no GPU. Output is the same `Report/` bundle a local run produces.

## Nightly, unattended (the morning-commute wrapper — 2026-09-11)

No laptop in the loop. Three parts, each already built:

| Part      | Mechanism                                                                                      |
|-----------|------------------------------------------------------------------------------------------------|
| Inbox     | Send links to your Telegram bot from the phone; the loop pulls them into `_lsic_links.txt`     |
| Runner    | `infra/nightly.sh` as the VM **startup-script**: sync → `run_all --local` in **URL mode** → shutdown |
| Delivery  | Each ✅ bundle (notes.md, coverage, references, slides.pdf) is sent back to the same chat       |

URL mode (`YT_INPUT=url`) means Gemini reads the public YouTube URL server-side — nothing is
downloaded, so the datacenter-IP block that pinned July's batch to the laptop never applies.

**One-time setup (run once, laptop):**

```bash
export PROJECT=$(gcloud config get-value project) ZONE=us-central1-a VM=lsic-batch

# 1. Telegram: create a bot with @BotFather → token; message it once, then read your chat id:
#    curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | grep -o '"chat":{"id":[0-9-]*'
#    Put both in the local .env; a `--remote` run tops them up on the VM automatically
#    (remote.py TOPUP_KEYS), or append by hand:
#      echo 'TELEGRAM_BOT_TOKEN=…' >> ~/LSIC_videos/.env ; echo 'TELEGRAM_CHAT_ID=…' >> …

# 2. the startup-script = nightly.sh (runs on every instance start)
gcloud compute instances add-metadata $VM --zone $ZONE \
  --metadata-from-file startup-script=infra/nightly.sh

# 3. a scheduler that just STARTS the instance (the script does the rest and shuts it down)
gcloud services enable cloudscheduler.googleapis.com
gcloud iam service-accounts create lsic-nightly --display-name "LSIC nightly starter"
gcloud projects add-iam-policy-binding $PROJECT \
  --member "serviceAccount:lsic-nightly@$PROJECT.iam.gserviceaccount.com" \
  --role roles/compute.instanceAdmin.v1
gcloud scheduler jobs create http lsic-nightly --location us-central1 \
  --schedule "0 3 * * *" --time-zone "America/Los_Angeles" --http-method POST \
  --uri "https://compute.googleapis.com/compute/v1/projects/$PROJECT/zones/$ZONE/instances/$VM/start" \
  --oidc-service-account-email "lsic-nightly@$PROJECT.iam.gserviceaccount.com"
```

**Try it now:** `gcloud scheduler jobs run lsic-nightly --location us-central1`, then watch
`gcloud compute ssh user@$VM --zone $ZONE --tunnel-through-iap -- tail -f ~/_lsic_nightly.log`.
The VM shuts itself down at the end; the bundles are on your phone.

Knobs (VM metadata or `.env`): `NIGHTLY_KEEP_UP=1` skips the shutdown; `LSIC_BRANCH` picks the
branch; `YT_INPUT` unset falls back to yt-dlp (laptop/residential only).

## TL;DR

```bash
# 1. provision (idempotent; override MACHINE_TYPE/SPOT/BUCKET as needed)
PROJECT=my-proj ZONE=us-central1-a ./infra/provision_gcp.sh

# 2. on the VM: build the image, then run the slice (SYNC = identical to local)
sudo docker build -t lsic-pipeline .
GEMINI_API_KEY=…  GCS_BUCKET=gs://…  ./download_lsic/run_corpus.sh slice

# 3. full 122 later (Gemini Batch, cheaper + async)
EXTRA=--batch  CONC=4  ./download_lsic/run_corpus.sh filter
```

## What each piece does

| Piece | Role |
|-------|------|
| `Dockerfile` | packages the validated pipeline (ffmpeg + libreoffice + deps); entrypoint `python -m src.main` |
| `infra/provision_gcp.sh` | GCS bucket + service account + Spot `e2-standard-8` VM with Docker |
| `download_lsic/run_corpus.sh` | fetch decks → group (relocate) → pipeline per event → GCS sync; `slice` / `filter` / `<ids-file>` |

## Run modes

| Mode | Flag | Output vs local | When |
|------|------|-----------------|------|
| **Sync** | (default) | **identical** (same code path you validated) | the 5-event slice — guarantees "same state" |
| Batch | `EXTRA=--batch` | quality-equivalent, not byte-identical | the full 122 — 50% cheaper, no 503s, async wait |

## Verify-first on the VM (resolves OQ1/OQ2)

1. **Gemini tier (OQ1):** run one event sync first. If ASR throws 429s, the key is free-tier — raise quota or set `ASR_CONCURRENCY=3`. Batch needs a paid tier.
2. **Container parity (M-C1 gate):** `docker run … --pipeline --event lsic_2025-07-24` then diff `work/events/lsic_2025-07-24/Report/notes.md` vs the known-good local one.
3. **Batch ≡ sync (before Part 3):** run one event both ways; confirm the bundles match in structure before trusting Batch on all 122.

## Knobs (env vars on `run_corpus.sh`)

`CAP_HOURS=4` (aggregate-video cap) · `CONC=4` (parallel events) · `EXTRA=--batch` · `GCS_BUCKET=gs://…` · `PY=python`
