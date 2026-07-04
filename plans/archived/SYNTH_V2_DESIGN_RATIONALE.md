# SYNTH_V2 — Design Rationale (frozen provenance)

> Original record of the decision-making process, captured at planning time. May have drifted
> from the current code — NOT authoritative. See the durable PLAN for current truth.

Scope: rework the **synthesis stage** for higher-quality, fully-covered, coherent briefings on
**long** videos — map-reduce over chapters, deeper item structure, a coverage/coherence score,
and compute spent where it pays. (Citation *verification*, EASYRUN N1, is a parallel track —
not this plan.)

## 1. Decisions record (choice + rationale)

| # | Decision | Choice | Why |
|---|----------|--------|-----|
| D1 | Synthesis topology | **Map-reduce over chapters** (per-chapter extract → one global reduce) | Today's single capped call truncates >140k chars and flattens mid-talk detail ("lost in the middle"); per-chapter passes give full attention + no truncation |
| D2 | Coherence enforcement | **Single-producer-per-section** — MAP extracts local facts only; REDUCE produces every global section once | Structurally prevents "N disconnected mini-summaries"; the narrative exists only in reduce |
| D3 | Coherence verification | **Citation-spread / cross-chapter ratio** (free, deterministic) + LLM coherence judge | The same `[mm:ss]` grounding that powers citations measures whether global sections reasoned across chapters |
| D4 | Coverage measurement (D1) | Tiered: chapter-coverage + groundedness (free) → completeness-critic (1 call) → atomic-claim recall (eval) | Highest-ROI signals first; rigorous recall as the validating eval |
| D5 | Compute tiering (D2) | Perception (transcribe/visual) stays **flash**; reasoning (synth) is **pro**; add a **critic→revise** pass | Spend where reasoning is hard + errors compound; test-time compute beats a bigger base model |
| D6 | Item depth (D0) | Add sub-fields: field-impl `mastery_signal`, open-q `engineering_gap`, thriving `math_framework`; verbosity via structure | Depth via structure, not prose; `math_framework` doubles as a citation hook |
| D7 | Eval-first | Build the **coverage/coherence eval FIRST**; map-reduce ships only on measured lift, no regression | CLAUDE.md Engineering Discipline; map-reduce is unproven until measured |
| D8 | Non-breaking | Default = today's monolithic synth (byte-identical); map-reduce flag-/threshold-gated | Degrade-to-today; LSIC + short videos unchanged until eval proves lift |
| D9 | Segmentation | Use YouTube chapters when present; else auto-segment (topic-shift / fixed window) | Chapters are a free, high-quality map unit; fallback for non-chaptered sources |

## 2. Q&A record (the IDEATION chat)

1. **Why cite at all?** → to **substantiate / verify claims & predictions** and give **go-deeper** pointers; corroboration doubles as a **speaker-credibility** signal. (→ EASYRUN N1; informed D6's `math_framework` hook.)
2. **Make Open Questions / Takeaways / Field Implications more verbose?** → yes, via **structure** (sub-fields), not prose. (→ D6)
3. **Which sub-fields?** → field-impl: *what demonstrates mastery/proficiency*; open-q: *what engineering is lacking now*; thriving: *what works well + the math framework behind it*. (→ D6)
4. **How to quantify missing detail?** → coverage methods discussed; chose tiered (D4).
5. **Where to spend compute?** → synthesize; bigger lever is critic→revise, not a bigger model. (→ D5)
6. **Does the convergence mean running synthesis per chapter?** → yes; map-reduce. (→ D1)
7. **How to enforce reduce coherence, and verify it?** → single-producer-per-section (D2) + cite-spread/judge verification (D3).

## 3. System-design hierarchy

```
SYNTH_V2 (synthesis stage rework)
├── EVAL (built first, D7)
│   ├── coverage: chapter-coverage · groundedness · completeness-critic · atomic-claim recall
│   └── coherence: cite-spread · cross-chapter ratio · chapter-index-leak · coherence judge
├── MAP — per-chapter EXTRACTOR (D1/D2): local key points/claims(+sub-fields)/methods/evidence
├── REDUCE — global SYNTHESIZER (D2): Summary · Lenses · Outlook · Field Impl · Takeaways ·
│             Open Qs · tensions  (single-valued schema, evidence union)
├── CRITIC→REVISE — completeness/coherence critic feeds a revise pass (D4/D5)
└── REPORT — notes.md (unchanged template) + a coverage/coherence score artifact
```

## 4. Trade-off analysis

- **Map-reduce vs monolith (D1):** map-reduce removes truncation + raises depth, at **N× synth calls** (cost/latency). Mitigated by per-chapter caching + a **duration threshold** (monolith for short, map-reduce for long) + flag-gating.
- **Single-producer (D2):** the strongest coherence guarantee, but the reduce step must genuinely reason across all chapter notes — done wrong it stitches. Mitigated by the single-valued schema + the `tensions` field + cite-spread verification.
- **Deterministic cite-spread vs LLM judge (D3):** cite-spread is free/objective but a proxy; the LLM judge is holistic but costs a call and is noisier. Use cite-spread as the CI guardrail, the judge as a periodic audit.
- **Critic→revise (D5):** raises quality + gives the coverage score, at +1–2 calls. Gate behind a `--quality` flag.
- **Sub-fields (D6):** richer, more actionable items, but more to extract per item → reinforces the case for map-reduce (a truncated monolith would surface them poorly).

## 5. LLM instructions to reproduce this plan

> Rework the synthesis stage of LSIC_videos into map-reduce over chapters with
> single-producer-per-section coherence (MAP extracts local facts only; REDUCE produces every
> global section once over the evidence union, with a `tensions` reconciliation field). Build a
> coverage+coherence eval FIRST (cite-spread/cross-chapter ratio + completeness-critic +
> atomic-claim recall); ship map-reduce only on measured lift, default-off (byte-identical
> monolith below a duration threshold). Add item sub-fields (mastery_signal, engineering_gap,
> math_framework) and a critic→revise quality pass. Perception stays flash; synth stays pro.
> Non-breaking, fakes-only tests, degrade-to-today.
