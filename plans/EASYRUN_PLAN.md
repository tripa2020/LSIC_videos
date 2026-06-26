# EASYRUN — Durable PLAN (easy-run · multi-source · citations · on-demand cloud)

_The living source of truth for the EASYRUN effort. Frozen provenance:
`EASYRUN_DESIGN_RATIONALE.md`. Status as of 2026-06-11: **M1–M4 + M2.1 shipped to `main`.**_

## Intro

- **Goal.** Make the pipeline trivial to run on **any** media:
  `python -m src.main --source <youtube-url> --out <folder>` → a full `Report/` bundle in the
  right template, enriched with related papers — while the LSIC 122-batch path stays byte-identical.
- **Inputs.** A YouTube URL or local video file (ad-hoc); or the LSIC catalog/job-file path
  (`run_corpus.sh`). `GEMINI_API_KEY`; optional search-API access (arXiv needs none).
- **Outputs.** `Report/{notes.md, slide_captions.md, slides.pdf, equations.md, references.md}`
  copied to a user-chosen `--out` folder (and GCS for LSIC).
- **Core abstraction.** `work/events.json` (a list of `Event`) decouples **input adapters** from
  the **source-agnostic 7-stage core** (ingest→…→report). EASYRUN adds: a third input adapter
  (URL→Event), a **profile** selector in synthesize, a post-synthesize **citation stage**, and an
  **on-demand VM** wrapper. Everything degrades to today when unset.

## Architecture Decisions

| Decision | Choice | Rationale | Date |
|----------|--------|-----------|------|
| Structure | Extend in place via the `Event`/`events.json` adapter seam | Pipeline core already source-agnostic; LSIC is one input adapter | 2026-06-11 |
| Template | `Profile` abstraction; default `briefing` = today verbatim; add `lecture` | Generic talks need a fitting template without breaking LSIC | 2026-06-11 |
| Generic template shape | **One** generic template; keep domain-adapted "Through N Expert Lenses"; mine YouTube chapters + description links | User decision — lenses are the signature feature and are domain-general | 2026-06-11 |
| Generic template depth | Add **Field Implications** (skills/transitions) + **Industry Outlook** (fading vs thriving) | User wants the strategic/career signal, extracted even when only implied | 2026-06-11 |
| Citations | arXiv (no key) behind a `SearchClient` seam; Semantic Scholar drops in later (OQ1) | Academic-first matches the corpus; no key ⇒ default always live | 2026-06-11 |
| Enrich scope | **Opt-in** for the LSIC pipeline (`--references`); **on** for `--source` | Keeps LSIC byte-identical; references are the whole point for new sources | 2026-06-11 |
| Execution env | Ad-hoc **local by default**; `--remote` ⇒ on-demand VM `ensure→start→run→scp-back→auto-stop` | One-offs need no cloud; VM earns its keep on heavy/long + the 122-batch | 2026-06-11 |
| Status column | **Omitted** `refs` from the status matrix | Enrichment is opt-in/optional — a column would read as "perpetually stuck" | 2026-06-11 |
| Non-breaking | Every new flag/stage degrades to today when unset/unavailable | 71 prior tests + `--selftest` golden stay green (now 111 total) | 2026-06-11 |

### System map

```
INPUT ADAPTERS (write work/events.json)        CORE (unchanged)                 EXEC + OUTPUT
 ├─ group_manifest.build() ← LSIC catalog ┐                                     ┌ local (default)
 ├─ discover.discover()    ← file scan    ├─► ingest→transcribe→visual→align    ┤
 └─ adhoc.build_adhoc_event() ← URL  [M1] │   →synthesize[+profile  M2]          └ --remote → VM [M4]
                                          │   →enrich_citations    [M3]            (ensure→start→
                                          │   →slide_book→report                   run→scp→stop)
                                          ▼                                       ↓
                                  work/events/<id>/Report/  ──► --out folder  (+ GCS for LSIC)
```

### Open Questions

