# Session Handoff — LSIC Briefing Pipeline

_For the next agent. Read `.claude/CLAUDE.md` first (operating discipline), then this._
_Address the user as **C'mmandr**. Pad all markdown tables (CLAUDE.md §9)._

---

## TL;DR

The **LSIC Event → Briefing pipeline** (audio/video/decks → per-event `notes.md` + slide book)
works end-to-end. This session built the **acquisition front-end** (scrape → filter → download),
**multi-video + YouTube** support, **Layout B** per-event folders, observability (`--status`),
a resilient launcher (`--keep-going`), and **crash-proofed + sped up the ASR calls**. The
5-event pilot is effectively done: **6/7 events have a `notes.md`**.

The remaining pain is **environmental, not code**: the home network's DNS/SSL flakiness and
Gemini's 503 capacity spikes. The durable fixes are already planned — **Gemini Batch API**
(kills 503s) and the **cloud VM move** (kills DNS/SSL flakiness).

---

## Git state — READ THIS FIRST

| Item                | State                                                                 |
|---------------------|-----------------------------------------------------------------------|
| Current branch      | `alex/asr-crashfix-speed` (off `main` @ `c2adcb0`)                      |
| Committed here      | `ffe6ca5` crash-fix+structured-output+`run_event_stages`+tests · `2060d63` inline 32k Opus+concurrency · `a0c3abc` unified DNS-aware transient retry |
| Tests               | `.venv/bin/python -m pytest tests/ -q` → **11 passed** (fakes-only, no network) |
| ⚠️ Uncommitted work | **Substantial — at risk.** See below.                                  |

**Uncommitted (source only; `work/` + `LSIC_Downloads/` are gitignored):**

| Path                    | What it is                                                      | Suggested branch                |
|-------------------------|----------------------------------------------------------------|---------------------------------|
| `download_lsic/`        | Acquisition front-end (harvest/select/fetch_docs + plans)       | `alex/acquisition-frontend`     |
| `src/group_manifest.py` | Build `events.json` from the catalog (Layout B, multi-video)    | `alex/acquisition-frontend`     |
| `src/contracts.py` (M)  | `VideoPart`, optional `lsic_id`/`path`, `source_url`, `meta`     | `alex/multi-video`              |
| `src/ingest.py` (M)     | Multi-video concat, URL fetch (yt-dlp/curl), resumable, dead-skip| `alex/multi-video`              |
| `src/align.py` (M)      | `t=` presentation seeding for deck-less YouTube events           | `alex/multi-video`              |
| `PLAN.md` (M)           | CLI-flags doc note                                              | (fold into the above)           |
| `AWS_batch.md`          | Deferred cloud-scaling plan                                     | doc — commit anytime            |
| `.claude/`, `.mcp.json` | CLAUDE.md/preferences/roles, settings, gemini-docs MCP          | config — commit anytime         |

> Per CLAUDE.md §2/§3 (one feature → one branch, commit frequently): the multi-video and
> acquisition work should be split into their own branches **with a `/python-unit-tests` gate**
> and committed — right now they live only in the working tree. The committed branch HEAD is
> **not self-consistent without them** (e.g. `src.group_manifest` is referenced but untracked).

---

## Pilot status (run `python -m src.main --status` for live)

| event             | through        | gets notes.md? | to finish                          |
|-------------------|----------------|----------------|------------------------------------|
| lsic_2020-02-28   | DONE (YouTube) | ✅              | —                                  |
| lsic_2025-06-25   | DONE (2 video) | ✅              | —                                  |
| lsic_2025-09-24   | DONE (2 video) | ✅              | —                                  |
| lsic_2026-03-26   | DONE (golden)  | ✅              | —                                  |
| lsic_2025-03-27   | slides ✅, report · | ✅ (in 05_briefing) | `--report --event lsic_2025-03-27` |
| lsic_2026-01-29   | slides ✅, report · | ✅ (in 05_briefing) | `--report --event lsic_2026-01-29` |
| lsic_2025-10-15   | nothing        | ❌              | needs ingest (video download), then pipeline |

Finish the pilot:
```bash
.venv/bin/python -m src.main --report --event lsic_2025-03-27
.venv/bin/python -m src.main --report --event lsic_2026-01-29
.venv/bin/python -m src.main --pipeline --event lsic_2025-10-15 --keep-going
```

---

## What the pipeline does (orientation)

