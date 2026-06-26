> _Original record of the decision-making process, captured at planning time. May have
> drifted from the current code — NOT authoritative. See the durable PLAN for current truth._

# SYNTH_QUALITY — Design Rationale (frozen provenance)

**Scope.** Reprioritized roadmap (2026-06-25). Prove the full pipeline end-to-end on a real
YouTube lecture **before any changes** and lock that output as an A/B reference; then raise
**synthesis quality** with a *measurable* coverage/coherence eval, item sub-fields, and chapter
**map-reduce** (killing the 140k-char truncation on long videos); then ship the **122-event
cloud batch**. Order is deliberately **quality-first, batch-last** — the Commander cares more
about the YouTube-talk path right now than the LSIC 122. This plan **cannibalizes**
`SYNTH_V2_PLAN.md` (design-only → superseded here) and the unfinished tail of
`CLOUD_BATCH_PLAN.md` (the 122-run + its two open bugs).

**Captured:** 2026-06-25. **Author of record:** IDEATION/qplan session on branch `main`.

---

## 1. Decisions record (choice + rationale)

| #  | Decision                  | Choice                                                                                  | Rationale                                                                                                                                            |
| -- | ------------------------- | --------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | Priority order            | **BASE → EVAL → DEPTH → MAPRED → FIX → BATCH** (ROI 2 → 3 → 1)                          | Commander reprioritized: the YouTube-talk path matters more now than the LSIC 122. Quality work first; the batch (fully built bar 2 bugs) ships last |
| 2  | Baseline first            | Run `lXUZvyajciY` on the **current** (monolithic) pipeline before any code change       | Need a frozen "before" to prove map-reduce is a *measured* lift, not a vibe (Engineering Discipline: eval-first)                                     |
| 3  | Baseline run config       | `--source <url> --profile lecture --references --remote` (on-demand VM)                 | It's a general talk → `lecture`; references on (the point for new sources); `--remote` offloads heavy ASR/VLM to the VM for a long video             |
| 4  | Baseline use              | **Lock the output as the A/B "before" reference**; EVAL sets the threshold from it      | Makes the whole effort measurable; one real artifact anchors OQ-thresholds instead of a guessed constant                                            |
| 5  | Missing local videos      | Ignored — the `--source <url>` path re-downloads via yt-dlp                             | The YouTube files absent from git are moot for the URL adapter; no need to recover them for this test                                               |
| 6  | SYNTH scope               | **EVAL + DEPTH + MAPRED** only (stop before the LLM critic→revise pass)                 | Commander's "2 then 3" + the free DEPTH win (independent, lands on today's monolith). Critic→revise (old M-S4) deferred                              |
| 7  | Milestone naming          | Descriptive prefixes (BASE/EVAL/DEPTH/MAPRED/FIX/BATCH), **drop M-S0/M-S2**             | Commander: "M-S0 and M-S2 are confusing naming conventions." Self-describing names over opaque codes                                                |
| 8  | Doc structure             | **One** new paired plan; SYNTH_V2 superseded, CLOUD_BATCH tail pulled in                | Commander: "add 1 new paired doc and cannibalize the existing." Single active driver; no duplicated milestone detail                                |
| 9  | Synthesis ownership (R1)  | Each `Profile` owns `synthesize(ctx)`; **briefing = today's code moved verbatim**       | No mode-branch / parallel path. LSIC briefing stays **byte-identical**; map-reduce is scoped to `lecture` only (carried from SYNTH_V2 R1)            |
| 10 | EVAL purity (R2/R3)       | EVAL is **pure, deterministic, no-LLM**, reads structured reduce JSON (not markdown)    | CI-able guardrail decoupled from render/template tweaks; LLM judges deferred to the dropped critic pass (carried from SYNTH_V2 R2/R3)               |
| 11 | Map-unit (R1)             | Per-profile: `briefing`→presentation (today), `lecture`→chapter                         | LSIC already map-reduces per presentation — generalize, don't replace (carried from SYNTH_V2)                                                       |
| 12 | Segmenter contract (R5)   | `segment()` **always** returns ≥1 unit (whole video if no chapters)                     | Defines the no-chapters edge out of existence; downstream consumes N≥1 uniformly (carried from SYNTH_V2)                                            |
| 13 | 122-run unaffected by synth | The 122 are `briefing` profile → byte-identical; map-reduce touches only `lecture`     | Sequencing quality before batch does **not** change the 122 output; BATCH is independent and can even run in parallel once FIX lands               |
| 14 | Non-breaking + test gate  | Degrade-to-today on every new path; fakes-only `/python-unit-tests` per milestone        | CLAUDE.md §2/§3; the 113 existing tests + `--selftest` golden stay green                                                                            |

---

## 2. Q&A record (the IDEATION chat)

