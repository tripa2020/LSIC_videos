# RUNBOOK — run the cloud slice with maximum visibility

Easiest install + most visibility: **git remote** to ship the code, **native** run on the VM
(no Docker layer), inside **tmux** so it survives disconnects and streams live — the exact
per-stage output you watch locally. (Docker stays available for the reproducible full-122 run.)

You run all of this; I can't access GitHub or GCP. `<...>` = fill in.

---

## A. Git remote (run on your laptop — you're already `gh`-authed)

```bash
cd /Users/user/LSIC_videos
gh repo create LSIC_videos --private --source=. --remote=origin
git push -u origin main
```

## B. Install gcloud + provision the VM (laptop)

```bash
brew install --cask google-cloud-sdk && gcloud init     # pick/create project, login
export PROJECT=$(gcloud config get-value project) ZONE=us-central1-a VM=lsic-batch
export BUCKET=gs://${PROJECT}-lsic-reports
PROJECT=$PROJECT ZONE=$ZONE BUCKET=$BUCKET ./infra/provision_gcp.sh
```

## C. On the VM — clone, install, key (native)

```bash
gcloud compute ssh $VM --zone=$ZONE          # now on the VM
tmux new -s lsic                             # ← survives disconnect; Ctrl-b d detaches, `tmux a -t lsic` reattaches
git clone https://github.com/<you>/LSIC_videos.git && cd LSIC_videos
./infra/vm_setup.sh                          # apt deps + venv + pip  (~5 min)
echo 'GEMINI_API_KEY=<your key>' > .env
```

## D. Run the 5-event slice — LIVE (VERBOSE), sync = same output as local

```bash
VERBOSE=1 CONC=1 GCS_BUCKET=$BUCKET ./download_lsic/run_corpus.sh slice
```
Every stage streams to your terminal (`ingest → transcribe → visual → align → synth → slide_book → report`) and is also saved to `logs/<event>.log`. Five `✅`/`❌` lines at the end; each `Report/` syncs to GCS.

## E. Visibility while it runs (and after)

| Want to see… | Do this |
|--------------|---------|
| live stage output | it's already streaming (VERBOSE); detach/reattach with tmux |
| a specific event's log | `tail -f logs/lsic_2025-09-25.log` (second tmux pane: Ctrl-b ") |
| per-event stage matrix | `./.venv/bin/python -m src.main --status` |
| bundles as they land | GCS browser in Cloud Console, or `gsutil ls -r $BUCKET` |
| VM health (CPU/net) | Cloud Console → Compute Engine → the VM → Monitoring |

## F. Verify (resolves OQ1/OQ2)

1. **Gemini tier (OQ1):** if transcribe shows `429`, the key is free-tier → re-run with `ASR_CONCURRENCY=3 VERBOSE=1 … run_corpus.sh slice`.
2. **Parity:** `ls work/events/*/Report/` → each has `notes.md, slide_captions.md, slides.pdf, equations.md`. Diff one `notes.md` against your local known-good.

## G. Pull bundles back to your laptop

```bash
gsutil -m rsync -r $BUCKET ./cloud_reports
```

## H. Later — full 122 (Gemini Batch, after batch ≡ sync is confirmed on one event)

```bash
EXTRA=--batch CONC=4 GCS_BUCKET=$BUCKET ./download_lsic/run_corpus.sh filter
```

---

### Undo / cost control
- Stop the VM when idle: `gcloud compute instances stop $VM --zone=$ZONE` (Spot also auto-stops on preempt; just re-run — resumable).
- Delete everything: `gcloud compute instances delete $VM --zone=$ZONE` + `gsutil rm -r $BUCKET`.
- Delete the GitHub repo: `gh repo delete LSIC_videos`.
