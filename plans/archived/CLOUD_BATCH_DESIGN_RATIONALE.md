> _Original record of the decision-making process, captured at planning time. May have drifted from the current code — NOT authoritative. See the durable PLAN for current truth._

# Cloud Batch — Design Rationale (frozen provenance)

**Scope.** Take the validated local LSIC Event→Briefing pipeline and run a **first
production batch** in the cloud: the **Energy ∪ ISRU** slice of the catalog, producing
the same per-event `Report/` bundle (`notes.md` + `slide_captions.md` + `slides.pdf` +
`equations.md`) that the pipeline already produces locally for `lsic_2025-06-25`.

**Captured:** 2026-06-09. **Author of record:** planning session on branch
`alex/asr-crashfix-speed`.

---

## 1. Decisions record (choice + rationale)

| #  | Decision               | Choice                                                                                                                             | Rationale                                                                                                                                                                                                                                                                                  |
| --- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1  | Effort decomposition   | **Three sequential parts**: (1) batch-processing code [untested], (2) cloud+Docker on 5 picked full events, (3) full 122-event run | Each part is independently green + deployable; Part 1 is highest-risk because it has never been run, so it is built and tested first against fakes before any cloud spend                                                                                                                  |
| 2  | Filter definition      | **`topics ⊇ {Surface Power} ∪ {In Situ Resource Utilization}`**                                                                    | Deterministic from the catalog `topics` field — no keyword guessing. Reproduces the target count exactly                                                                                                                                                                                   |
| 3  | Filter source-of-truth | **`download_lsic/selected_manifest.json`** (curated, 181 events)                                                                   | Pre-vetted for downloadability; reproduces **130 events / 122 with video** exactly (vs full catalog's 298→130/123). The 122-with-video set is the runnable batch                                                                                                                           |
| 4  | Robotics in batch 1    | **Dropped** (`Excavation and Construction` excluded)                                                                               | Commander scoped batch 1 to Energy + ISRU; Robotics is a later batch                                                                                                                                                                                                                       |
| 5  | Cloud target           | **GCP VM + GCS**                                                                                                                   | Co-located with Gemini: service-account auth (no API-key sprawl), lower egress, easier quota raises. Commander confirmed GCP project + billing ready. `AWS_batch.md` is explicitly **non-authoritative** context, not ground truth                                                         |
| 6  | LLM batch backend      | **Single Gemini Batch API path** for ALL LLM stages                                                                                | Investigation found **all four LLM stages are Gemini** (ASR + VLM `flash`, synth `pro`); the Claude/Anthropic backend was already migrated out (vestigial in comments + `requirements.txt`). "Batch all the LLM work" therefore needs ONE backend, not two. Drops the dead `anthropic` dep |
| 7  | Batch topology         | **Pipeline of per-stage batch jobs**                                                                                               | Stages are sequential per event (transcribe→align→synth), but the work *within* a stage fans out across all events. Batch each stage across the whole event set; `align` is local Python between batches                                                                                   |
| 8  | Output contract        | **Full `Report/` bundle incl. `equations.md`**                                                                                     | Commander: "Report + equations is what I want for the Cloud Version." `equations.md` currently lives in `05_briefing/`; the cloud version **promotes it into `Report/`**                                                                                                                   |
| 9  | Slice output           | **Full Report bundle** for all 5 picked events                                                                                     | Commander upgraded the slice from notes-only to full bundle — the slice must prove the *complete* product, including `slides.pdf` render and `equations.md`                                                                                                                                |
| 10 | Slice events           | **5 Commander-picked FULL events** (process all videos + decks per event)                                                          | Real-data validation of container parity + batch path + GCP auth on a representative spread (4 Surface Power + 1 ISRU; single-video telecons → 7-video workshop)                                                                                                                           |
| 11 | Big-event cap          | **4 h aggregate video per event**                                                                                                  | The ~11 multi-video Meetings (7–21 videos) are the cost/time tail. Cap the *sum* of an event's video durations at 4 h; truncate beyond. Extends the existing `--max-sec` from per-event-transcribe to a true aggregate bound across stages                                                 |
| 12 | Non-breaking gate      | **Degrade-to-today** on every new path                                                                                             | Batch path, topic filter, and cap are all flag/signal-gated; unset ⇒ byte-identical to today's sync local behavior (CLAUDE.md §3)                                                                                                                                                          |
| 13 | Test gate              | **Fakes-only `/python-unit-tests`**, no network                                                                                    | Each new behavior (build_jsonl, distribute_results, filter set, cap truncation) has a deterministic in-memory test; merge only on green (CLAUDE.md §2)                                                                                                                                     |

---

## 2. Q&A record (the IDEATION chat)

**Q1 — Cloud target?** → *AWS_batch.md is not certain; pick the best option; if GCP VM is
easier it should be chosen.* Later confirmed **GCP ready (project + billing)**.

**Q2 — Filter source-of-truth?** → **Curated `selected_manifest`.** (Reproduced: 130
events / **122 with video** — matches the stated 122 exactly.)

**Q3 — Gemini sync vs Batch for batch 1?** → **Gemini Batch API for batch 1.**

**Q4 — Output contract?** → Initially *full bundle for 122, notes-only for the 5-slice* →
**revised to full bundle for the 5-slice too.**

**Q5 — Batch scope across LLM stages?** → *All three (incl. Anthropic Batches)* → **corrected
during investigation: synth is Gemini, not Claude → one Gemini Batch backend covers all.**

**Q6 — Cap rule for big Meetings?** → **Cap by total aggregate video hours = 4 h per event.**

**Q7 — The 5 slice events?** → Commander named them (resolved against the catalog):

| # | Handle given                                          | Resolved event                                                          |
| --- | ----------------------------------------------------- | ----------------------------------------------------------------------- |
| a | Speaker: Brianne DeMattia                             | `63600025` — Surface Power April 2026 Telecon (video 3178 + pptx + pdf) |
| b | `3022-GMT20260129…` / Sotirios Zormpas                | `lsic_2026-01-29` (pilot event; slides done, report pending)            |
| c | Agenda `id=638` + YT playlist `…MGjmj`                | `638` — Surface Power Sept 2025 Workshop (**7 videos**)                 |
| d | Cadogan/Hunt · *Opterus 50kW R-ROMA … Telecon.pdf*    | `618` — Surface Power July 2025 Telecon (video + 2 pptx + pdf)          |
| e | ISRU July 2025 Workshop Pt.3 · Berdis/Coburger/Miller | `624` — ISRU July 2025 Workshop (Recording3 Miller)                     |

**Q8 — Read-only lookups / settings?** → *Pre-authorized; update settings as needed.*
(Found `Bash(*)` already allowed in `.claude/settings.local.json` — no change required.)

---

## 3. System-design hierarchy

```
EFFORT
├── PART 1  Batch processing (code, untested)        [no cloud, no network — fakes only]
│   ├── src/batch_gemini.py            build JSONL → submit → poll → distribute to caches
│   ├── stage wiring                   transcribe / visual / slide_book / synthesize → opt-in batch
│   └── degrade-to-today gate          batch OFF ⇒ today's sync calls, byte-identical
│
├── PART 2  Cloud + Docker, 5 full events            [GCP VM, real data]
│   ├── Dockerfile + .dockerignore     ffmpeg · libreoffice · yt-dlp · PyMuPDF · entrypoint
│   ├── GCP provisioning               VM + GCS + service account (Commander runs in their project)
│   ├── topic filter wrapper           Energy∪ISRU event-id set → group_manifest.build(event_ids)
│   ├── 4h aggregate cap               sum(video durations) ≤ 14400s, truncate beyond
│   └── slice run                      5 full events → full Report bundle each → validate
│
└── PART 3  Full processing                           [GCP, the 122]
    ├── run_corpus.sh                  xargs -P over 122 event ids, batch mode, per-event log
    ├── GCS sync + sync-back           Report bundles → bucket → local work/events/<id>/Report/
    └── cost gate                      --dry-run estimate per event; stop on ceiling breach
```

---

## 4. Trade-off analysis

| Axis           | Option A                  | Option B        | Chosen          | Why                                                                                |
| -------------- | ------------------------- | --------------- | --------------- | ---------------------------------------------------------------------------------- |
| Cloud          | AWS Spot (plan-of-record) | GCP VM          | **GCP**         | Gemini co-location: auth + egress + quota; Commander has GCP billing               |
| Batch backends | Gemini + Anthropic (2)    | Gemini only (1) | **Gemini only** | All stages are Gemini; Anthropic is dead code                                      |
| Gemini mode    | Sync + retry              | Batch API       | **Batch**       | 50% cheaper, no 503 fighting, higher limits; async 2–6 h acceptable for a bulk run |
| Build order    | Cloud-first               | Code-first      | **Code-first**  | Batch code is untested — prove it on fakes before paying for cloud                 |
| Big events     | Process whole             | 4 h cap         | **4 h cap**     | One 21-video Meeting could dominate cost/time; cap bounds the tail                 |
| Slice output   | Notes-only                | Full bundle     | **Full bundle** | Slice must validate the *complete* product incl. slide render                      |

**Key risk accepted:** Gemini Batch turnaround is async (2–6 h); the pipeline's manifest
gates + per-chunk caches already make resume-after-wait free, so latency is tolerable for
a bulk job and is the price of killing the 503 wall + halving cost.

---

## 5. LLM instructions used to generate this document (reproduce prompt)

> Read `.claude/CLAUDE.md`, `HANDOFF.md`, `AWS_batch.md`, `PLAN.md`, and the existing
> `work/events/lsic_2025-06-25/Report/` bundle. Treat `AWS_batch.md` as non-authoritative
> context. The Commander wants a first cloud batch producing the same Report bundle (+
> equations) for the **Energy ∪ ISRU** catalog slice, decomposed into 3 parts: (1) untested
> batch-processing code, (2) cloud+Docker validated on 5 named full events, (3) the full
> run. Run IDEATION MODE: ground the filter against the `topics` field in
> `selected_manifest.json`, ground the LLM-call seams in `src/{transcribe,visual,slide_book,
> synthesize}.py`, ask decision-changing questions only, then write this frozen rationale
> plus the durable `CLOUD_BATCH_PLAN.md`. Honor degrade-to-today + fakes-only test gates.