**Q1 — How to run the baseline?** → `lecture` profile, references on, **`--remote`** (offload to VM).

**Q2 — How much SYNTH_V2 to build?** → **EVAL + DEPTH + MAPRED** (old M-S0 + M-S1 + M-S2); stop before the critic→revise pass (old M-S4).

**Q3 — Role of the baseline output?** → **Lock it as the A/B "before" reference**; EVAL scores it and sets the cross-chapter/coverage threshold.

**Q4 — Plan structure?** → **One** new paired doc; cannibalize SYNTH_V2 (superseded) + CLOUD_BATCH tail. M-S0/M-S2 naming is confusing → use descriptive names.

---

## 3. System-design hierarchy

```
SYNTH_QUALITY
├── BASE    Baseline reference                    [remote VM, real data — no code change]
│   ├── run lXUZvyajciY: --source --profile lecture --references --remote
│   ├── verify-first: confirm --remote forwards --profile/--references
│   └── freeze the bundle as golden/<id>_baseline/ (A/B "before")
│
├── PART 1  Synthesis quality                      [fakes-only gate + measured lift]
│   ├── EVAL    synth_eval.py  pure deterministic scorer (cite-spread, cross-chapter,
│   │           chapter-coverage, groundedness, leak) — sets threshold from BASE
│   ├── DEPTH   lecture sub-fields (mastery_signal · engineering_gap · math_framework)
│   │           lands on TODAY's monolith — independent of map-reduce
│   └── MAPRED  Profile.synthesize(ctx); briefing=verbatim; lecture=segment+map-reduce
│               kills the 140k truncation; REDUCE = single-producer-per-section
│
└── PART 2  Ship at scale                          [the CLOUD_BATCH payoff]
    ├── FIX     run_corpus.sh event-drop bug + ingest whole-command retry
    └── BATCH   the 122-event run (briefing profile, unaffected by PART 1)
```

---

## 4. Trade-off analysis

| Axis            | Option A                 | Option B                  | Chosen                | Why                                                                 |
| --------------- | ------------------------ | ------------------------- | --------------------- | ------------------------------------------------------------------- |
| Order           | Batch-first (ship 122)   | Quality-first             | **Quality-first**     | Commander values the YouTube path now; batch is built, can wait     |
| Baseline run    | Local                    | `--remote` VM             | **--remote**          | Long talk → offload heavy ASR/VLM; auto-stop bounds cost            |
| EVAL signals    | LLM judge now            | Pure deterministic first  | **Deterministic**     | Free, CI-able, decouples from render; LLM judge deferred            |
| SYNTH depth     | Full (incl. critic loop) | EVAL+DEPTH+MAPRED         | **EVAL+DEPTH+MAPRED** | Critic→revise is the long pole; stop at the measured map-reduce win |
| briefing path   | Refactor too             | Move verbatim (R1)        | **Verbatim**          | LSIC byte-identical; map-reduce risk isolated to `lecture`          |
| 122 vs synth    | Couple them              | Independent               | **Independent**       | 122 = briefing profile, untouched by map-reduce; FIX unblocks it    |

**Key risk accepted:** the baseline is a single video. If `lXUZvyajciY` isn't chaptered or is
short, MAPRED's benefit won't show on it alone — EVAL's threshold may need a second long,
chaptered sample. The segmenter's "always ≥1 unit" contract (R5) keeps the no-chapters case
working; A/B on a short video still validates *coherence ≥ monolith* even if truncation never bit.

## 5. LLM instructions used to generate this document (reproduce prompt)

> Read `.claude/CLAUDE.md`, the moved plans in `plans/` (`SYNTH_V2_*`, `CLOUD_BATCH_*`,
> `EASYRUN_*`), and the synthesis code (`src/synthesize.py`, `src/profiles/`). The Commander
> reprioritized to **quality-first, batch-last** and wants a single new paired plan that
> cannibalizes SYNTH_V2 (design-only) and the CLOUD_BATCH tail. Run IDEATION: (1) a BASE
> milestone that runs `lXUZvyajciY` on today's pipeline via
> `--source --profile lecture --references --remote` and freezes it as an A/B reference;
> (2) PART 1 synthesis quality = EVAL (pure deterministic coverage/coherence scorer, reads
> structured JSON) + DEPTH (lecture sub-fields on today's monolith) + MAPRED (Profile-owned
> synthesize, briefing verbatim, lecture chapter map-reduce, single-producer-per-section,
> kills the 140k truncation); (3) PART 2 = FIX (run_corpus.sh event-drop + ingest retry) then
> BATCH (the 122-run). Use descriptive milestone names, NOT M-S0/M-S2. Honor degrade-to-today
> + fakes-only gates; map-reduce ships only on measured lift over the BASE reference.
