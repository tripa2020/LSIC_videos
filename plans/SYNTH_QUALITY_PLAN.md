# SYNTH_QUALITY — Durable PLAN

> 🟢 **ACTIVE PLAN — this is the plan currently being worked on (as of 2026-07-03).**
> **Build order (re-prioritized 2026-07-03):** **DEPTH v3 → EVAL → FIX → RUNEASY** (then BATCH).
> BASE + DEPTH v1/v2 + MAPRED shipped (MAPRED verified 2026-06-27 on `alex/mapred-windows`;
> merge to main pending). **DEPTH v3 — the cognitive core taken to the real world — is the
> immediate build target:** full-context two-pass cognition, Founder Lens, How-to-Learn-It.

_The living source of truth for the reprioritized quality-first roadmap. Kept synced to the
code. Frozen provenance: `SYNTH_QUALITY_DESIGN_RATIONALE.md`. **Supersedes** `archived/SYNTH_V2_PLAN.md`
(design-only) and owns the unfinished tail of `archived/CLOUD_BATCH_PLAN.md` (the 122-run + 2 bugs).
Status as of 2026-07-03: **in progress — BASE + DEPTH v1/v2 + MAPRED shipped; DEPTH v3 → EVAL → FIX → RUNEASY next.**_

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
  over presentations (today's code, verbatim); `lecture` maps over **size/token-bounded windows** (new — sized to the context budget, *not* author chapters). The same
  `[mm:ss]` grounding measures coherence (cite-spread) and coverage. The default path stays
  **byte-identical**.

```
[✓BASE] [✓DEPTH v1/v2] [✓MAPRED] ──► DEPTH v3 ──► EVAL ──► FIX ──► RUNEASY ──► BATCH
 freeze  cognition       windowed     cognitive     pure     2 bugs  list/PL →   122-run
 A/B ref layer           map-reduce   core v3       scorer           --remote    (briefing)
              (re-prioritized 2026-07-03 — founder-grade cognitive core first)
```

---

## Architecture Decisions

| Decision               | Choice                                                              | Rationale                                                                          | Date       |
| ---------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------- | ---------- |
| Priority order (rev)   | MAPRED → FIX → EVAL → RUNEASY → BATCH (BASE + DEPTH v1/v2 done)      | Re-prioritized 2026-06-26: land the long-video synthesis win, harden the driver, measure, then make multi-video runs one-command | 2026-06-26 |
| Baseline run           | `--source --profile lecture --references --remote`, frozen as A/B   | Real "before" anchors the eval; `--remote` offloads heavy ASR/VLM                  | 2026-06-25 |
| Synthesis ownership R1 | `Profile.synthesize(ctx)`; briefing = today's code **verbatim**     | No mode-branch; LSIC byte-identical; map-reduce scoped to `lecture`                 | 2026-06-25 |
| Cognition decomposition | DEPTH v2 = **additive, lecture-scoped dedicated cognition call** (descriptive call unchanged; cognition fields move to a 2nd focused call merged before render) | v1's crowded single call under-resourced the inferential cognition fields; additive keeps briefing byte-identical and the descriptive lecture call unchanged (honors "augment not refactor") | 2026-06-25 |
| Cognition synth model | **`COGNITION_MODEL` knob, default `claude-opus-4-8`** (Opus 4.8) via a scoped `anthropic_caller`; descriptive call stays `gemini-2.5-pro`; the 122 LSIC briefing batch stays single-backend Gemini | The cognition fields are a *reasoning* task (idiosyncratic signature, epistemics, boundary conditions) where a frontier model earns its keep; one bounded call/talk so cost is trivial (~$0.15 batched). Knob enables A/B: `COGNITION_MODEL=gemini-2.5-pro` reproduces an all-Gemini run | 2026-06-25 |
| Anthropic dep re-add | Re-introduce `anthropic` SDK, **scoped to the lecture cognition call only** | CLOUD_BATCH dropped it for batch unification; scoping keeps the Gemini Batch path untouched. `anthropic_caller` imports the SDK lazily (module import is dep-free → fakes-only tests need no install) | 2026-06-25 |
| EVAL purity R2/R3      | Pure deterministic, reads structured reduce JSON, no LLM            | CI-able guardrail decoupled from render; LLM judge deferred (critic pass dropped)  | 2026-06-25 |
| Map-unit (rev)         | briefing→presentation (today); lecture→**size/token window** (NOT author chapters) | Map-reduce targets the *context-size* constraint (140k truncation / lost-in-middle), which scales with video length — not where the uploader drew chapter marks. Uniform windowing also kills the no-chapter edge | 2026-06-26 |
| Segmenter contract R5  | `segment()` always returns ≥1 unit                                 | No-chapters edge defined out of existence; downstream uniform                       | 2026-06-25 |
| SYNTH scope            | EVAL + DEPTH + MAPRED only                                          | Stop before the LLM critic→revise pass (old M-S4); measured map-reduce win is enough | 2026-06-25 |
| 122 independence       | BATCH uses briefing profile → unaffected by PART 1                  | Map-reduce touches only `lecture`; FIX is the only real blocker for the 122         | 2026-06-25 |
| Non-breaking           | Map-reduce flag/threshold-gated; default monolith byte-identical    | Degrade-to-today; 113 tests + `--selftest` golden stay green                        | 2026-06-25 |
| Priority order (rev 2) | DEPTH v3 → EVAL → FIX → RUNEASY → BATCH (MAPRED verified 2026-06-27) | Alex 2026-07-01: the cognitive core is where the pipeline's utility concentrates — "this is where this should focus for now" | 2026-07-03 |
| Cognition context (v3) | Cognition path drops the 140k-char cap — the FULL transcript goes into one call (146 min ≈ 45k tok; Fable's 1M-token window ≈ 20× headroom; the 4h ingest cap bounds the worst case ≤ ~90k tok). No cognition windowing. | Hard data: no cognitive move in v2_opus OR v3 cites past [83:33] of the 146-min talk — the self-imposed cap physically hid the last hour (incl. the [138:55] educator material Alex flagged). MAPRED-style windowing is unnecessary at these sizes and costs more | 2026-07-03 |
| Cognition model (v3)   | `COGNITION_MODEL` default → **`claude-fable-5`** ($10/$50 per Mtok); thinking always-on (omit the param); refusal → server-side fallback `claude-opus-4-8` (doubles as the A/B knob) | Cognition is the highest-reasoning task in the pipeline; Alex accepted ~2× Opus cost for the cognitive core; the fallback keeps runs alive on classifier false-positives | 2026-07-03 |
| Two-pass cognition R6  | **Pass 1 EXTRACT** (speaker-facing: algorithm · ≥10 moves · epistemics) → **Pass 2 CONVERT** (reader-facing: Founder Lens + How-to-Learn-It; input = transcript + Pass 1 moves). **No split knob** — the `v2_opus`/`v3_mapreduce` goldens ARE the single-call A/B baseline; reversibility is git | DEPTH v1's measured failure mode: crowded calls under-resource tail fields; extraction (describe the speaker) and conversion (prescribe for the reader) are different cognitive jobs. ~$1.20–1.50/talk vs $0.70 — Alex chose depth over cost | 2026-07-03 |
| Founder Lens section   | NEW top-level section, **3-5 entries synthesized ACROSS the talk** (NOT 1:1 per move): idea(from_moves + [mm:ss]) → `wedge` (ONE sentence passing the rubric: segment + urgent pain + why-now + access) → `action` (Monday morning) → `learn` (gap to close) → `deeper` (1-2 named) | Alex's reader persona: robotics entrepreneur/CEO taking ideas to the real world. 1:1 per-move mapping would force filler wedges; the rubric (NFX/Every wedge literature) blocks hand-wavy "robotics is big" output | 2026-07-03 |
| How-to-Learn-It section | NEW top-level section: 5-8 retrieval Q/A prompts (Matuschak rules: effortful recall, no yes/no, no enumerations) + first-order terms + ONE minimal buildable artifact (micrograd-style) | "Educator every time" as concrete artifacts, not advice — retrieval practice is the evidence-backed mechanism for retention; Q/A pairs are Anki/Mochi-importable later | 2026-07-03 |
| Moves contract (v3)    | **≥10 moves × 2-3 substantive sentences**; per move: verbatim quote · tag · work · fails_when · self_question; tag set = full 15-tag taxonomy **+ ACTA probes** (anomaly-noticing, workarounds/job-smarts, improvising, self-monitoring); quote-FIRST-then-analyze ordering; 2-3 few-shot exemplars | Alex: v3 moves "not robust/verbose enough" — the old prompt itself CAPPED output ("4-7 entries", "one substantive sentence, no padding", 8 tags, no exemplars). ACTA adds the practitioner-craft dimensions; verbatim quotes make EVAL's hallucination check deterministic | 2026-07-03 |
| Reader-context parity  | `READER_DOMAIN` + `CURRENT_WORK` (founder-persona wording) baked into `.env` and topped-up to the VM `.env` by `remote.py` (same grep-append as the ANTHROPIC key); no-domain degrade → GENERIC self-questions, never an empty section | v3's Transfer Questions vanished because the VM never saw the env vars and the prompt ordered an empty list on no-domain — an env-parity bug class, killed at the root | 2026-07-03 |
| Cognition failure semantics | Required fields (algorithm · moves≥10 · founder_lens · learn_it) get ONE plain re-issue retry (identical call, no repair prompt), then degrade with a **visible `cognition_status`** in the bundle + JSON. Cost = **ACTUAL API usage→$** (pricing table lives ONLY in `anthropic_caller`), printed per pass; **no ceiling in v1** — observe the completed system's real cost, then set `COGNITION_COST_CEILING` (OQ9 revised); a fixed input-size sanity guard covers the pathological case | Today ANY cognition failure silently drops the whole layer — that is exactly how the vanished section went unnoticed. Alex 2026-07-03: "see the cost after running the completed system before setting a ceiling"; a pre-call chars/4 estimator would duplicate drift-prone pricing knowledge (complexity review) | 2026-07-03 |
| Complexity review (RUNEASY) | CR1 **one loop everywhere** (the VM batch = `--source-list --local` on the VM; resume-skip in the loop ONLY) · CR2 `BATCH_DONE`/`PROGRESS` sentinel files + shared `_launch_and_poll` (no duplicated poll machinery) · CR3 stateless poller, deadline scales with list length (no cross-poll stall state machine) · CR4 `_parse_links` function in adhoc.py, no links module | `/complexity_reviewer` 2026-07-05 — all four approved by Alex; removes both 🔴 modules (a second VM runner + a stateful poller) before any code exists | 2026-07-05 |
| Complexity review (v3) | Reductions applied 2026-07-03 (all utility-neutral — default two-pass output unchanged): (1) no `COGNITION_SPLIT` knob (goldens = A/B baseline, no third prompt variant); (2) actual-usage cost accounting, ceiling between passes; (3) single downstream contract — `founder_lens`/`learn_it` are optional fields ON `CognitionOutput` v3; (4) `remote.py` top-up generalized to a key-list loop; (5) plain re-issue retry, no repair prompt | `/complexity_reviewer` on the v3 spec: the split knob's OFF path and the pre-call estimator were the two 🔴 modules (permanent prompt-maintenance surface; shallow drift-prone heuristic) | 2026-07-03 |

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
| ~~OQ3~~ | ✅ RESOLVED 2026-06-26 — no duration threshold; auto map-reduce iff size-windowing yields **≥2 windows** (evidence text > `WINDOW_BUDGET`). | — | done |
| OQ4  | Cross-chapter-ratio threshold for the CI coherence guardrail                      | data      | EVAL (from BASE baseline) |
| OQ5  | 122-run $ ceiling (CLOUD_BATCH OQ3 default ~$75–100 batch-priced)                 | Commander | BATCH      |
| ~~OQ6~~ | ✅ RESOLVED 2026-07-05 (Alex) — **one VM run looping the list on the VM**. Decision metrics: VM overhead/video · tunnel-flake surface · isolation vs idempotent-stage resume · single-VM parallelism ceiling · ops complexity | — | done |
| ~~OQ7~~ | ✅ RESOLVED 2026-07-04 (Alex) — one output folder per batch; **each video gets its own subfolder** (`<out>/<video_id>/` with notes.md, coverage_report.md, …) | — | done |
| OQ8  | MAPRED: `WINDOW_BUDGET` default (per-window char/token budget) — tune via A/B vs golden | data      | MAPRED     |
| ~~OQ9~~ | ✅ RESOLVED 2026-07-03 (revised) — **no ceiling in v1**; observe then set. **Observed 2026-07-04:** clean run ≈ $3.03/talk; worst case $9.83 via truncation retry storm (now failfast-guarded). Suggested ceiling when enforcement lands: ~$5/talk | Commander | done (data in) |
| OQ10 | Are ALL 5 per-move fields hard-required for a move to count (quote·tag·work·fails_when·self_question)? Defaulted to all-required — veto if too rigid | Commander | DEPTH v3   |
| ~~OQ11~~ | ✅ RESOLVED 2026-07-03 — founder-persona wording **blessed as drafted** and written to the gitignored `.env`: READER_DOMAIN = robotics-entrepreneur/CEO lens; CURRENT_WORK = venture-wedge scouting + Tripp arm + LSIC pipeline | — | done |

### Deliverable / Output Contract

| Artifact                       | Validator                                   | Notes                                              |
| ------------------------------ | ------------------------------------------- | -------------------------------------------------- |
| `golden/<id>_baseline/notes.md`| `validate_notes` + manual review            | The frozen A/B "before" (BASE)                     |
| `coverage_report.md`           | score JSON present; metrics computed        | chapter_coverage · cross_chapter_ratio · groundedness · leak (EVAL) |
| `lecture` `notes.md` (map-reduce) | `validate_notes`; no truncation; sub-fields present | beats BASE on coherence; `cross_chapter_ratio ≥ OQ4` (MAPRED) |
| 122 × `Report/` bundle         | `validate_notes`/`validate_slides`; GCS count | briefing profile, unchanged output (BATCH)         |
| `lecture` cognition v3 bundle  | EVAL v3: moves ≥10 · ≥2 cite final third · quotes verbatim-match transcript · Founder Lens + Learn-It present · `cognition_status` clean | `golden/lXUZvyajciY_v4_depth3/` A/B vs `v2_opus` + `v3_mapreduce` (DEPTH v3) |

---

## Repo Layout (new/changed — per-file LOC budgets)

```
LSIC_videos/
├── plans/SYNTH_QUALITY_PLAN.md / _DESIGN_RATIONALE.md   this pair
├── golden/
│   └── <id>_baseline/        NEW   frozen A/B "before" bundle (BASE)
├── src/
│   ├── segment.py            NEW ≤80   map-units: SIZE/token windows over evidence → ALWAYS ≥1 (R5) [MAPRED]
│   ├── synth_mapreduce.py    NEW ≤180  MAP (per-unit extract) → REDUCE (single-producer)        [MAPRED]
│   ├── synth_eval.py         NEW ≤120  PURE deterministic scorer; reads structured JSON (R2/R3) [EVAL]
│   ├── profiles/__init__.py  MOD +≤15  Profile gains deep method `synthesize(ctx)` (R1)         [MAPRED]
│   ├── profiles/briefing.py  NEW +≤20  briefing.synthesize = today's pres+thematic VERBATIM     [MAPRED]
│   ├── profiles/lecture.py   MOD +≤80  lecture.synthesize = chapter map-reduce + sub-fields     [DEPTH/MAPRED]
│   ├── synthesize.py         MOD +≤25  synthesize_full keeps scaffolding → calls prof.synthesize()
│   ├── profiles/lecture.py   MOD +≤120 v3: EXTRACT prompt (≥10 moves, 15-tag+ACTA, quote-first, exemplars) + CONVERT prompt (Founder Lens, Learn-It) + 2 new render sections [DEPTH v3]
│   ├── anthropic_caller.py   MOD +≤40  fable-5 routing (thinking omitted, server-side fallback→opus-4-8); usage→$ accounting (the ONLY pricing table) [DEPTH v3]
│   ├── synthesize.py         MOD +≤40  cognition context uncapped; two-pass orchestration; between-pass ceiling; retry-then-cognition_status [DEPTH v3]
│   ├── remote.py             MOD +≤15  key top-up generalized to a list loop (ANTHROPIC + READER_DOMAIN + CURRENT_WORK) [DEPTH v3]
│   ├── contracts.py          MOD +≤60  CognitionOutput v3: 5-field moves + optional founder_lens/learn_it + cognition_status (ONE downstream contract) [DEPTH v3]
│   ├── ingest.py             MOD +≤10  wrap _fetch_youtube/_fetch_http in util.retry_transient  [FIX]
│   ├── main.py               MOD +≤8   only `--quality` deferred; print coverage score
│   └── report.py             MOD +≤6   ship coverage_report.md (optional artifact)
├── download_lsic/run_corpus.sh   MOD   run_one traps failures, logs ❌, exits 0 (no xargs abort) [FIX]
└── tests/
    ├── test_cognition_v3.py     NEW    fakes: two-pass merge · retry-then-status · per-pass cost reporting · key-list top-up · no-domain → generic questions [DEPTH v3]
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

- [x] **EVAL — `src/synth_eval.py`** (BUILT 2026-07-04; R2/R3) — pure, no-LLM, deterministic.
  Two modes: `score_notes` (notes.md alone — scores every golden, old or new) and `score_full`
  (+ `thematic.json`/`evidence.json`: verbatim quote verification, evidence resolution,
  **cross-window ratio** = OQ4's metric). Encodes the v3 gates (moves ≥10 · ≥2 final-third ·
  Founder Lens 3-5 · Learn-It ≥5 Qs + artifact · status clean). Hooks: `synthesize._run_eval`
  (read-only, failure-swallowed) writes `coverage_report.{md,json}` per run; `report.py` ships
  it; CLI `python -m src.synth_eval <bundles…>` for retro-scoring.
  **Retro-scores: `golden/EVAL_SCORES.md`** — v4_depth3 is the only 5/5-gate generation; the
  DEPTH v3 lift is now measured, and the table is the regression floor for all future changes.
  *Gate:* 175 tests + `--selftest` green (metrics deterministic on fixtures incl. 1-vs-≥2-window
  cites, normalized quote match, read-only + never-blocks contracts). **OQ4 residual:** the
  cross-window threshold gets its number after a few in-pipeline `score_full` runs accumulate.

- [~] **DEPTH v1 — Cognition Layer (SHIPPED on `alex/cognition-layer`)** — the lecture profile now
  extracts HOW the speaker thinks: `operating_algorithm`, `cognitive_moves` (tagged by operation),
  inline epistemic `status` + `what_doesnt_transfer` (survivorship guard), `transfer_questions`
  (env `READER_DOMAIN`). Additive, speaker-agnostic, degrade-to-today; 119 tests green; `--selftest`
  OK. **Supersedes** the original `mastery_signal/engineering_gap/math_framework` idea (subsumed by
  `cognitive_moves`). Spec: `golden/golden_additions.md`. **A/B vs BASE by eye (2026-06-25):**
  Cognitive Moves strong; Operating Algorithm generic (talk-outline failure); epistemic/transfer
  thin → drives v2.

- [x] **DEPTH v2 — Cognition refinement (dedicated call + 4 fixes) — SHIPPED 2026-06-25**
  (commits `9c2537f` / `0e1cf2f` / `23a71c7`: `src/anthropic_caller.py`, `_call_cognition` +
  `COGNITION_MODEL=claude-opus-4-8`, `when_it_fails` + per-move `transfer_questions` + `CURRENT_WORK`;
  A/B bundles `golden/lXUZvyajciY_v2_{gemini,opus}/`; `tests/test_cognition.py`). *Root cause of v1 weakness:*
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

- [x] **DEPTH v3 — the cognitive core, taken to the real world** (VERIFIED + CLOSED 2026-07-04;
  R6 two-pass) — make the cognition layer founder-grade: full-context, two-pass,
  three sections. Root causes it kills (diagnosed 2026-07-02 from the `v3_mapreduce` A/B): the
  140k context cap hid the last hour of the talk (no move cites past `[83:33]` of 146 min); the
  VM never saw `READER_DOMAIN` (Transfer Questions silently vanished); the prompt itself capped
  moves at 4-7 × 1 sentence; the educator lens appeared by luck (1 of 5 bundles).
  1. **Full context.** The cognition path drops the 140k cap in `_build_event_context` — the
     whole transcript goes into ONE call (146 min ≈ 45k tok; Fable's 1M-token window ≈ 20×
     headroom; the 4h ingest cap bounds the worst case ≤ ~90k tok). The descriptive path keeps
     MAPRED windowing untouched.
  2. **Two-pass (no knob — this IS the design).**
     **Pass 1 EXTRACT** (speaker-facing): `operating_algorithm` + **≥10 `cognitive_moves`** —
     per move: verbatim quote · tag · 2-3 sentence `work` · `fails_when` · `self_question`;
     full 15-tag taxonomy **+ ACTA probes** (anomaly-noticing, workarounds/job-smarts,
     improvising, self-monitoring); quote-FIRST-then-analyze ordering; 2-3 few-shot exemplars
     (the Bezos/Musk/Feynman surface-vs-extraction conversions) — + `claim_epistemics` +
     `what_doesnt_transfer`.
     **Pass 2 CONVERT** (reader-facing; input = transcript + Pass 1 moves): **Founder Lens —
     To Market** (3-5 entries synthesized ACROSS the talk, NOT 1:1 per move: idea(from_moves +
     `[mm:ss]`) → `wedge` — ONE sentence passing the rubric segment + urgent pain + why-now +
     access → `action` (Monday morning) → `learn` (gap to close) → `deeper` (1-2 named)) and
     **How to Learn It (So It Sticks)** (5-8 retrieval Q/A prompts per Matuschak's rules —
     effortful recall, no yes/no, no enumerations — + first-order terms + ONE minimal buildable
     artifact, micrograd-style). No split knob: the `v2_opus`/`v3_mapreduce` goldens are the
     single-call A/B baseline, and reversibility is git (complexity reduction 1).
  3. **Model + cost.** `COGNITION_MODEL` default → **`claude-fable-5`** (thinking always-on —
     omit the param; server-side refusal fallback → `claude-opus-4-8`, which doubles as the A/B
     knob). Cost = ACTUAL API usage→$ (pricing lives only in `anthropic_caller`), printed per
     pass. **No ceiling in v1** — observe the completed system's real cost first, then set
     `COGNITION_COST_CEILING` (OQ9 revised). A fixed input-size sanity guard covers the
     pathological case. Expected ≈ $1.20-1.50/talk.
  4. **Reader-context parity.** `READER_DOMAIN` + `CURRENT_WORK` (founder persona: robotics
     entrepreneur/CEO; Tripp arm + LSIC pipeline as current work — blessed 2026-07-03) baked into
     `.env`; `remote.py` tops them up into the VM `.env` (same grep-append as the ANTHROPIC
     key). No-domain degrade → GENERIC self-questions — the section never silently vanishes.
  5. **Failure semantics.** A missing/invalid required field (`operating_algorithm`,
     `cognitive_moves`≥10, `founder_lens`, `learn_it`) gets ONE plain re-issue retry (identical
     call — no repair prompt), then degrades with a **visible `cognition_status`** in the
     bundle + JSON. Schema: ONE downstream contract — `founder_lens` + `learn_it` are
     optional-default-empty fields on `CognitionOutput` v3 (each pass validates its half via
     thin submodels); "absent ⇒ section omitted" falls out of the defaults for free.
  *Gate:* `/python-unit-tests` fakes — two-pass merge · retry-then-status · per-pass cost
  reporting · key-list env top-up · no-domain generic questions · **briefing byte-identical** — **+** live A/B:
  regenerate the Karpathy talk → `golden/lXUZvyajciY_v4_depth3/`, judged vs `v2_opus` +
  `v3_mapreduce` by eye; EVAL (next milestone) retro-scores it deterministically (moves ≥10,
  ≥2 final-third cites, verbatim-quote match, sections present).
  *Provenance:* Alex's cognitive-core framework (thought-process extraction, 2026-07-01) +
  the 2026-07-03 research adoptions — ACTA knowledge-audit probes (Militello & Hutton),
  Matuschak retrieval-prompt rules, the wedge rubric (NFX / Every), and quote-first /
  according-to grounding.
  - **✅ CLOSED OUT 2026-07-04 (successful).** Code `b02bae4` + `8420c63` on `alex/depth-v3`;
    164 tests + `--selftest` green; briefing byte-identical. **A/B (Alex): PASS** — "exactly
    the direction I want to go in"; one defect class found in grading (talk vernacular
    referenced but never introduced — 'nines', the joke anecdote) → the **SELF-CONTAINED
    RULE** added to both prompts; the v4.1 re-run passes every gate: 13 moves (≥10) spanning
    `[00:14]`→`[110:42]` with 2 final-third cites, 13/13 quote + fails_when + self_question,
    5 founder plays, 8 retrieval prompts, clean `cognition_status`, vernacular glossed at
    first use. **Frozen:** `golden/lXUZvyajciY_v4_depth3/` (47.2KB notes.md).
    **Observed cost (OQ9 data):** clean run ≈ **$3.03/talk** (extract $1.67 + convert $1.36;
    ~90k input tokens each — full-transcript confirmed); the first v4.1 attempt cost ~$9.83
    via a truncation retry storm (16k output cap → unparseable JSON → 4 identical full-price
    internal retries) → `call_json` now **fails fast** on max_tokens truncation. Suggested
    ceiling when enforcement lands: ~$5/talk.

- [x] **MAPRED — profile-owned synthesis + lecture map-reduce** (VERIFIED 2026-06-27; R1/R5) — introduce
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
  - **⚙ Build context (mapped + verified 2026-06-26 — scope REDUCED):** the `Profile.synthesize(ctx)`
    seam **and** the briefing-verbatim move are **ALREADY DONE** — `synthesize_full` dispatches at
    [synthesize.py:371] `thematic, pres_outputs = prof.synthesize(ctx)`; `briefing_synthesize`
    ([synthesize.py:627-644]) + `lecture_synthesize` ([synthesize.py:647-656]) are wired as `Profile`
    callables ([profiles/__init__.py:38,44]). So MAPRED collapses to **3 moves**: **(1)** NEW
    `src/segment.py` `segment(evidence, budget_chars) -> windows` — **SIZE/token windowing, NOT author
    chapters** (decision 2026-06-26): sort evidence by `timestamp_start`, greedily accumulate until the
    window's text would exceed `budget_chars` (≈ tokens×4; env `WINDOW_BUDGET`), then close; each window
    `= (idx, start_sec, end_sec, evidence_subset)`; total ≤ budget ⇒ 1 window (always ≥1). Window count
    scales with **video length** — the real constraint — not where the uploader drew chapter marks
    (`meta["chapters"]` is now **irrelevant** to synthesis). **(2)** NEW `src/synth_mapreduce.py` — MAP
    each window's evidence subset (per-window `_build_event_context`) → REDUCE once (single-producer;
    reuse the lecture thematic keys + `tensions`). **(3)** rewire **only** the `_call_thematic` at
    [synthesize.py:652] inside `lecture_synthesize`; `_call_cognition` ([:655]) and `briefing_synthesize`
    stay untouched. Removes the 140k ceiling (`_build_event_context`, [synthesize.py:532-552]) for lecture.
    **Gaps eliminated by size-windowing:** no-chapter / non-YouTube / long-non-chaptered edges all vanish —
    every input is windowed uniformly, nothing truncates. **Auto-select (OQ3 RESOLVED):** map-reduce iff
    `len(windows) ≥ 2` (evidence text > `WINDOW_BUDGET`), else today's single call (degrade-to-today).
    Open: `WINDOW_BUDGET` default — tune via A/B vs `golden/` (OQ8). Test seam: monkeypatch
    `synthesize._call_thematic` per window (existing fakes pattern, `tests/test_cognition.py` `_ctx()`).
    EVAL comes after ⇒ A/B by eye vs `golden/` bundles.
  - **✅ Code SHIPPED 2026-06-26 on `alex/mapred-windows`:** `src/segment.py` (size windowing) +
    `src/synth_mapreduce.py` (MAP→REDUCE, single-producer, injected `call_json` ⇒ no import cycle)
    + the window-gated branch in `lecture_synthesize` ([synthesize.py:647]). **Gates:** 144 pytest
    green (new `test_segment.py` ×7 + `test_synth_mapreduce.py` ×6 — single-producer, map-once/
    reduce-once-over-union, map-failure degrade, ≥2-window routing vs ≤1-window single call) +
    `--selftest` OK; briefing + ≤1-window lecture byte-identical. **Scope notes:** `tensions` field
    **deferred** (needs a new lecture render section — beyond this minimal rewire); the dedicated
    **cognition call stays single-pass** (still 140k-capped — separate follow-up). **Before merge:**
    a live A/B-by-eye on a long lecture vs `golden/` (the eval-lift check; EVAL milestone next).

### PART 2 — Ship at scale (CLOUD_BATCH tail; independent of PART 1)

- [x] **FIX — corpus driver + ingest retry + remote hardening** (DONE 2026-07-04) —
  (a) `run_corpus.sh`: `run_one` `return 0` always (one bad event can never abort the
  `xargs -P` batch); ✅/❌ recorded to `logs/_{ok,fail}.txt`; the summary **counts the
  driver's own records** (the old tally log-grepped `"report OK"` and — pre-existing bug —
  the trailing GCS guard made every non-GCS run exit 1; now explicit `exit 0`).
  (b) `ingest.py._fetch_with_retry`: bounded whole-command retry on a non-zero yt-dlp/curl
  exit (NOT `util.retry_transient` — its message-marker classifier can't see a
  `CalledProcessError`; the exit code itself is the signal). First-try success = zero sleeps.
  (c) `remote.run_remote_job` (from Known Failures): **detached nohup launch + VM-side log
  (`_lsic_run.log`) + short-lived poll sshes** — the blocking IAP ssh that died mid-v4.1-run
  and took the cost lines with it can no longer kill a job; DONE/RUNNING/DEAD polls, log tail
  surfaced locally either way.
  *Gate:* 184 tests + `--selftest` green — `test_corpus_driver` runs the REAL bash driver with
  a stub `$PY` (poisoned event doesn't drop the rest; tally counted not grepped; all-green
  clean); ingest retry (transient-then-success · zero-cost success · dead-URL raises);
  remote (detached launch · poll-until-done · dead-job surfaces log then raises, VM still stopped).

- [ ] **RUNEASY — one-command multi-video front door** (SCOPED 2026-07-05 via the 7-role Q&A;
  depends on FIX ✓) — make running "a bunch of videos" one short command; **"just type run all"**.
  - *Input (strict template):* `links.txt` — one URL per line, `#` comments, blank lines ignored;
    parsed by a small `_parse_links` function in `adhoc.py` (CR4 — no shallow links module).
    Repo-root default so the command needs zero args. URLs route through the existing `--source`
    adhoc path — **NOT** the catalog machinery.
  - *Command:* `python -m src.main --source-list [FILE=links.txt]` + a 2-line `./run_all` alias
    (pure `exec` of the same path — an alias, not a second command path). `--local` opt-out
    (default `--remote`); `--redo` forces re-run.
  - *Loop shape (Q7 + CR1 — ONE loop everywhere):* **in-process Python loop** in the adhoc
    path — per-URL no-drop (one bad video logs ❌ and the loop continues, FIX semantics),
    ✅/❌ tally. The remote batch simply runs `--source-list links.txt --local` ON the VM —
    no separate VM runner exists, and **resume-skip lives in the loop only** (wherever the
    loop runs, resume works). `run_corpus.sh` stays catalog-only; no second bash driver.
  - *Remote (OQ6 resolved 2026-07-05 — one VM run looping ON the VM):* the links file is
    **pushed to the VM as a file, never interpolated into ssh argv** (Q6, quoting/injection
    surface); detached launch + VM-side log via a **shared `_launch_and_poll`** (CR2 —
    `run_remote_job`'s FIX machinery generalized, not copied). The loop writes a one-line
    `PROGRESS` file (`3/10 <video_id>`) as it goes and a `BATCH_DONE` sentinel at the end, so
    the poll stays the same **stateless** DONE/RUNNING/DEAD check with a different done-test
    (CR3 — no log-advancement stall detector; the batch deadline scales with list length).
    The poller prints `PROGRESS` changes live (Q4: running `n/10` + current video) and
    per-video $ + the batch $ total from the VM log at the end.
  - *Output (OQ7):* `<out>/<video_id>/` per video — notes.md · coverage_report.md ·
    references.md · slides. Batch summary table: per video ✅/❌ + EVAL gate column
    (**reported, not enforced** — Q2: gates were tuned on a 146-min talk) + $.
  - *Resume (Q3):* re-running the same doc **skips videos whose output subfolder is already
    complete** (notes.md present); upstream stages are cache-skipped anyway; duplicate URLs
    dedupe to one cached event; `--redo` overrides.
  - *Deferred but planned (Q5):* playlist/channel URLs auto-expanded via
    `yt-dlp --flat-playlist` — v2; the links-file format is unchanged when it lands.
  - *Degrade-to-today:* catalog-id and single `--source` inputs run today's exact paths;
    the list input is the only new branch.
  *Gate:* `/python-unit-tests` — links parsing (strict template) · skip-completed resume ·
  no-drop loop · file-push (no argv interpolation) · sentinel/`PROGRESS` poll — all fakes, no network.
  **+ VALIDATION CRITERION (Alex 2026-07-05):** a document with **10 video links**, one
  command, PASS = all 10 output subfolders exist with `notes.md` + `coverage_report.md` +
  clean `cognition_status`; any failure is loud in the tally.

- [ ] **BATCH — the 122-event run** (was CLOUD_BATCH M-F2) — `run_corpus.sh filter` over the
  122 video-bearing events, 4h cap applied, `--dry-run` cost gate per event, stop on $ ceiling
  (OQ5). *Gate (binary):* GCS `notes.md` count == expected (≤122); spot-check 3 bundles valid;
  spend ≤ ceiling; sync-back populates local `Report/`.

---

## Implementation Outline

### Dependency graph + build order

```
DONE: BASE (frozen A/B ref) · DEPTH v1/v2 (cognition layer) · MAPRED (verified 2026-06-27; merge pending)
DEPTH v3 (full-context two-pass cognitive core; Founder Lens + Learn-It; beat v2_opus/v3 on the A/B)
   ──► EVAL (pure scorer + v3 cognition checks; retro-scores MAPRED + DEPTH v3)
   ──► FIX (driver no-drop + ingest retry) ──► RUNEASY (list/playlist → --remote) ──► BATCH (122-run)
```
Build order **DEPTH v3 → EVAL → FIX → RUNEASY → BATCH** (re-prioritized 2026-07-03). Each: own
branch `alex/<short-desc>`, degrade-to-today (default monolith = byte-identical), fakes-only tests
green, merged only when green + verified.
**Caveat (eval-first tension):** MAPRED now lands BEFORE EVAL, so during MAPRED there is no
deterministic scorer — lift is judged **by eye against the frozen golden bundles**
(`golden/lXUZvyajciY_{baseline,v2_opus,v2_gemini}/`). EVAL retro-scores MAPRED immediately after.

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
| `test_cognition_v3` (fakes)   | two-pass merge; retry-then-status; cost reporting; key-list top-up; generic-question degrade | DEPTH v3 |
| EVAL v3 cognition checks      | moves ≥10; ≥2 final-third cites; quotes verbatim-match transcript; sections present           | EVAL     |
| A/B v4 vs v2_opus/v3 by eye   | founder-lens utility; move depth; learn-it quality (human judgment — EVAL can't score taste)  | DEPTH v3 |
| `test_corpus_driver` (fakes)  | a failing event doesn't drop the rest; ingest retry          | FIX      |
| Existing 113 tests            | no regression with all new paths OFF                         | every step |
| Full-run count + spot-check   | 122 bundles, spend ≤ ceiling                                 | BATCH    |

---

## Footer

### Known Failures

_Inherited from CLOUD_BATCH / EASYRUN; resolved within this plan's FIX milestone._

| Symptom                                              | Root cause                                                                                  | Fix (this plan)                                                    | Status |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- | ------ |
| `run_corpus.sh` silently dropped 1 of 5 events       | `run_one` lets a non-zero exit propagate; `xargs -P` aborts the whole batch on a 255 exit   | FIX: `return 0` trap in `run_one`, ✅/❌ tally files, explicit driver `exit 0` | FIXED (2026-07-04, test_corpus_driver) |
| Ingest died on a transient yt-dlp 503/throttle       | `_fetch_youtube`/`_fetch_http` have no whole-command retry ([src/ingest.py:151-176])        | FIX: `_fetch_with_retry` — bounded outer retry keyed on the exit code | FIXED (2026-07-04) |
| Long-video synthesis truncated / "lost in the middle" | thematic call caps context at 140k chars ([src/synthesize.py:553])                          | MAPRED: chapter map-reduce removes the single-call ceiling         | OPEN   |
| `validate_notes`/`validate_slides` false-fail on a `lecture` bundle | both encode the 15-section LSIC **briefing** template only | EVAL (profile-agnostic, reads structured JSON) is the lecture scorer; a profile-aware validator is a later option | KNOWN  |
| `references.md` off-target on metaphorical claims    | `derive_queries` keyword-matched "building animals/ghosts" → smart-buildings energy papers   | EASYRUN M3.1 residual; LLM query-gen is the upgrade (out of scope here) | KNOWN  |
| v3 lecture bundle lost Transfer Questions entirely   | `--remote` VM never receives `READER_DOMAIN`/`CURRENT_WORK` (remote.py ships only API keys); the prompt orders an empty list on no-domain; render omits empty sections silently | DEPTH v3: bake into `.env` + remote top-up; generic-question degrade; visible `cognition_status` | FIXED (v4.1 verified 2026-07-04) |
| No cognitive move cites past `[83:33]` of a 146-min talk | cognition call is single-pass under the 140k-char cap ([synthesize.py:606], [:532]) — the model never SEES the last hour | DEPTH v3: uncap the cognition context (one full-context Fable call) + EVAL final-third guard | FIXED (v4 cites to [139:53]; v4.1 [110:42]) |
| Educator perspective appears by luck (1 of 5 golden bundles) | lens selection is model-free-choice ("choose 3-5 perspectives that genuinely fit")     | DEPTH v3: dedicated How-to-Learn-It section owned by the CONVERT pass (always rendered)       | FIXED (v4.1 verified 2026-07-04) |
| Cognitive Moves thin (≤7 moves × 1 sentence)         | the prompt itself caps output: "4-7 entries", "one substantive sentence per item, no padding"; 8-tag set; no exemplars | DEPTH v3: ≥10 moves × 2-3 sentences, 15-tag + ACTA probes, few-shot exemplars                 | FIXED (v4: 17 moves; v4.1: 13) |
| Notes reference talk vernacular never introduced ('nines', 'three jokes') | extraction compressed to insider shorthand — written for someone who watched the talk | SELF-CONTAINED RULE in both prompts (`8420c63`): one-clause setup at first use; terms carry definitions | FIXED (v4.1 verified 2026-07-04) |
| `--remote` job died with ssh 255 mid-run              | gcloud IAP ssh drops on long silent stretches (a Fable pass thinks for minutes with no output); remote stdout — incl. the cost lines — dies with the channel | FIX: `run_remote_job` → detached nohup + `_lsic_run.log` + DONE/RUNNING/DEAD polls; log tail surfaced locally | FIXED (2026-07-04) |
| First v4.1 extract burned 4× $1.70 on identical retries | 16k output cap truncated mid-JSON; `call_json` retried identical params at full price | `call_json` fails fast on max_tokens truncation (2026-07-04); raising the cap via streaming is a FIX option | FIXED  |

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
