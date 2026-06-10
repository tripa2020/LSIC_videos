# Cloud Batch — Durable PLAN

_The living source of truth for the first cloud production batch. Kept synced to the code.
Frozen provenance: `CLOUD_BATCH_DESIGN_RATIONALE.md`._

## Intro

- **Goal.** Run the validated LSIC Event→Briefing pipeline in the cloud over the
  **Energy ∪ ISRU** catalog slice, emitting the same per-event `Report/` bundle the
  pipeline already produces locally — **plus `equations.md`** promoted into `Report/`.
- **Inputs.** `download_lsic/selected_manifest.json` (catalog truth incl. `topics`);
  source videos/decks resolved per-event (yt-dlp / curl); `GEMINI_API_KEY` /
  GCP service-account creds.
- **Outputs.** Per event: `Report/{notes.md, slide_captions.md, slides.pdf, equations.md}`,
  synced to a GCS bucket and back to `work/events/<id>/Report/`.
- **Core abstraction.** **Pipeline of per-stage Gemini Batch jobs**, driven through a single
  **`Caller` seam**. Per-event stages stay sequential (transcribe→align→synth→slide_book);
  the work *inside* each LLM stage fans out across all events into one batch submission.
  Stages call `caller.generate(...)` unconditionally — `SyncCaller` (today) or `BatchCaller`
  (buffer→submit→resolve) is injected. `align` is local Python between batches.

The effort is **three parts, in dependency order** — each independently green + deployable:

```
PART 1  Batch code (untested)  ──►  PART 2  Cloud+Docker, 5 full events  ──►  PART 3  Full 122
   fakes-only test gate              5/5 valid full bundle gate              GCS count + spot-check gate
```

---

## Architecture Decisions

