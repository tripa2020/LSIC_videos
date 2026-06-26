> ⛔ **SUPERSEDED (2026-06-25) by [`SYNTH_QUALITY_PLAN.md`](SYNTH_QUALITY_PLAN.md).** This was
> design-only and never built. Its milestones were cannibalized into SYNTH_QUALITY with clearer
> names: **M-S0 → EVAL**, **M-S1 → DEPTH**, **M-S2 → MAPRED** (M-S3 report + M-S4 critic→revise
> deferred). Kept for design provenance only — do **not** drive work from this file.

# SYNTH_V2 — Durable PLAN (map-reduce synthesis · coherence · coverage)

_Living source of truth. Frozen provenance: `SYNTH_V2_DESIGN_RATIONALE.md`. Status: **DESIGN —
not yet built** (awaiting complexity review + "code it")._

## Intro

- **Goal.** Make synthesis produce **fully-covered, coherent, deeper** briefings on **long**
  videos — by reasoning **per chapter then weaving once** — and make "did we miss anything / is
  it coherent" a **measurable** number.
- **Inputs.** The existing per-event artifacts (`02_transcript`, `04_aligned/evidence.json`,
  `meta.json` chapters); the active `Profile`.
- **Outputs.** Same `notes.md` template (richer content + new item sub-fields) **plus** a
  **coverage/coherence score** artifact. Default path stays byte-identical.