| # | Question | Status |
|---|----------|--------|
| OQ1 | Add Semantic Scholar behind the `SearchClient` seam (DOI/venue richness)? | Open — arXiv-only shipped; S2 is a drop-in |
| OQ2 | `--remote` report return: scp (current) vs GCS bucket | Resolved — direct `gcloud scp` |
| OQ3 | tmux-detached remote job (survive laptop disconnect) vs foreground ssh | Open — foreground shipped; tmux is a future enhancement |

### Deliverable / Output Contract

The `--out` folder contains the bundle, each artifact passing its validator: `notes.md`
(`validate_notes`), `slide_captions.md`/`slides.pdf` (`validate_slides`/page>0), `equations.md`
(present or skip-stub), `references.md` (present or skip-stub — NEW, M3).

---

## Repo Layout (shipped)

```
src/
├── adhoc.py             NEW  URL/file→Event · mint id · non-clobber events.json · run_adhoc      [M1]
├── profiles/
│   ├── __init__.py      NEW  Profile dataclass + get_profile (default "briefing")                 [M2]
│   └── lecture.py       NEW  generic template: Lenses · Outline · Field Implications · Outlook     [M2/M2.1]
├── enrich_citations.py  NEW  SearchClient seam (arXiv/Null) · derive_queries · references.{md,json} [M3]
├── remote.py            NEW  gcloud lifecycle (injectable runner): ensure→start→sync→run→scp→stop  [M4]
├── synthesize.py        MOD  profile param · _call_thematic system_prompt · persist thematic.json · **_kwargs
├── main.py              MOD  --source/--out/--profile/--references/--enrich/--remote/--keep-up + dispatch
├── report.py            MOD  dest_dir kwarg · references.md in REPORT_FILES
└── util.py              MOD  STAGE_REFERENCES = "06_references" · retry_transient (pre-existing)
tests/  test_adhoc.py · test_profiles.py · test_enrich_citations.py · test_remote.py  (40 new, fakes-only)
```

---

## TODO milestones — ALL SHIPPED

- [x] **M1 — Ad-hoc local run (`--source/--out`)** `<!-- progress: EASYRUN_M1 (0ce4569) -->`
  Gate met: 16 fakes-only tests (URL→Event, non-clobber/idempotent merge, `--out` copy); suite green.
- [x] **M2 — Selectable profiles** `<!-- progress: EASYRUN_M2 (5a3f634) -->`
  `briefing` reuses unchanged synthesize symbols (byte-identical); `lecture` = generic template
  (domain Expert Lenses + chapters Outline + description-link references). Gate: 25 tests, briefing untouched.
- [x] **M2.1 — Field Implications + Industry Outlook** `<!-- progress: EASYRUN_M2_1 (deb4769) -->`
  Two forward-looking sections (skills/transitions; fading vs thriving), extracted even when implied.
- [x] **M3 — Citation enrichment** `<!-- progress: EASYRUN_M3 (133dd97) -->`
  `enrich_citations.py`: deterministic queries → arXiv behind `SearchClient` → `references.md`.
  Opt-in for pipeline (`--references`), on for `--source`; skip-stub when offline. Gate: 9 tests.
- [x] **M4 — On-demand remote (`--remote`)** `<!-- progress: EASYRUN_M4 (4fefb4a) -->`
  `remote.py`: ensure→start→sync→run→scp-back→**finally auto-stop**; `--keep-up` skips. Gate: 6 tests.

Build order was M1 → M2 → M2.1 → M3 → M4, each its own branch, fakes-only gate green, merged to `main`.

---

## Verification (end-to-end — run when you want to exercise the live paths)

```bash
python -m src.main --source "https://youtu.be/<id>" --profile lecture --out /tmp/rep   # local talk
sed -n '1,40p' /tmp/rep/notes.md        # Summary · Expert Lenses · Outline · … · Field Implications · Outlook
sed -n '1,20p' /tmp/rep/references.md   # arXiv related work
python -m src.main --source "https://youtu.be/<id>" --remote --out /tmp/rep2          # offload to VM, auto-stop
python -m pytest tests/ -q && python -m src.main --selftest                            # 111 green, golden unchanged
```

## Next iteration — design notes (NOT yet built; discussion in progress)

