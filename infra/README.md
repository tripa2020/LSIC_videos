# Cloud run — GCP (Part 2)

You run these in **your own GCP project** (I can't access it). The pipeline is CPU-only and
I/O+API-bound — no GPU. Output is the same `Report/` bundle a local run produces.

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