- **Core abstraction.** **Map-reduce with single-producer-per-section**, **owned per Profile.**
  MAP extracts *local* facts per map-unit; REDUCE produces *every global section once* over the
  evidence union. The map-unit is **profile-specific**: `briefing` already maps over
  **presentations** (today's per-presentation + thematic call — *unchanged*); `lecture` maps over
  **chapters** (new). The same `[mm:ss]` grounding measures coherence (cite-spread) and coverage.
- **NOT an overwrite.** SYNTH_V2 **generalizes the map-reduce pattern LSIC already uses** — it does
  not replace it. `briefing.synthesize` is the existing code moved verbatim (byte-identical LSIC);
  only `lecture` runs the new chapter path. The only thing spanning both profiles is the
  **read-only** coverage/coherence score (it measures, never mutates).

## Architecture Decisions

| Decision | Choice | Rationale | Date |
|------------------------|------------------------------------------------------------|------------------------------------------------------------------------------|------------|
| Synthesis topology     | Map-reduce over chapters                                    | Removes the 140k truncation + "lost in the middle"; full attention per part   | 2026-06-11 |
| Coherence enforcement  | **Single-producer-per-section** (MAP extracts, REDUCE synthesizes once) | Structurally prevents N disconnected mini-summaries                          | 2026-06-11 |
| Coherence verification | Cite-spread / cross-chapter ratio (free) + coherence judge | The grounding that powers citations measures cross-chapter reasoning          | 2026-06-11 |
| Coverage measurement   | Tiered: chapter-coverage + groundedness → critic → recall  | Highest-ROI free signals first; recall as the validating eval                 | 2026-06-11 |
| Compute tiering        | flash perception · pro synth · +critic→revise pass         | Spend where reasoning compounds; test-time compute > bigger base model        | 2026-06-11 |
| Item depth             | sub-fields: mastery_signal · engineering_gap · math_framework | Depth via structure; math_framework is also a citation hook                  | 2026-06-11 |
| Eval-first             | Build the coverage/coherence eval FIRST                     | Map-reduce ships only on measured lift, no regression (Engineering Discipline)| 2026-06-11 |
| Non-breaking           | Default monolith (byte-identical); map-reduce flag/threshold-gated | Degrade-to-today; LSIC + short videos unchanged                              | 2026-06-11 |
| **Strategy ownership (R1)** | Each `Profile` owns a deep `synthesize(ctx)`; **no mode-branch** | Kills the parallel synthesis path; `briefing` = today's code verbatim (LSIC byte-identical); map-reduce scoped to `lecture` | 2026-06-11 |
| **Map unit (R1)**      | Per-profile: `briefing`→presentation (today), `lecture`→chapter | LSIC already map-reduces per presentation — generalize, don't replace        | 2026-06-11 |
| **Eval interface (R2)** | `synth_eval` reads the **structured reduce JSON + evidence**, never rendered markdown | Decouples the eval from every render/template tweak; profile-agnostic (can score LSIC unchanged) | 2026-06-11 |
| **Eval purity (R3)**   | `synth_eval` = **pure deterministic** guardrail only; LLM critic/judge live in the M-S4 revise loop | Deep, free, CI-able guardrail; LLM cost isolated to the quality pass         | 2026-06-11 |
| **Flag collapse (R4)** | Drop `--synth-mode`; map-reduce auto-selects by an internal duration constant; keep only `--quality` | One synthesis knob, not three (env override for debugging)                   | 2026-06-11 |
| **Segmenter contract (R5)** | `segment()` **always** returns ≥1 unit (whole video if no chapters) | Defines the no-chapters edge out of existence; downstream consumes N≥1 uniformly | 2026-06-11 |

### System map

```
 segment(meta.chapters | auto)              [NEW]
        │  [(start,end,title)]…
        ▼
 MAP: per-chapter EXTRACT  ──(cache per chapter)──┐   local facts only:
        │                                         │     points · claims(+sub-fields) ·
        ▼                                         │     methods · evidence[mm:ss]
 REDUCE: global SYNTH (single-valued schema) ◄────┘   Summary · Lenses · Outlook ·
        │   evidence UNION across chapters             Field Impl · Takeaways · Open Qs · tensions
        ▼
 CRITIC → REVISE (completeness + coherence)   [opt, --quality]
        │
        ▼
 notes.md (same template)  +  coverage/coherence score   ──►  Report/
```

### Open Questions

| #     | Question | Resolve-by |
|-------|----------|------------|
| OQ-S1 | Duration threshold for auto map-reduce (e.g. >45 min)? | M-S2 |
| OQ-S2 | Auto-segmentation for non-chaptered videos — topic-shift vs fixed-window? | M-S2 |
| OQ-S3 | Cross-chapter-ratio threshold for the CI coherence guardrail? | M-S0 (set from baseline) |
| OQ-S4 | Critic/judge model — flash (cheap) or pro (sharper)? | M-S4 |

### Deliverable / Output Contract

- `notes.md` — same template; map-reduce variant must show **no truncation** on long videos and
  carry the new sub-fields.
- **Coverage/coherence score** (new artifact) — `chapter_coverage %`, `cross_chapter_ratio`,
  `groundedness %`, `critic_omissions`, `coherence_judge`.
- **Acceptance:** map-reduce ≥ monolith on the coherence judge for short videos (A/B) **and**
  `cross_chapter_ratio ≥ OQ-S3 threshold` **and** zero chapter-index leakage.

---

## Repo Layout (new/changed — per-file LOC budgets)

```
src/
├── segment.py            NEW ≤80   map-units: meta.chapters | auto-segment → ALWAYS ≥1 (R5)
├── synth_mapreduce.py    NEW ≤180  map (per-unit extract) → reduce (single-producer global synth); used BY lecture
├── synth_eval.py         NEW ≤120  PURE deterministic guardrail (R3): cite-spread · cross-chapter ratio ·
│                                   chapter-coverage · groundedness · leak-regex — reads structured JSON (R2)
├── profiles/
│   ├── __init__.py       MOD +≤15  Profile gains ONE deep method `synthesize(ctx)` (R1) — no leaked prompts
│   ├── briefing.py       MOD +≤20  wrap today's per-presentation+thematic code AS-IS into briefing.synthesize (verbatim)
│   └── lecture.py        MOD +≤80  lecture.synthesize = chapter map-reduce (calls synth_mapreduce) + sub-fields
│                                   (mastery_signal/engineering_gap/math_framework) + render
├── synthesize.py         MOD +≤25  synthesize_full keeps shared scaffolding (load/cache/manifest) → calls prof.synthesize()
├── main.py               MOD +≤8   ONLY `--quality` (R4); auto-by-duration is internal; print coverage score
└── report.py             MOD +≤6   ship coverage_report.md (optional artifact)
tests/  test_segment.py · test_synth_mapreduce.py · test_synth_eval.py  (fakes-only, no network)
# LLM critic/judge (completeness, coherence) live in the M-S4 revise loop, NOT in synth_eval (R3).
```

### Fixtures (fakes-only, no network)

| Fixture | Feeds |
|---------|-------|
| Multi-chapter fake transcript + chapter list | `test_segment`, `test_synth_mapreduce` |
| Fake LLM: canned per-chapter extracts + a canned reduce JSON | `test_synth_mapreduce` |
| Canned evidence with chapter offsets (cites spanning 1 vs ≥2 chapters) | `test_synth_eval` (cite-spread) |

---

## TODO milestones (each names unit testing as a gate)

### M-S0 — Deterministic coverage/coherence EVAL (built FIRST; R2/R3) `<!-- progress: SYNTH_M0 -->`
`src/synth_eval.py` — **pure, no LLM, reads the structured reduce JSON + evidence** (R2/R3):
cite-spread · cross-chapter ratio · chapter-coverage · groundedness · chapter-index-leak.
**Profile-agnostic** — scores any briefing incl. LSIC without changing it. Run on the existing
Karpathy output to record a **baseline** + set OQ-S3. (LLM critic/judge/atomic-recall → M-S4.)
*Gate:* `/python-unit-tests` — metrics computed deterministically on fixtures (cites spanning 1 vs
≥2 chapters); baseline JSON emitted.

### M-S1 — Item sub-fields (D6) `<!-- progress: SYNTH_M1 -->`
`lecture.py`: add `mastery_signal` (field-impl), `engineering_gap` (open-q), `math_framework`
(thriving) to schema + render; verbosity via structure. Lands on the **current monolith** (independent).
*Gate:* `/python-unit-tests` — render shows sub-fields, degrades when absent; briefing untouched.

### M-S2 — Profile-owned synthesis + lecture map-reduce (R1/D1/D2/coherence) `<!-- progress: SYNTH_M2 -->`
Introduce `Profile.synthesize(ctx)` (R1). **First move `briefing.synthesize` = today's
per-presentation+thematic code VERBATIM** (proves LSIC byte-identical, no mode-branch). Then
`lecture.synthesize` = `segment.py` (R5) + `synth_mapreduce.py`: MAP extracts local facts per
chapter (cached); REDUCE synthesizes every global section once over the evidence union,
single-valued schema + `tensions`. `synthesize_full` keeps the shared scaffolding and calls
`prof.synthesize()`. Map-reduce auto-selects by internal duration constant (R4).
*Gate:* `/python-unit-tests` — **briefing output unchanged** (selftest + existing synth tests green);
fake LLM map+reduce with single-producer asserted (chapters emit NO summary/lens/outlook) **+** on
a long real video: no truncation, `cross_chapter_ratio ≥ OQ-S3`, coherence judge ≥ monolith on a
short A/B (eval-first).

### M-S3 — Coverage/coherence report + guardrail (D1/D3) `<!-- progress: SYNTH_M3 -->`
Emit the score as `coverage_report.md`; wire the cite-spread/cross-chapter guardrail as a
non-fatal warning in the run + a CI check.
*Gate:* `/python-unit-tests` — score artifact written; guardrail flags a hand-built incoherent fixture.

### M-S4 — LLM critic→revise + compute tiering (D2/D5; R3) `<!-- progress: SYNTH_M4 -->`
The **LLM-based** signals live here (R3): completeness-critic · coherence-judge · atomic-claim
recall. `--quality`: the critic feeds a single revise pass on the reduce output; confirm flash
perception / pro synth split is explicit.
*Gate:* `/python-unit-tests` (fake critic→revise loop) **+** measured lift on the M-S0 deterministic
eval, no regression.

### Implementation Outline — dependency graph + build order

```
M-S0 eval (first) ──► M-S2 map-reduce ──► M-S3 report/guardrail ──► M-S4 critic→revise
        └─ M-S1 sub-fields (independent; lands on current monolith, carried into the map schema)
```
Build order **M-S0 → M-S1 → M-S2 → M-S3 → M-S4**. Each: own branch `alex/<short-desc>`,
degrade-to-today (default mono = byte-identical), fakes-only tests green, **eval lift measured**
before merge (LLM behavior), merged only when green + verified.

---

## Footer

### Known Failures
(none yet — populate after the first map-reduce debug session.)

### Out of scope (parallel tracks)
- **EASYRUN N1** — citation *verification* of predictions (agentic, multi-source stance). Separate plan.
- **Ingest whole-command retry** — OPEN in `EASYRUN_PLAN.md` Known Failures.

### LLM instructions to reproduce this plan
> Rework synthesis into map-reduce over chapters with single-producer-per-section coherence (MAP
> extracts local facts only; REDUCE produces every global section once over the evidence union +
> a `tensions` field). Build the coverage/coherence eval FIRST (cite-spread/cross-chapter ratio +
> completeness-critic + atomic recall); map-reduce ships only on measured lift, default-off
> (byte-identical monolith below a duration threshold). Add item sub-fields (mastery_signal,
> engineering_gap, math_framework) + a critic→revise quality pass. Perception flash, synth pro.
> Non-breaking, fakes-only tests, degrade-to-today; milestones M-S0→M-S4, unit-test gate each.
