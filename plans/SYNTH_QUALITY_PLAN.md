# SYNTH_QUALITY — Durable PLAN

_The living source of truth for the reprioritized quality-first roadmap. Kept synced to the
code. Frozen provenance: `SYNTH_QUALITY_DESIGN_RATIONALE.md`. **Supersedes** `SYNTH_V2_PLAN.md`
(design-only) and owns the unfinished tail of `CLOUD_BATCH_PLAN.md` (the 122-run + 2 bugs).
Status as of 2026-06-25: **planned — awaiting "code it".**_

## Intro

- **Goal.** (1) Prove the full pipeline on a real YouTube lecture and freeze it as an A/B
  reference; (2) make synthesis **measurably** more complete/coherent/deep on long videos
  (eval → sub-fields → chapter map-reduce); (3) run the 122-event cloud batch.
- **Inputs.** The talk `https://www.youtube.com/watch?v=lXUZvyajciY`; existing per-event
  artifacts (`02_transcript`, `04_aligned/evidence.json`, `meta.json` chapters); the active
  `Profile`; `GEMINI_API_KEY` + GCP creds (for `--remote` and BATCH).
- **Outputs.** A frozen baseline bundle under `golden/`; a deterministic **coverage/coherence
  score** artifact; richer `lecture` notes (sub-fields + map-reduce, no truncation); and the
  122 `Report/` bundles in GCS.
