# AWS / Cloud Scaling Plan — LSIC Briefing Pipeline

> **Status: DEFERRED — plan for later.** Not started. Revisit after the current local
> pilot work (finish the 5-event pilot, parallelization). Captured 2026-06 so the
> research + decisions aren't lost.

## Why this exists

The pipeline is **correct** (validated `notes.md`; Zoom + YouTube/multi-video paths working;
ASR parallelized). The unsolved problems are **throughput, storage, and a flaky home network** —
not code:

1. **Length** — sequential; ~1–3 hr/event × ~180 events = weeks on the laptop.
2. **Storage** — 372 videos = 150–300+ GB; won't fit locally.
3. **Flaky home network** — DNS failures, SSL timeouts, 143 KB/s↔1.5 MB/s download swings keep killing runs.

Goal: a cloud VM for ample storage, fast/stable downloads, parallel execution — process the
corpus fast, then grow into a reusable, multi-source, recurring system.

## Decisions (locked)

- **Target:** a **single large Spot VM** first (simplest; solves all 3 pains). **Not** AWS Batch yet.
- **Cadence:** **one bulk run** to start, but **architect for a future multi-source, recurring system** — later feed in **arbitrary YouTube videos and podcasts**, run repeatedly.
- **Gemini calls:** **synchronous first** (ship it), **Batch API** as a later optimization.

## Key insight (shapes everything)

**I/O- and API-bound, not compute-heavy.** All "AI" is external Gemini API calls; local CPU is
just ffmpeg / opencv / scene-detect / libreoffice. **No GPU needed** → cheap CPU instance. The
cloud wins are bandwidth, storage, and parallel events.

Already fits cloud: **per-event isolation**, **manifest-gated idempotent stages**
(`src/util.py` `is_complete`/`write_with_manifest`), **`work/events.json` read-only after build**,
**per-chunk ASR caching** → parallel workers + resumable runs are natural.

## ⚠️ Verify first: Gemini API tier (likely the real cause of the 503/504s)

Free-tier `gemini-2.5-flash` ≈ **10 RPM** — 8-way parallel ASR blows past it instantly, which
likely explains most of the rate-limit pain seen in the pilot. **Confirm the key is paid-tier
(or raise quota) before scaling parallelism.** Cheap to check; possibly the single highest-impact fix.

## Phase 1 — containerize + one Spot VM (the committed first build)