### N1 — Claim Verification (citation purpose B: corroborate predictions)
_Reframes citations from "related arXiv work" to "do the speaker's forward-looking claims hold
up?" — which doubles as a **speaker-credibility signal** (how corroborated are their bets)._

| Knob | Decision (2026-06-11) |
|------|------------------------|
| **Trigger** | predictive claims only — **predictions, forecasts, projections, guesses** (route on claim *type*, which `thematic.json` already separates: `industry_outlook`, `field_implications`, predictive `notable_claims`). NOT every claim. |
| **Source** | ML/Robotics-heavy → **arXiv + Semantic Scholar + other reputable scholarly APIs**; for non-paper predictions, reputable web/analyst sources behind the same `SearchClient` seam. |
| **Query** | **agentic** — spawn a sub-agent per claim to formulate queries, run searches, read results (not a single keyword string). |
| **Surface** | gather **multiple** sources per claim and **compare stances** — do they agree or differ (support / contradict / mixed / no-evidence) → renders as a mini "state of the debate" + a corroboration score. |

### N1-adjacent open discussion (not yet decided)
- **D0 — verbosity:** make Open Questions, Takeaways, Field Implications more substantive (prefer richer *structure* per item over longer prose — see chat).
- **D1 — coverage measurement:** how to quantify "did the briefing miss important detail?" (atomic-claim recall · segment/chapter coverage uniformity · completeness-critic pass · QA-coverage · groundedness rate — see chat).
- **D2 — compute tiering:** where to spend stronger models / test-time compute. Working hypothesis: **synthesize** is the leverage point (already `gemini-2.5-pro`); the bigger lever is a **critique→revise pass** (= D1's critic), not a bigger base model. Perception stages (transcribe/visual) stay on flash.

## Footer

### Known Failures
_From the first live `--source` verification (2026-06-11, Karpathy 2.4 h talk — full bundle produced)._

| Symptom | Root cause | Status |
|---------|-----------|--------|
| `references.md` empty (`CERTIFICATE_VERIFY_FAILED`) | macOS framework Python lacks a CA bundle; urllib couldn't verify arXiv's cert | ✅ Fixed (M3.1) — https + certifi SSL context |
| `references.md` empty even with SSL | `derive_queries` emitted full claim sentences; arXiv `all:` matches terms not phrases | ✅ Fixed (M3.1) — keyword-ify; **residual:** metaphorical claims ("building ghosts") match off-target. LLM query-gen is the upgrade |
| Ingest died on a transient yt-dlp 503/throttle | `ingest._fetch_youtube`/`_fetch_http` have no **whole-command** retry (yt-dlp's internal `--retries` don't cover a fast non-zero exit) | **OPEN** — worked around by staging the file; wrap both in `util.retry_transient`-style retry |
| Transcribe exhausted 5-retry budget on some chunks | Gemini `503 "high demand"` storm + 12-way concurrency saturates the model | Mitigated — `ASR_CONCURRENCY=3` rode it out (per-chunk cache resumes); consider lowering the default under sustained 503s |

### Out of scope (tracked elsewhere)
- `run_corpus.sh` event-drop bug (M-F2 blocker) — OPEN in `CLOUD_BATCH_PLAN.md`.
- General-web search (Tavily/Exa) and Semantic Scholar — drop in behind the `SearchClient` seam.
- tmux-detached remote job (OQ3).

### LLM instructions to reproduce this plan
> Extend LSIC_videos (adapter pattern, no rewrite): `src/adhoc.py` (URL/file→Event + `--source/--out`
> reusing `Event`/`events.json` + `report.assemble_report`); `src/profiles/` (`Profile`, default
> `briefing`=today verbatim, new `lecture` with domain Expert Lenses + chapters Outline + description
> links + Field Implications + Industry Outlook) threaded through `synthesize_full`; post-synthesize
> `src/enrich_citations.py` (arXiv behind a faked `SearchClient`→`references.md`, opt-in for pipeline /
> on for ad-hoc); `src/remote.py` (`--remote`: gcloud ensure→start→sync→run→scp-back→finally auto-stop,
> injectable runner). Five independently-green steps, degrade-to-today, fakes-only tests; LSIC batch
> path untouched.