```
catalog (public Products.php JS array)
  → harvest → download_manifest.json (1184) → select → selected_manifest.json (714 / ~180 events)
  → group_manifest → work/events.json (+ per-event meta.json)        [Layout B: LSIC_Downloads/lsic_<date>/]
  → per event: ingest → transcribe → visual → align → synthesize → slide_book → report
                (audio)  (Gemini ASR) (VLM)  (sections)  (Gemini Pro) (VLM)   (Report/)
  → work/events/<id>/Report/{notes.md, slides.pdf, slide_captions.md}
```
Each stage is **manifest-gated** (`util.is_complete`) → idempotent + resumable. Source of truth
for design: **`PLAN.md`** (pipeline) and **`download_lsic/plan_download_lsic.md`** (acquisition).

---

## Key files

| Area                | File(s)                                                                 |
|---------------------|------------------------------------------------------------------------|
| CLI entry / stages  | `src/main.py` (`--pipeline --all --keep-going`, `--status`, `--report`) |
| ASR (this session)  | `src/transcribe.py` — split-on-`MAX_TOKENS`, inline 32k Opus, structured output |
| Shared retry        | `src/util.py` `is_transient()` (DNS+503+disconnect; one source of truth) |
| Grouping            | `src/group_manifest.py` (uncommitted)                                   |
| Acquisition         | `download_lsic/{harvest,select_manifest,fetch_docs}.py` (uncommitted)   |
| Tests               | `tests/test_transcribe.py`, `tests/test_pipeline.py` (11, fakes-only)   |
| Plans               | `PLAN.md`, `download_lsic/plan_download_lsic.md`, `AWS_batch.md`, `~/.claude/plans/now-i-want-you-cuddly-backus.md` (ASR speed plan) |

---

## Blockers (environmental, not code)

| Wall                          | Cause                          | Durable fix                              |
|-------------------------------|--------------------------------|------------------------------------------|
| `503 high demand`             | Gemini server capacity         | **Phase 2: Batch API** (no 503 fighting) |
| `[Errno 8] nodename...` / SSL | Home network DNS/SSL flakiness | **Cloud VM** (`AWS_batch.md`)            |

Retries now absorb *brief* spikes of both across all 3 Gemini stages; sustained outages still
need the cloud move. The crash-fix means a failure now **skips gracefully** (`--keep-going`) and
re-running resumes from cache — nothing is lost.

---

## Approved plan — what's left (ship order)

1. **Done** — Step 1 (crash-fix) + Step 2 (inline Opus + concurrency). Committed, tested, verified.
2. **Phase 2 — Gemini Batch API** (`src/batch_asr.py`, new): build JSONL of pending chunk
   requests → submit → poll → write into the same `chunk_NNN.segments.json` caches. 50% cheaper,
   no 503s. Add fakes-only test #8 (`build_jsonl` / `distribute_results`). _Audio via Files API +
   `response_schema` confirmed supported; sub-batch under the tier enqueue limit (Flash Tier-1 = 3M tokens)._
3. **Phase 3 (eval-gated)** — model swap `gemini-2.5-flash` → `gemini-3.5-flash` / `-flash-lite`;
   MM:SS timestamps (Gemini-native); context caching for synth. Each: labeled OFF-vs-ON eval on
   the golden `lsic_2026-03-26`, ship only on no-regression.
4. **Cloud migration** (`AWS_batch.md`, deferred) — single Spot VM + S3; `--pipeline --all
   --keep-going` is the container entrypoint. Future: arbitrary YouTube + podcasts via a source adapter.

---

## Immediate next decisions for the new session

- **Commit/branch the uncommitted work** (multi-video, acquisition) per CLAUDE.md before building more — it's the biggest risk right now.
- Then: **build Phase 2 Batch API** (kills the 503 wall) or **start the cloud VM** (kills the DNS wall). Recommend cloud first since the home network is the dominant blocker.
- Finish the last pilot event (`lsic_2025-10-15`) when the network is stable.

## Operating reminders (from `.claude/CLAUDE.md`)

- Address as **C'mmandr**; facts/data, structured + visual, no code dumps (see `Behavior/Preferences.md`).
- **Branch first → explain before editing → 2–3 options → tests via `/python-unit-tests` → green gate → merge.**
- Non-breaking (degrade-to-today); **eval-first** for any LLM/model change. Pad all tables (§9).