Deliverables (I prepare; **run in your AWS account — I can't access it**: I supply scripts + steps):

1. **`Dockerfile`** — base + system deps + pip:
   - System: `ffmpeg`/`ffprobe`, `libreoffice` (soffice; PPTX→PDF at `src/pptx_handler.py:83`), `curl`, `pip install -r requirements.txt` (incl. `yt-dlp`, run as `python -m yt_dlp` at `src/ingest.py:133`).
   - Entrypoint `python -m src.main` (already exposes all stages + `--event`/`--all`/`--pipeline`).
   - `GEMINI_API_KEY` via container env — **never baked into the image**.
2. **`download_lsic/run_corpus.sh`** — generalize `run_pilot.sh`: build `events.json` for all selected events, then `xargs -P $CONC` over event ids running the full per-event pipeline (events are isolated). Per-event log + ✅/❌ summary. Bounded-storage delete-after-process per `download_lsic/plan_download_lsic.md`.
3. **Provisioning** (AWS CLI script or tiny Terraform + documented steps):
   - One **`c7g.4xlarge` Spot** (Graviton, no GPU) + **1 TB gp3 EBS** for transient videos.
   - Install Docker → pull image → `docker run -e GEMINI_API_KEY … run_corpus.sh -P 16`.
   - **Artifacts** (small: `transcript.json`, `notes.md`, `captions.json`, `slides.pdf`) `aws s3 sync` to a bucket at the end; transient videos stay on EBS, deleted as processed.

**Solves the 3 pains:** datacenter bandwidth → downloads stop failing; 1 TB EBS → storage;
`-P 16` over isolated events + per-chunk ASR parallelism → weeks → ~12–24 hr.

## Future direction (architect now, build later)

The "add YouTube + podcasts, run repeatedly" goal is **already mostly supported**:
- **Arbitrary sources:** ingestion is `source_url`-driven (`src/ingest.py` `_resolve_video` → yt-dlp/curl). Generalize `download_lsic/` from "LSIC catalog only" to a pluggable **source adapter** (LSIC catalog · arbitrary YouTube · podcast RSS/mp3). yt-dlp handles most podcast/YouTube URLs.
- **Audio-only (podcasts):** the **deck-less event path** built for YouTube (align seeds from metadata, synthesize degrades gracefully) is exactly the podcast shape — audio → transcribe → synthesize, skip visual/decks.
- **Recurring → Phase 2: AWS Batch + S3** — one job per item on Fargate/Spot, S3-backed state (manifest gates map 1:1 to S3 objects), triggered by EventBridge/queue. Turns the single-run VM into a standing service. (Ref: `aws-samples/aws-batch-with-ffmpeg`.)
- **Cost/throughput → Phase 3: Gemini Batch API** — refactor `transcribe.py`/`visual.py`/`synthesize.py` to JSONL batches (audio/images via Files API — confirmed supported). **50% cheaper**, higher limits, no 503 fighting; async 2–6 hr turnaround.

## Cost & time (full ~180-event corpus, order-of-magnitude)

| | Phase 1 (sync, single VM) | + Batch API later |
|---|---|---|
| Gemini API | ~$100 | ~$50 |
| Compute (Spot CPU VM, ~1–2 days) | ~$15–40 | ~$15–40 |
| S3 + transfer (ingress free) | ~$10 | ~$10 |
| **Total** | **~$125–150** | **~$75–100** |
| Wall-clock | ~12–24 hr (16× parallel) | bounded by batch turnaround |

vs. **weeks** sequentially on the laptop.

## Critical files (when Phase 1 starts)
- `Dockerfile` (new), `.dockerignore` (new) — exclude `.env`, `work/`, `LSIC_Downloads/`
- `download_lsic/run_corpus.sh` (new) — parallel-over-events driver
- `infra/` (new) — provisioning script/Terraform + run instructions
- Reused as-is: `src/main.py` entrypoint, `src/ingest.py` (`_resolve_video`), `src/group_manifest.py`, `src/util.py` (manifest gates)

## Verification (when built)
1. **Container parity** (local): `docker build` → `docker run … --pipeline --event lsic_2025-03-27`; diff `notes.md` vs the known-good local one (validate_notes OK).
2. **Tier check** (on VM): `gemini-2.5-flash` at ~12 RPM for 1 min; 429s ⇒ free tier ⇒ upgrade.
3. **Small cloud run**: `run_corpus.sh -P 5` on the 5 pilot events → 5 valid `notes.md`; record wall-clock + cost.
4. **Full run**: all ~180 events; S3 `notes.md` count == expected; spot-check 3; tally spend.

## Web research sources
- AWS Batch + FFmpeg pattern: [AWS Open Source Blog](https://aws.amazon.com/blogs/opensource/create-a-managed-ffmpeg-workflow-for-your-media-jobs-using-aws-batch/) · [aws-samples/aws-batch-with-ffmpeg](https://github.com/aws-samples/aws-batch-with-ffmpeg)
- Batch vs Fargate vs EC2: [AWS Batch](https://aws.amazon.com/batch/) · [EC2 Spot for batch (save 90%)](https://aws.amazon.com/ec2/spot/use-case/batch/)
- Gemini Batch API (50% cheaper, audio via Files API): [Batch API docs](https://ai.google.dev/gemini-api/docs/batch-api) · [Google Developers Blog](https://developers.googleblog.com/scale-your-ai-workloads-batch-mode-gemini-api/) · [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