- **Core abstraction.** **Map-reduce with single-producer-per-section, owned per Profile**
  (carried from SYNTH_V2). MAP extracts *local* facts per map-unit; REDUCE produces *every
  global section once* over the evidence union. Map-unit is profile-specific: `briefing` maps
  over presentations (today's code, verbatim); `lecture` maps over chapters (new). The same
  `[mm:ss]` grounding measures coherence (cite-spread) and coverage. The default path stays
  **byte-identical**.

```
BASE ──► EVAL ──► DEPTH ──► MAPRED ──► FIX ──► BATCH
freeze    pure      sub-      chapter    2 bugs   122-run
A/B ref   scorer    fields    map-reduce          (briefing)
        (PART 1 — synthesis quality)        (PART 2 — ship)
```

---

## Architecture Decisions

| Decision               | Choice                                                              | Rationale                                                                          | Date       |
| ---------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------- | ---------- |
| Priority order         | BASE → EVAL → DEPTH → MAPRED → FIX → BATCH                          | Quality-first; the YouTube path matters now, the batch is built bar 2 bugs          | 2026-06-25 |
| Baseline run           | `--source --profile lecture --references --remote`, frozen as A/B   | Real "before" anchors the eval; `--remote` offloads heavy ASR/VLM                  | 2026-06-25 |
| Synthesis ownership R1 | `Profile.synthesize(ctx)`; briefing = today's code **verbatim**     | No mode-branch; LSIC byte-identical; map-reduce scoped to `lecture`                 | 2026-06-25 |
| Cognition decomposition | DEPTH v2 = **additive, lecture-scoped dedicated cognition call** (descriptive call unchanged; cognition fields move to a 2nd focused call merged before render) | v1's crowded single call under-resourced the inferential cognition fields; additive keeps briefing byte-identical and the descriptive lecture call unchanged (honors "augment not refactor") | 2026-06-25 |
| Cognition synth model | **`COGNITION_MODEL` knob, default `claude-opus-4-8`** (Opus 4.8) via a scoped `anthropic_caller`; descriptive call stays `gemini-2.5-pro`; the 122 LSIC briefing batch stays single-backend Gemini | The cognition fields are a *reasoning* task (idiosyncratic signature, epistemics, boundary conditions) where a frontier model earns its keep; one bounded call/talk so cost is trivial (~$0.15 batched). Knob enables A/B: `COGNITION_MODEL=gemini-2.5-pro` reproduces an all-Gemini run | 2026-06-25 |
| Anthropic dep re-add | Re-introduce `anthropic` SDK, **scoped to the lecture cognition call only** | CLOUD_BATCH dropped it for batch unification; scoping keeps the Gemini Batch path untouched. `anthropic_caller` imports the SDK lazily (module import is dep-free → fakes-only tests need no install) | 2026-06-25 |
| EVAL purity R2/R3      | Pure deterministic, reads structured reduce JSON, no LLM            | CI-able guardrail decoupled from render; LLM judge deferred (critic pass dropped)  | 2026-06-25 |
| Map-unit R1            | briefing→presentation (today), lecture→chapter                     | Generalize the pattern LSIC already uses; don't replace it                          | 2026-06-25 |
| Segmenter contract R5  | `segment()` always returns ≥1 unit                                 | No-chapters edge defined out of existence; downstream uniform                       | 2026-06-25 |
| SYNTH scope            | EVAL + DEPTH + MAPRED only                                          | Stop before the LLM critic→revise pass (old M-S4); measured map-reduce win is enough | 2026-06-25 |
| 122 independence       | BATCH uses briefing profile → unaffected by PART 1                  | Map-reduce touches only `lecture`; FIX is the only real blocker for the 122         | 2026-06-25 |
| Non-breaking           | Map-reduce flag/threshold-gated; default monolith byte-identical    | Degrade-to-today; 113 tests + `--selftest` golden stay green                        | 2026-06-25 |

### System map

```
 BASE: lXUZvyajciY ──(--source lecture --references --remote)──► golden/<id>_baseline/  [FROZEN A/B "before"]
                                                                        │
 segment(meta.chapters | auto, ALWAYS ≥1)  [NEW, MAPRED]                │ EVAL reads structured JSON
        │  [(start,end,title)]…                                         ▼
        ▼                                                       synth_eval.py (pure):
 MAP: per-chapter EXTRACT ──(cache per chapter)──┐  local facts:        cite-spread · cross-chapter ratio ·
        │                                        │   points · claims    chapter-coverage · groundedness · leak
        ▼                                        │   (+sub-fields,DEPTH) │
 REDUCE: global SYNTH (single-valued schema) ◄───┘   methods · ev[mm:ss] ▼
        │   evidence UNION across chapters             Summary · Lenses · coverage_report.md (score artifact)
        ▼                                              Outlook · Field Impl · Takeaways · tensions
 notes.md (same template, no truncation)  ──► Report/

 PART 2 (independent):  run_corpus.sh [FIX] ──► 122 briefing events ──► GCS  [BATCH]
```

### Open Questions

| #    | Question                                                                          | Owner     | Resolve-by |
| ---- | --------------------------------------------------------------------------------- | --------- | ---------- |
| ~~OQ1~~ | ✅ RESOLVED (2026-06-25) — **no code fix needed.** `--remote` doesn't forward the `--references` flag, but the VM job runs `src.main --source …` which routes to `adhoc.run_adhoc` ([src/adhoc.py:137](../src/adhoc.py)) that **hardcodes `references=True`** for any `--source` run. So the remote BASE bundle gets `references.md` automatically. The real prerequisite is **gcloud install + GCP auth + VM verification** (not configured on this device — VM was provisioned elsewhere). | — | done |
| ~~OQ2~~ | ✅ RESOLVED — `lXUZvyajciY` is the **Karpathy "Digital Ghosts" talk, 146 min, chaptered, 7 speakers** → ideal MAPRED sample (long+chaptered). BASE citations reach `[117:08]`, so the lecture single-call didn't *visibly* truncate late content; EVAL will quantify actual coverage. | — | done |
| OQ3  | Duration threshold for auto map-reduce (e.g. >45 min)?                            | Commander | MAPRED     |
| OQ4  | Cross-chapter-ratio threshold for the CI coherence guardrail                      | data      | EVAL (from BASE baseline) |
| OQ5  | 122-run $ ceiling (CLOUD_BATCH OQ3 default ~$75–100 batch-priced)                 | Commander | BATCH      |

### Deliverable / Output Contract

| Artifact                       | Validator                                   | Notes                                              |
| ------------------------------ | ------------------------------------------- | -------------------------------------------------- |
| `golden/<id>_baseline/notes.md`| `validate_notes` + manual review            | The frozen A/B "before" (BASE)                     |
| `coverage_report.md`           | score JSON present; metrics computed        | chapter_coverage · cross_chapter_ratio · groundedness · leak (EVAL) |
| `lecture` `notes.md` (map-reduce) | `validate_notes`; no truncation; sub-fields present | beats BASE on coherence; `cross_chapter_ratio ≥ OQ4` (MAPRED) |
| 122 × `Report/` bundle         | `validate_notes`/`validate_slides`; GCS count | briefing profile, unchanged output (BATCH)         |

---

## Repo Layout (new/changed — per-file LOC budgets)

```
LSIC_videos/
├── plans/SYNTH_QUALITY_PLAN.md / _DESIGN_RATIONALE.md   this pair
├── golden/
│   └── <id>_baseline/        NEW   frozen A/B "before" bundle (BASE)
├── src/
│   ├── segment.py            NEW ≤80   map-units: meta.chapters | auto → ALWAYS ≥1 (R5)         [MAPRED]
│   ├── synth_mapreduce.py    NEW ≤180  MAP (per-unit extract) → REDUCE (single-producer)        [MAPRED]
│   ├── synth_eval.py         NEW ≤120  PURE deterministic scorer; reads structured JSON (R2/R3) [EVAL]
│   ├── profiles/__init__.py  MOD +≤15  Profile gains deep method `synthesize(ctx)` (R1)         [MAPRED]
│   ├── profiles/briefing.py  NEW +≤20  briefing.synthesize = today's pres+thematic VERBATIM     [MAPRED]
│   ├── profiles/lecture.py   MOD +≤80  lecture.synthesize = chapter map-reduce + sub-fields     [DEPTH/MAPRED]
│   ├── synthesize.py         MOD +≤25  synthesize_full keeps scaffolding → calls prof.synthesize()
│   ├── ingest.py             MOD +≤10  wrap _fetch_youtube/_fetch_http in util.retry_transient  [FIX]
│   ├── main.py               MOD +≤8   only `--quality` deferred; print coverage score
│   └── report.py             MOD +≤6   ship coverage_report.md (optional artifact)
├── download_lsic/run_corpus.sh   MOD   run_one traps failures, logs ❌, exits 0 (no xargs abort) [FIX]
└── tests/
    ├── test_segment.py          NEW    chapters | auto → ≥1; offsets correct
    ├── test_synth_mapreduce.py  NEW    fake LLM map+reduce; single-producer asserted
    ├── test_synth_eval.py       NEW    cite-spread on cites spanning 1 vs ≥2 chapters
    └── test_corpus_driver.py    NEW    driver processes ALL events; a failing event doesn't drop the rest [FIX]
```

### Fixtures (fakes-only, no network)

| Fixture                                                       | Feeds                                   |
| ------------------------------------------------------------- | --------------------------------------- |
| Multi-chapter fake transcript + chapter list                  | `test_segment`, `test_synth_mapreduce`  |
| Fake LLM: canned per-chapter extracts + canned reduce JSON     | `test_synth_mapreduce`                  |
| Canned evidence with chapter offsets (cites spanning 1 vs ≥2) | `test_synth_eval` (cite-spread)         |
| Fake event list where one event's runner exits non-zero        | `test_corpus_driver` (no-drop)          |

---

## TODO milestones (each names unit testing as a gate)

### BASE — Baseline reference (no code change to the pipeline)  `<!-- progress: SQ_BASE -->`

**Prerequisites (this device — see resolved OQ1). Chosen: VM/`--remote`.** No code fix needed —
the VM's `src.main --source` run forces references on via `adhoc.run_adhoc`.
1. Install gcloud: `brew install --cask google-cloud-sdk`
2. Auth (Commander — Google account): `gcloud init` → pick the project that owns `lsic-batch`
3. Verify reachable: `gcloud compute instances describe lsic-batch --zone us-central1-a --format='value(status)'`
   then IAP ssh: `gcloud compute ssh lsic-batch --zone us-central1-a --tunnel-through-iap --command 'echo ok'`

- [x] **BASE — run + freeze** — DONE 2026-06-25. Ran via hardened `--remote` →
  `golden/lXUZvyajciY_baseline/` (notes.md 10.5KB, references.md 3.2KB, equations/slides stubs —
  no deck for a YouTube talk). Bundle complete on manual review; citations span to `[117:08]`.
  **Caveat:** `validate_notes`/`validate_slides` are **briefing-schema-only** and false-fail on a
  `lecture` bundle (they require the 15 LSIC sections). Lecture validation falls to EVAL
  (profile-agnostic) + manual review. **TODO:** `git`-commit `golden/lXUZvyajciY_baseline/` to
  freeze the A/B "before".

### PART 1 — Synthesis quality

- [ ] **EVAL — `src/synth_eval.py`** (was M-S0; built FIRST; R2/R3) — pure, no-LLM, reads the
  structured reduce JSON + evidence: cite-spread · cross-chapter ratio · chapter-coverage ·
  groundedness · chapter-index-leak regex. Profile-agnostic (scores LSIC unchanged). Run it on
  the BASE output to record a baseline + set OQ4.
  *Gate:* `/python-unit-tests` — metrics deterministic on fixtures (cites spanning 1 vs ≥2 chapters); baseline JSON emitted.

- [~] **DEPTH v1 — Cognition Layer (SHIPPED on `alex/cognition-layer`)** — the lecture profile now
  extracts HOW the speaker thinks: `operating_algorithm`, `cognitive_moves` (tagged by operation),
  inline epistemic `status` + `what_doesnt_transfer` (survivorship guard), `transfer_questions`
  (env `READER_DOMAIN`). Additive, speaker-agnostic, degrade-to-today; 119 tests green; `--selftest`
  OK. **Supersedes** the original `mastery_signal/engineering_gap/math_framework` idea (subsumed by
  `cognitive_moves`). Spec: `golden/golden_additions.md`. **A/B vs BASE by eye (2026-06-25):**
  Cognitive Moves strong; Operating Algorithm generic (talk-outline failure); epistemic/transfer
  thin → drives v2.

- [ ] **DEPTH v2 — Cognition refinement (dedicated call + 4 fixes)** — *root cause of v1 weakness:*
  the 4 inferential cognition fields share ONE crowded call with ~13 descriptive fields (last in the
  schema → least attention) and the prompt is example-free. Fixes:
  1. **Dedicated cognition call (additive, lecture-scoped) + model knob** — the cognition fields
     (operating_algorithm, cognitive_moves, notable_claims+status, what_doesnt_transfer,
     transfer_questions) leave the descriptive `_call_thematic` and move to a **2nd focused call**
     (`_call_cognition`) reusing the same event context, merged into `thematic` before render.
     Routed by **`COGNITION_MODEL` (default `claude-opus-4-8`)**: `claude-*` → scoped
     `src/anthropic_caller.py` (adaptive thinking + high effort); `gemini-*` → the existing
     `_call_gemini_json` (for A/B). Briefing has no cognition call → byte-identical. Degrades to
     omitting the cognition sections if the call fails (no key / error).
  2. **Sharpen Operating Algorithm** — instruct the *idiosyncratic, transferable reasoning signature*
     vs a *talk outline* (explicit negative guidance) to kill the generic-outline failure mode.
  3. **Survivorship `when_it_fails`** (section C) — per bet/move, the boundary condition where the
     play backfires + who has run it and lost, from the model's OWN knowledge. **No parallel system.**
  4. **Robust Transfer** — (a) a richer `current_work` context input (project-level, beyond the bare
     `READER_DOMAIN` string); (b) one question per major cognitive move, each tied to its named move
     + `[mm:ss]`.
  - **Verbosity standard:** the **Cognitive Moves** level is the target for ALL cognition sections.
  *Gate:* `/python-unit-tests` (fakes — dedicated-call seam, `when_it_fails` render, transfer
  grounding; briefing byte-identical) **+** A/B the regenerated lecture vs DEPTH-v1 by eye against the
  gold (EVAL scores groundedness but not "idiosyncrasy" — that stays a human/critic check).

- [ ] **MAPRED — profile-owned synthesis + lecture map-reduce** (was M-S2; R1/R5) — introduce
  `Profile.synthesize(ctx)`. **First** move `briefing.synthesize` = today's per-presentation +
  thematic code **VERBATIM** (proves LSIC byte-identical, no mode-branch). Then
  `lecture.synthesize` = `segment.py` (R5) + `synth_mapreduce.py`: MAP extracts local facts per
  chapter (cached); REDUCE synthesizes every global section once over the evidence union
  (single-valued schema + `tensions`). `synthesize_full` keeps shared scaffolding and calls
  `prof.synthesize()`. Auto-select map-reduce by internal duration constant (OQ3).
  *Gate:* `/python-unit-tests` — **briefing output unchanged** (`--selftest` + synth tests green);
  fake LLM map+reduce with single-producer asserted (chapters emit NO summary/lens/outlook) **+**
  on the BASE video (or a 2nd long sample, OQ2): no truncation, `cross_chapter_ratio ≥ OQ4`,
  coherence ≥ BASE on the A/B.

### PART 2 — Ship at scale (CLOUD_BATCH tail; independent of PART 1)

- [ ] **FIX — corpus driver + ingest retry** — (a) `run_corpus.sh`: make `run_one` trap failures,
  log `❌ <event>`, and `exit 0` so `xargs -P` never sees a 255 and never aborts the batch; tally
  failures at the end. (b) `ingest.py`: wrap `_fetch_youtube`/`_fetch_http` in `util.retry_transient`
  (exists, [src/util.py:174]).
  *Gate:* `/python-unit-tests` — `test_corpus_driver`: a failing event does NOT drop the rest;
  ingest retries a transient non-zero exit then succeeds.

- [ ] **BATCH — the 122-event run** (was CLOUD_BATCH M-F2) — `run_corpus.sh filter` over the
  122 video-bearing events, 4h cap applied, `--dry-run` cost gate per event, stop on $ ceiling
  (OQ5). *Gate (binary):* GCS `notes.md` count == expected (≤122); spot-check 3 bundles valid;
  spend ≤ ceiling; sync-back populates local `Report/`.

---

## Implementation Outline

### Dependency graph + build order

```
BASE (freeze ref) ──► EVAL (scorer; baseline from BASE) ──► MAPRED (must beat BASE on EVAL)
                          └─ DEPTH (independent; on today's monolith; carried into map schema)
FIX (driver + ingest retry) ──► BATCH (122-run)      [PART 2: parallel-able once FIX lands]
```
Build order **BASE → EVAL → DEPTH → MAPRED → FIX → BATCH**. Each: own branch
`alex/<short-desc>`, degrade-to-today (default monolith = byte-identical), fakes-only tests
green, **eval lift measured over the BASE reference** before merging any LLM-behavior change,
merged only when green + verified.

### Module ownership (new code)

- **`synth_eval.py`** (EVAL) — pure deterministic metrics over the structured reduce JSON +
  evidence. **Knows nothing about render/markdown** (R2); no LLM (R3). Profile-agnostic.
- **`segment.py`** (MAPRED) — `segment(meta) -> list[(start,end,title)]`, **always ≥1** (R5);
  uses `meta.chapters` if present, else one whole-video unit (auto-segment later).
- **`synth_mapreduce.py`** (MAPRED) — `map_extract(unit, ctx)` per chapter (cached) →
  `reduce_synth(extracts, evidence_union)` producing every global section **once**
  (single-producer). Chapters emit local facts only — never summaries/lenses.
- **`profiles/briefing.py`** (MAPRED) — `synthesize(ctx)` wrapping today's `_call_presentation`
  + `_call_thematic` **verbatim**; the byte-identical proof for LSIC.

### Non-breaking contract (every new path)

| Path                     | OFF/unset behavior                                                              |
| ------------------------ | ------------------------------------------------------------------------------- |
| `Profile.synthesize`     | `briefing` = today's pres+thematic code verbatim ⇒ identical `notes.md`         |
| map-reduce (lecture)     | below the duration constant ⇒ today's single-call lecture path                  |
| sub-fields (DEPTH)       | absent in model output ⇒ render omits them, no crash                            |
| `synth_eval` / score     | read-only; never mutates the briefing; absent ⇒ no score file, pipeline runs    |
| ingest retry (FIX)       | success on first try ⇒ identical to today (retry only on transient non-zero)    |
| corpus driver (FIX)      | all-success run ⇒ identical behavior; only changes the *failure* path (no drop) |

---

## Testing Strategy

| Layer                         | Catches                                                      | When     |
| ----------------------------- | ------------------------------------------------------------ | -------- |
| `test_synth_eval` (fakes)     | metric correctness; cite-spread on 1- vs ≥2-chapter cites    | EVAL     |
| lecture render test           | sub-fields rendered; degrade when absent; briefing untouched | DEPTH    |
| `test_segment` / `test_synth_mapreduce` | ≥1 unit; single-producer (no summary from chapters) | MAPRED   |
| `--selftest` golden + synth tests | briefing byte-identical (no regression)                  | MAPRED   |
| A/B vs BASE on `synth_eval`   | map-reduce ≥ monolith coherence; no truncation               | MAPRED   |
| `test_corpus_driver` (fakes)  | a failing event doesn't drop the rest; ingest retry          | FIX      |
| Existing 113 tests            | no regression with all new paths OFF                         | every step |
| Full-run count + spot-check   | 122 bundles, spend ≤ ceiling                                 | BATCH    |

---

## Footer

### Known Failures

_Inherited from CLOUD_BATCH / EASYRUN; resolved within this plan's FIX milestone._

| Symptom                                              | Root cause                                                                                  | Fix (this plan)                                                    | Status |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- | ------ |
| `run_corpus.sh` silently dropped 1 of 5 events       | `run_one` lets a non-zero exit propagate; `xargs -P` aborts the whole batch on a 255 exit   | FIX: trap in `run_one`, log ❌, `exit 0`, tally at end             | OPEN   |
| Ingest died on a transient yt-dlp 503/throttle       | `_fetch_youtube`/`_fetch_http` have no whole-command retry ([src/ingest.py:151-176])        | FIX: wrap both in `util.retry_transient` ([src/util.py:174])      | OPEN   |
| Long-video synthesis truncated / "lost in the middle" | thematic call caps context at 140k chars ([src/synthesize.py:553])                          | MAPRED: chapter map-reduce removes the single-call ceiling         | OPEN   |
| `validate_notes`/`validate_slides` false-fail on a `lecture` bundle | both encode the 15-section LSIC **briefing** template only | EVAL (profile-agnostic, reads structured JSON) is the lecture scorer; a profile-aware validator is a later option | KNOWN  |
| `references.md` off-target on metaphorical claims    | `derive_queries` keyword-matched "building animals/ghosts" → smart-buildings energy papers   | EASYRUN M3.1 residual; LLM query-gen is the upgrade (out of scope here) | KNOWN  |

### Out of scope (deferred / parallel tracks)

- **Critic→revise quality pass + `--quality`** (old SYNTH_V2 M-S4) — deferred; build after MAPRED proves a measured lift.
- **EASYRUN N1** — agentic claim-verification of predictions. Separate effort.
- **Semantic Scholar / general-web search** behind the `SearchClient` seam (EASYRUN OQ1).

### LLM instructions to reproduce this plan

> After the IDEATION Q&A closed (see `SYNTH_QUALITY_DESIGN_RATIONALE.md` §2), derive this durable
> plan: BASE (run `lXUZvyajciY` via `--source --profile lecture --references --remote`, freeze as
> golden A/B reference) → PART 1 synthesis quality {EVAL = pure deterministic coverage/coherence
> scorer reading structured JSON; DEPTH = lecture sub-fields on today's monolith; MAPRED =
> Profile-owned synthesize, briefing verbatim, lecture chapter map-reduce, single-producer,
> kills the 140k truncation} → PART 2 {FIX = run_corpus.sh no-drop + ingest retry; BATCH = the
> 122-run}. Cannibalize SYNTH_V2 (superseded) + the CLOUD_BATCH tail. Descriptive milestone
> names (BASE/EVAL/DEPTH/MAPRED/FIX/BATCH). Degrade-to-today + fakes-only gates; map-reduce ships
> only on measured lift over BASE. Keep this doc synced to code; move Open Questions into
> Architecture Decisions as resolved.