| Decision                      | Choice                                                                       | Rationale                                                                                                                                          | Date       |
| ----------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Decomposition                 | 3 sequential parts (code → slice → full)                                     | Part 1 is untested = highest risk; prove on fakes before cloud spend                                                                               | 2026-06-09 |
| Filter                        | `topics ⊇ {Surface Power} ∪ {In Situ Resource Utilization}`                  | Deterministic from catalog; no keyword guessing                                                                                                    | 2026-06-09 |
| Filter source                 | `selected_manifest.json` (181 events)                                        | Reproduces **129 events / 122 with video** exactly (verified by topic_filter, M-C3)                                                                 | 2026-06-09 |
| Cloud target                  | GCP VM + GCS + service account                                               | Gemini co-location: auth, egress, quota; GCP billing ready                                                                                         | 2026-06-09 |
| LLM batch backend             | **Single Gemini Batch API**                                                  | All 4 LLM stages are Gemini; Anthropic is dead code → drop it                                                                                      | 2026-06-09 |
| Batch topology                | Per-stage batch jobs, `align` local between                                  | Stages sequential per event; work fans out within a stage                                                                                          | 2026-06-09 |
| Output contract               | Full `Report/` bundle incl. `equations.md`                                   | "Report + equations"; promote `equations.md` from `05_briefing/`                                                                                   | 2026-06-09 |
| Slice output                  | Full bundle for all 5 picked events                                          | Slice validates the complete product incl. slide render                                                                                            | 2026-06-09 |
| Big-event cap                 | 4 h aggregate video / event (`14400 s`)                                      | Bounds the multi-video Meeting tail; extends `--max-sec`                                                                                           | 2026-06-09 |
| Non-breaking                  | Degrade-to-today on batch / filter / cap                                     | Unset ⇒ byte-identical to today's sync local path                                                                                                  | 2026-06-09 |
| Batch transport coupling (R1) | `batch_gemini` returns `{custom_id: response}`, knows **no** stage cache     | Transport stays general-purpose; cache knowledge stays in the stage that already owns it (kills info-leakage; new stages don't touch transport)    | 2026-06-09 |
| Batch ON/OFF seam (R2)        | **One `Caller` seam** (`SyncCaller`/`BatchCaller`), not 4 per-stage branches | Collapses 4 shallow OFF/ON branches → 1 injected decision; degrade-to-today proven once; new stages get batch free                                 | 2026-06-09 |
| Cap enforcement point (R3)    | **Once at ingest** → bounded manifest (`duration_sec ≤ 14400`)               | Downstream stages read the capped artifact and are auto-bounded; no stage knows the number; removes transcribe-vs-visual silent-disagreement class | 2026-06-09 |
| Batch async failure (R4)      | Failed `custom_id`s left **uncached**                                        | Existing manifest-gate + resume re-enqueues them next run — zero new retry code (error defined out of existence)                                   | 2026-06-09 |
| VM provisioning model         | **STANDARD** (was Spot)                                                       | Spot preempted 3× in one afternoon (`us-central1-a` e2-standard-8 uncontendable); standard ~$0.27/hr (~$2–3 total) removes preemption toil for the multi-hour 122-run | 2026-06-10 |
| Per-stage LLM retry           | **One shared `util.retry_transient`** (companion to `is_transient`)          | `slide_book`'s VLM call was the only LLM stage without retry → dropped slides on Gemini's ~8% image-503; one shared policy closes the gap (synth can adopt it next)    | 2026-06-10 |

### System map

```
selected_manifest.json ──(topic filter: Energy∪ISRU)──► 122 event-id set
        │
        ▼  group_manifest.build(event_ids)                 [seam ALREADY EXISTS]
   work/events.json  (per-event assets, topics in meta, lsic_<date> ids)
        │
        ▼  per event: ingest (audio spine, decks) ── 4h aggregate cap ──┐
        │                                                                │
   ┌────┴─── BATCH(ASR: all chunks, all events) ── align (local) ────────┤
   │                                                                     │
   ├──────── BATCH(VLM: all keyframes) ──┐                               │
   │                                     ▼                               │
   ├──────── BATCH(synth: all sections) ──► notes.md + equations.md      │
   │                                                                     │
   └──────── BATCH(slide_book) ──► slide_captions.md + slides.pdf ───────┘
        │
        ▼  Report/ bundle ──► GCS bucket ──► sync-back to work/events/<id>/Report/
```

### Open Questions

| #   | Question                                                              | Owner     | Resolve-by                       |
| --- | --------------------------------------------------------------------- | --------- | -------------------------------- |
| OQ1 | Gemini key tier — paid? (Batch enqueue limit + quota)                 | Commander | Part 2 M-C2 (verify-first on VM) |
| OQ2 | GCS bucket name + region; VM machine type (default e2-standard-8 CPU) | Commander | Part 2 M-C2                      |
| OQ3 | Total $ ceiling for Part 3 (default: ~$75–100 batch-priced)           | Commander | before Part 3                    |
| ~~OQ4~~ | ✅ RESOLVED — `topic_filter` yields exactly **129 / 122** (matches the original spec; my planning-time 130 was an imprecise ad-hoc grouping). Pinned by `test_real_manifest_locked_counts`. | — | done (M-C3) |

### Deliverable / Output Contract

Per event, `Report/` MUST contain all four, each passing its validator:

| Artifact            | Validator                               | Notes                                             |
| ------------------- | --------------------------------------- | ------------------------------------------------- |
| `notes.md`          | `validate_notes` (`--strict` in Part 3) | 15-section canonical template, grounded `[mm:ss]` |
| `slide_captions.md` | `validate_slides`                       | per-slide captions                                |
| `slides.pdf`        | render present + page count > 0         | from deck renders                                 |
| `equations.md`      | present + non-empty OR skip-stub line   | **promoted from `05_briefing/`**                  |

---

## Repo Layout (new/changed — per-file LOC budgets)

```
LSIC_videos/
├── CLOUD_BATCH_PLAN.md              this file
├── CLOUD_BATCH_DESIGN_RATIONALE.md  frozen provenance
├── src/
│   ├── batch_gemini.py    NEW  ≤120  build_jsonl · submit · poll · resolve → {custom_id: response}  [NO cache knowledge — R1]
│   ├── llm_caller.py      NEW  ≤80   Caller protocol; SyncCaller (today's genai call); BatchCaller (buffer→submit→resolve)  [R2]
│   ├── topic_filter.py    NEW  ≤60   Energy∪ISRU event-id set from selected_manifest
│   ├── transcribe.py      MOD  +≤10  call caller.generate(); mint custom_id + write own cache
│   ├── visual.py          MOD  +≤10  call caller.generate(); mint custom_id + write own cache
│   ├── slide_book.py      MOD  +≤10  call caller.generate(); mint custom_id + write own cache
│   ├── synthesize.py      MOD  +≤10  call caller.generate(); mint custom_id + write own cache
│   ├── ingest.py          MOD  +≤25  emit bounded manifest: 4h aggregate cap on the concat spine  [R3]
│   ├── report.py          MOD  +≤15  promote equations.md into Report/
│   └── main.py            MOD  +≤25  inject SyncCaller/BatchCaller; --topic-batch event selection
├── Dockerfile             NEW  ≤45   base + ffmpeg/libreoffice/yt-dlp + entrypoint
├── .dockerignore          NEW  ≤15   exclude .env, work/, LSIC_Downloads/, .git
├── download_lsic/
│   └── run_corpus.sh      NEW  ≤80   xargs -P over event ids, batch mode, GCS sync, log
├── infra/                 NEW
│   ├── provision_gcp.sh   NEW  ≤80   VM + GCS + service account + run steps
│   └── README.md          NEW       Commander-runs-in-their-project instructions
└── tests/
    ├── test_batch_gemini.py  NEW     build_jsonl / resolve→{id:resp} / failed-id-left-uncached (R4)
    ├── test_llm_caller.py     NEW     SyncCaller==today's call · BatchCaller buffer→resolve (R2)
    ├── test_topic_filter.py  NEW     Energy∪ISRU set == 130/122; determinism
    └── test_cap.py           NEW     bounded-manifest duration ≤ 14400; under-cap no-op (R3)
```

### Fixtures (fakes-only, no network)

| Fixture                                                                        | Feeds               |
| ------------------------------------------------------------------------------ | ------------------- |
| `tests/fixtures/selected_manifest_mini.json` (hand-built, ~8 events w/ topics) | `test_topic_filter` |
| Fake Gemini batch client (in-memory submit/poll returning canned JSONL)        | `test_batch_gemini` |
| Synthetic multi-video event meta (durations summing >4 h)                      | `test_cap`          |

---

## TODO milestones (each names unit testing as a gate)

### PART 1 — Batch processing (code, untested)  `<!-- progress: P1_BATCH -->`

- [x] **M-B1 — `src/batch_gemini.py`** (transport only, R1+R4) — `build_jsonl(requests)`,
  hybrid `submit` (inline ≤100 / JSONL-file above), `poll`/`is_terminal`,
  `resolve(job) -> {custom_id: response}`. **Knows nothing about stage caches.** Failed
  `custom_id`s absent from the map (R4). ✅ 13 fakes-only tests, 100% coverage. `<!-- progress: P1_BATCH (b6cd640) -->`
- [x] **M-B2 — `src/llm_caller.py` (seam ✅) + stage calls ✅** (R2) — `Caller` protocol with
  `generate(...)`; `SyncCaller` wraps today's `genai` call (byte-identical), `BatchCaller`
  buffers fan-out → `batch_gemini.submit` → `resolve`. The four stages call
  `caller.generate(...)` unconditionally and each mints its own `custom_id` + writes its
  own cache (cache knowledge stays in the stage — R1). The ON/OFF decision lives in ONE
  place: which caller `main.py` injects.
  *Gate:* `/python-unit-tests` — `SyncCaller` enqueues the identical call today makes;
  `BatchCaller` buffers→resolves to the same per-stage cache writes.
  *Acceptance:* with `SyncCaller` injected (default), the 11 existing tests pass unchanged.
  **Status: DONE (84ba49a).** `llm_caller.py` (Caller/SyncCaller/BatchCaller/`prefill`) ✅.
  Wired via **batch-prefill**: each heavy stage (`transcribe`/`visual`/`slide_book`) has a
  `batch_prefill_*` that bulk-fills its own per-item cache (R1) through one batch; the
  untouched sync loop then hits cache, so `--batch` absent ⇒ byte-identical (caller=None).
  ASR offset rides in the custom_id; dense chunks defer to the sync split (R4). Synthesis
  stays sync (≈12 interdependent calls/event). `main.py --batch` interleaves prefill before
  each stage. 46 tests green; batch modules 99–100% coverage.
  **Untested-on-purpose (M-C2 live):** the three `batch_prefill_*` orchestrators + the live
  SDK response shape — they need ffmpeg/video/genai; their shared logic (`prefill`,
  `response_text`, transport) is unit-tested. **Also done:** `report.py` promotes
  `equations.md` into `Report/` (4b1520d).

### PART 2 — Cloud + Docker, 5 full events  `<!-- progress: P2_CLOUD_SLICE -->`

- [x] **M-C1 — `Dockerfile` + `.dockerignore`** ✅ — system deps (ffmpeg, libreoffice,
  yt-dlp, PyMuPDF), `pip install -r requirements.txt` (minus dead `anthropic`),
  entrypoint `python -m src.main`. *Gate:* local `docker run … --pipeline --event 618`
  produces a Report bundle; diff `notes.md` vs known-good local (container parity).
- [x] **M-C2 — GCP provisioning** ✅ (scripts; you run on GCP) (`infra/`) — VM + GCS bucket + service account scripts +
  steps. *Gate (verify-first):* on the VM, confirm Gemini key tier (OQ1) + GCS write.
- [x] **M-C3 — `src/topic_filter.py`** ✅ (129/122 pinned) — compute Energy∪ISRU event-id set; feed
  `group_manifest.build(event_ids)`. *Gate:* `/python-unit-tests` — set == 130/122,
  deterministic; log the 130-vs-129 delta (OQ4).
- [x] **M-C4 — 4 h aggregate cap, once at ingest** ✅ (`ingest.py`, R3) — sum video durations
  per event; emit a **bounded manifest** whose concat spine `duration_sec ≤ 14400`. Every
  downstream stage (transcribe, visual, synth, slide_book) reads the bounded manifest and is
  auto-capped — **no stage knows the number**. *Gate:* `/python-unit-tests` — bounded
  manifest duration ≤ 14400; under-cap event unaffected (degrade-to-today).
- [x] **M-C5 — slice run** ✅ — 5 full events → **full Report bundle each** (sync path, not batch).
  **Gate (binary) MET 2026-06-10:** 5/5 bundles pass `validate_notes` + `validate_slides` +
  `equations.md` present, all synced to GCS. Actual events resolved by the `slice` target were
  `lsic_2025-07-16`, `lsic_2025-07-24`, `lsic_2025-09-25`, `lsic_2026-01-29`, `lsic_2026-04-09`
  (the planning-time id list above was illustrative). Run on the **native non-batch path**
  (`run_corpus.sh slice`, sync caller); the `--batch` path is exercised at M-F2.
  **Caveats (see Known Failures):** the corpus driver silently dropped 1 event (completed via
  direct `src.main` invocation); `reportlab` + `PyYAML` were undeclared deps (now pinned).
  Per-event wall-clock ≈ 33 min for a fresh 71-min/4K event (ingest+transcribe dominate).
  <!-- progress: P2_CLOUD_SLICE done (5/5 valid, 2026-06-10) -->

### PART 3 — Full processing  `<!-- progress: P3_FULL -->`

- [x] **M-F1 — `download_lsic/run_corpus.sh`** ✅ (built w/ Part 2) — `xargs -P $CONC` over the 122 video-bearing
  event ids, batch mode, per-event log + ✅/❌ summary, GCS `sync` of bundles, delete-after-
  process for transient video. *Gate:* dry-run on 3 events prints plan + cost estimate.
  ⚠️ **REGRESSION found at M-C5 (2026-06-10):** the loop silently dropped 1 of 5 events (no log,
  never invoked). Must root-cause the `xargs -P` early-exit (suspected 255-exit abort) **before
  M-F2**, or the 122-run will silently under-process. See Known Failures.
- [ ] **M-F2 — full run** — 122 events, 4 h cap applied, `--dry-run` cost gate per event,
  stop on $ ceiling (OQ3). **Gate (binary):** GCS `notes.md` count == expected (≤122);
  spot-check 3 bundles valid; tally spend ≤ ceiling; sync-back populates local `Report/`.

---

## Implementation Outline

### Dependency graph + build order

```
batch_gemini.py (transport) ──► llm_caller.py (Sync/Batch) ──► stages call caller.generate()
                                        │                              (mint custom_id + own cache)
topic_filter.py ────────────────────────┼─► main.py (inject caller, --topic-batch)
ingest.py (bounded manifest, R3) ────────┘
report.py (equations→Report/) ──► Dockerfile + infra/ ──► run_corpus.sh ──► slice run ──► full run
```

| Step | Module                               | Builds on                    | Why now                                                     |
| ---- | ------------------------------------ | ---------------------------- | ----------------------------------------------------------- |
| 1    | `batch_gemini.py` (transport, R1/R4) | google-genai                 | Riskiest (untested); fakes-only first; returns `{id: resp}` |
| 2    | `llm_caller.py` + stage calls (R2)   | batch_gemini, existing seams | One Caller seam; degrade-to-today proven once               |
| 3    | `topic_filter.py`                    | selected_manifest            | Thin wrapper over existing `build(event_ids)`               |
| 4    | `ingest.py` bounded manifest (R3)    | manifest durations           | Bounds Meeting tail at one enforcement point                |
| 5    | `report.py`                          | existing Report assembly     | Promote `equations.md` into `Report/`                       |
| 6    | `Dockerfile` + `infra/`              | all above                    | Container parity → GCP provisioning                         |
| 7    | `run_corpus.sh`                      | container + filter + cap     | Drive the 122                                               |

### Module ownership (new code)

- **`batch_gemini.py`** (transport only — R1) — `build_jsonl(requests) -> str`,
  `submit(jsonl) -> job_id`, `poll(job_id) -> status`, `resolve(job_id) -> dict[custom_id,
  response]`. Audio/images via Files API. **Knows nothing about stage caches**; failed ids
  are absent from the returned map (R4). Pure batch transport.
- **`llm_caller.py`** (the seam — R2) — `Caller` protocol `generate(request) -> response`;
  `SyncCaller` = today's `genai.generate_content` (byte-identical); `BatchCaller` buffers a
  stage's fan-out, calls `batch_gemini.submit`/`resolve`, returns responses keyed by the
  stage's `custom_id`. The OFF/ON decision = which caller `main.py` injects.
- **`topic_filter.py`** — `energy_isru_event_ids(manifest_path) -> set[str]`,
  `with_video(ids) -> set[str]`. Reads `topics`; zero network.
- **Cap (`ingest.py`, R3)** — `_emit_bounded_manifest(event, max_total_sec=14400)`: caps the
  concat spine `duration_sec`; downstream stages read it and are auto-bounded. Logs truncation.

### Non-breaking contract (every new path)

| Path                     | OFF/unset behavior                                                                    |
| ------------------------ | ------------------------------------------------------------------------------------- |
| `Caller` injection       | `SyncCaller` (default) ⇒ today's synchronous Gemini calls, byte-identical             |
| topic filter             | `build(None)` = all selected events (today's behavior)                                |
| 4 h cap                  | events ≤ 4 h ⇒ bounded manifest == today's manifest; cap only truncates longer events |
| `equations.md` promotion | absent `05_briefing/equations.md` ⇒ skip-stub, no crash                               |
| batch failed-id (R4)     | uncached ⇒ existing manifest-gate + resume re-enqueues next run                       |

---

## Testing Strategy

| Layer                       | Catches                                                   | When       |
| --------------------------- | --------------------------------------------------------- | ---------- |
| `test_batch_gemini` (fakes) | JSONL shape, `resolve→{id:resp}`, failed-id-uncached (R4) | M-B1       |
| `test_llm_caller` (fakes)   | SyncCaller==today's call, BatchCaller buffer→resolve (R2) | M-B2       |
| `test_topic_filter`         | filter set == 130/122, determinism                        | M-C3       |
| `test_cap`                  | bounded-manifest ≤ 14400, under-cap no-op (R3)            | M-C4       |
| Existing 11 tests           | no regression with batch OFF                              | every step |
| Container parity diff       | cloud `notes.md` == known-good local                      | M-C1       |
| Slice binary gate           | 5/5 full bundles valid                                    | M-C5       |
| Full-run count + spot-check | 122 bundles, spend ≤ ceiling                              | M-F2       |

---

## Footer

### Known Failures

_Populated from the first cloud debug session (2026-06-10, slice run M-C5)._

| Symptom                                       | Root cause                                                                                                                                                   | Fix                                                                                              | Date       |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- | ---------- |
| `run_corpus.sh` prints `done` but does no work | Script defaults `PY=python`; the native Ubuntu VM has only `python3` + the venv → `python: command not found`, swallowed by the per-event loop (no `set -e`) | Run with `PY=./.venv/bin/python` (now baked into RUNBOOK §D/§H + `vm_setup.sh`)                  | 2026-06-10 |
| VM dies mid-run every ~2 min                   | Spot/preemptible instance reclaimed by GCP (3× in one afternoon); `us-central1-a` e2-standard-8 Spot was uncontendable                                       | Converted to **STANDARD** provisioning — recreate reusing the boot disk; cache + `.env` preserved | 2026-06-10 |
| `slide_book` silently drops ~3 slides/event    | Image/multimodal requests hit a contended Gemini pool returning ~8% transient 503s (text calls clean); `_vlm_curate` was the only LLM call **without retry**, and the stage-resume gate then locks the loss in | Added shared `util.retry_transient` (companion to `is_transient`); wrapped the VLM call (`d648dbe`) | 2026-06-10 |
| `synth` failed all 5 events on the first run   | Transient Gemini **Pro** 503 capacity window; cleared on its own minutes later                                                                              | None needed — synth's existing 5× linear backoff rides it out (verified by re-run)              | 2026-06-10 |
| `slide_book` crashed at stage 6 (`No module named 'reportlab'`) AFTER captioning succeeded | `reportlab` (used by `_render_pdf`) was never in `requirements.txt`; native `pip install -r` missed it | Declared `reportlab>=4.0` in `requirements.txt` (`42b061a`); installed on VM                     | 2026-06-10 |
| `validate_notes` FAILed all 5 (`frontmatter_parses`) even with valid `---` frontmatter | `validators._parse_frontmatter` soft-imports PyYAML; absent PyYAML → `except` returns `None` → false fail. PyYAML was undeclared | Declared `PyYAML>=6.0`; installed on VM (now a hard dep for the validation gate)                 | 2026-06-10 |
| `run_corpus.sh` silently **dropped 1 of 5 events** (no log, never invoked) | Corpus driver loop skipped the last event — suspected `xargs -P` aborting on a 255 exit; not yet root-caused | **OPEN — blocks M-F2.** Worked around via direct `src.main --event`; must fix before the 122-run | 2026-06-10 |

### LLM instructions to reproduce this plan

> After the IDEATION Q&A closed (see `CLOUD_BATCH_DESIGN_RATIONALE.md` §2), derive this
> durable plan: 3-part decomposition (untested batch code → cloud+Docker on 5 named full
> events → full 122 run), single Gemini Batch backend (all stages are Gemini), GCP target,
> full Report bundle incl. promoted `equations.md`, 4 h aggregate video cap, degrade-to-today
> + fakes-only test gates on every addition. Ground every milestone in real files/seams
> (`group_manifest.build(event_ids)`, `--max-sec`, the four `genai` call sites). Keep this
> document live against the code; move Open Questions into Architecture Decisions as resolved.
