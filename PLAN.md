# Implementation Plan — LSIC Event → Briefing Pipeline

Audio-first, **event-shaped** pipeline. Input: a folder of LSIC assets (videos,
PPTX decks, PDFs). Output: one strict-template markdown briefing per event,
plus separate briefings for standalone reference papers, aligned to C'mander
Alex's interests: current state, engineering constraints, funding landscape,
chokepoints.

**An event is a cluster of files that share an LSIC ID range and date.**
Each event has 1 video + 0–N slide decks + 0–N notes PDFs. Audio is the spine.
Decks are first-class: they carry clean slide text + speaker notes and map to
sub-sections per guest presentation inside the event briefing.

**Output mockup:** `golden/2026-03-26_event_mockup.md` shows the shape of the
final briefing for the richest event in the current corpus (3 guest presentations
on dust-tolerant connectors). Approve the mockup before any code is written.

---

## Architecture Decisions

| Decision | Choice | Rationale | Date |
|---|---|---|---|
| Build order | Stage-by-stage finish (not vertical slice) | Strict output contract already known; pydantic seams remove integration risk; avoids double-coding each stage | 2026-05-29 |
| ASR model | `gemini-2.5-flash` | Handles audio + frames; 2.0 line retiring; one vendor for ASR + VLM | 2026-05-29 |
| ASR chunking | 10-min WAV segments, offset added back to absolute time | Keeps each Gemini response within output-token ceiling | 2026-05-29 |
| Diarization | Prompted on Gemini (request `speaker_id` per segment) | 2–3 speakers, low noise → Gemini suffices; pyannote is the GPU-box upgrade | 2026-05-29 |
| Language | Auto-detect per segment, transcribe in source, ISO code in payload | Multi-language is in-scope; translation deferred | 2026-05-29 |
| Synth model | `claude-sonnet-4-6`, per-section call | Crash-safe; small prompts keep quality high; per-section resume on failure | 2026-05-29 |
| Synth template | Strict 9-section, emoji-rich, timestamp-cited | Alex's interests are stable; reproducibility > free-form | 2026-05-29 |
| Citations | `[mm:ss]` inlined per bullet/row | Cheap now, painful to retrofit | 2026-05-29 |
| Equations | LaTeX `$..$` / `$$..$$` in markdown | Standard render path | 2026-05-29 |
| Visual sampling | Scene-change only (`pyscenedetect`, threshold 27.0) | Cost knob; audio is primary | 2026-05-29 |
| Frame dedup | Perceptual hash, Hamming ≤ 4 | Kills duplicate slide VLM calls | 2026-05-29 |
| Frame fidelity | Downscale to 1024 px longest side, JPEG q=85 | Slide text still legible; halves VLM cost | 2026-05-29 |
| VLM schema | `{visible_text, description, has_equation, has_diagram}` | Feeds synth template (📐, 📎 sections) directly | 2026-05-29 |
| Identity | sha256(video)[:12] → workdir | Rename-safe; collision-proof | 2026-05-29 |
| Stage contract | Each stage reads previous JSON, writes own JSON, skips if artifact exists | Idempotency + resume after crash | 2026-05-29 |
| Schemas | `pydantic` models in `contracts.py` | Catches drift at seams instead of in stage 4 | 2026-05-29 |
| Concurrency | Sync CLI for now, async later | Debuggable; matches "step through myself" rhythm | 2026-05-29 |
| Secrets | `.env` + `python-dotenv` | Conventional, gitignored | 2026-05-29 |
| Failure mode | Crash loud, leave partial artifacts | Matches debuggable preference; cache makes rerun cheap | 2026-05-29 |
| Validation | Hand-written reference notes + concept checklist diff | Binary, not vibes | 2026-05-29 |
| GPU-box swap path | `Transcriber` and `Describer` interfaces hide vendor calls | One-file replacement when WhisperX/local VLM lands | 2026-05-29 |
| Output unit | One briefing per **event**; standalone papers get their own briefing | Matches the data shape (LSIC ID ranges cluster files into events) | 2026-05-29 |
| Event grouping | Cluster by LSIC ID proximity + `YYYYMMDD` in filename | Avoids forcing user to reorganize 26 flat files | 2026-05-29 |
| Asset classification | Sniff by extension + filename heuristics (`SPCAslides`→host_deck, `Recording`→video, other→presentation/paper) | Filename convention is consistent across LSIC corpus | 2026-05-29 |
| Host SPCA deck | Folds into event header only, no full sub-section | Admin/intro content, not a presentation | 2026-05-29 |
| Multi-presentation alignment | Fingerprint-match each deck's slide text vs ASR transcript; assign best-fit time window | Avoids guessing where presentations start; deterministic | 2026-05-29 |
| PPTX handling | `python-pptx` for text + speaker notes; `libreoffice --headless` to render slides → PNG | Text-extract is fast & free; render only when VLM is needed | 2026-05-29 |
| PDF handling | `pypdf` for text; `pdf2image` for page renders when needed | Handles both slide-PDFs and paper-PDFs uniformly | 2026-05-29 |
| Standalone papers | Separate 5-section template (TL;DR / Problem / Approach / Findings / LSIC fit) | Different artifact class than meeting briefings | 2026-05-29 |
| Deduplication | sha256 content hash at ingest; dupes collapse to same workdir | Catches the `3178 ×2` case automatically | 2026-05-29 |
| Template addition: ⚙️ TRL | Per-technology TRL table (NASA 1–9), `claimed` vs `inferred` confidence flag, inserted between 🚧 Chokepoints and 📐 Equations | Anchor: Preferences §4 — "theory → implementation bridge"; matches Alex's lab-vs-flight distinction filter | 2026-05-29 |
| Template addition: 🎯 Through 5 Expert Lenses | Sub-block under 🎯 Bottom Line; 5 roles picked from `clai/.claude/Behavior/Roles.md` based on event content; one bullet each | Anchor: CLAUDE.md hard rule — "pick the 5 most relevant expert roles for the task at hand" | 2026-05-29 |
| Markdown table alignment | All tables in `notes.md` use space-padded columns aligned to the widest entry (header, divider, and cells); divider row uses matching-width `---` runs | Alex edits in IDE — raw markdown legibility matters; aligned tables are scannable, ragged tables are not | 2026-05-29 |
| Template addition: per-section 3-role mini-lens | "Through Expert Lenses" italic block (3 roles, one sentence each) appended to 🔬 What's being done, 🛠️ Engineering questions, 💰 Funding landscape | Extends G pattern; Alex wants role perspectives across three thematic sections, not only Bottom Line | 2026-05-29 |
| Template addition: ❓ Per-Question Role Analysis | New section after 🛠️; each engineering question gets a bolded restatement + 2–3 role bullets from `clai/.claude/Behavior/Roles.md` | Anchor: Alex's "particular attention to the system engineering question"; CLAUDE.md 5-role rule applied at question scope rather than event scope | 2026-05-29 |
| Template addition: 🛒 Paying Customers / Demand | New section after 💰; 2–3 sentence prose intro + two-layer table (`Active funding` / `Active PO` / `Open RFP/RFI` / `Aspirational` status flags) | Anchor: Alex's "customers who are willing to pay for it right now" — surfaces demand-side procurement reality, distinct from supply-side grant funding | 2026-05-29 |
| PDF rendering library | `PyMuPDF` (fitz) | `pdf2image`+poppler stalled on macOS 13 (Tier 3, source build of ~50 deps including cmake). PyMuPDF is pure-pip, zero system deps, ships text extract + PNG render in one library | 2026-05-29 |
| Hidden-slide handling in PPTX | Use `min(python-pptx slide count, libreoffice page count)` and log mismatch | `python-pptx` counts hidden slides; libreoffice exports only visible. SPCAslides decks routinely have a hidden tail-slide | 2026-05-29 |
| ASR backend | Gemini 2.5 Flash via `google-genai`; behind `Transcriber` protocol | Cheapest (~$0.16/hr), single API for M2+M3, decent diarization on 2-3 clean speakers; protocol enables one-file swap to Deepgram/WhisperX later | 2026-05-30 |
| Tail-clamp segment dropping | Drop segments where `end <= start` after timestamp clamp | Gemini occasionally hallucinates segments past the clip boundary; clamping flattens them to zero-duration which carry no signal | 2026-05-30 |

---

## The Output Contract

**Authoritative reference:** `golden/2026-03-26_event_mockup.md`. PLAN.md
summarizes the shape; the mockup is the literal target every M5 output is
diffed against.

Every event run produces `work/events/<event_id>/notes.md` in this section
order:

```
🎯 Bottom Line for C'mander Alex
  └─ Through 5 Expert Lenses          ← 5 roles from clai/.claude/Behavior/Roles.md
🗂️ Contents
🎤 Presentations (N)                  ← one sub-section per guest deck
                                         (TL;DR / Key claims / Open questions raised)
🔬 What's being done right now
  └─ Through Expert Lenses (3 roles)
🛠️ Engineering system-design questions
  └─ Through Expert Lenses (3 roles)
❓ Per-Question Role Analysis        ← each 🛠️ question, 2–3 role takes
⚠️ Main engineering constraints
💰 Funding landscape
  └─ Through Expert Lenses (3 roles)
🛒 Paying Customers / Demand         ← prose + two-layer procurement table
🚧 Chokepoints
⚙️ Technology Readiness & Maturity   ← TRL per technology, claimed vs inferred
📐 Key equations & models
🗣️ Speakers
🔖 Citations & references mentioned
📎 Slide highlights
```

**Citation rule.** Every populated section carries at least one `[mm:ss]`
citation back to the source video.

**Table formatting rule.** Every markdown table in `notes.md` MUST be
column-aligned: each column's cells, header, and divider padded with spaces
to match the widest entry in that column. The synthesizer renders tables
this way before writing the file. Ragged tables are a regression — they
will fail M5 acceptance.

**Standalone paper template (M5b) — separate, simpler:**
`TL;DR / Problem / Approach / Findings / How it fits LSIC` — no timestamps,
no speakers.

---

## Repo Layout (greenfield, to create)

```
LSIC_videos/
├── PLAN.md                  this file
├── Progress/                handoff notes, one per milestone TODO
│   └── M<N>_<NAME>.md
├── src/
│   ├── discover.py          ≤80  LOC  — event grouping, asset classification
│   ├── ingest.py            ≤120 LOC  — per-asset dispatch (video/pptx/pdf)
│   ├── pptx_handler.py      ≤100 LOC  — text + notes + libreoffice render
│   ├── pdf_handler.py       ≤80  LOC  — text + page render
│   ├── transcribe.py        ≤150 LOC  — audio work (chunking, diarization, lang)
│   ├── visual.py            ≤120 LOC  — video frame scene-detect + VLM
│   ├── align.py             ≤120 LOC  — sectioning + per-deck fingerprint match
│   ├── synthesize.py        ≤180 LOC  — event + paper templates
│   ├── contracts.py                   — pydantic models (the seams)
│   ├── util.py                        — strip_fences, mm:ss formatter
│   └── main.py                        — spine, one event at a time
├── LSIC_Downloads/          source assets (flat, gitignored)
├── golden/                  reference outputs for diffs
│   └── 2026-03-26_event_mockup.md   ← approved-shape mockup
├── work/                    artifact cache (gitignored)
│   ├── events/<event_id>/   per-event artifacts
│   │   ├── manifest.json    event grouping result
│   │   ├── audio.wav        from video ingest
│   │   ├── transcript.json
│   │   ├── decks/<asset_id>/  per-deck text + slide images
│   │   ├── captions.json    video-frame VLM output
│   │   ├── aligned.json     sectioning + presentation windows
│   │   └── notes.md         final output
│   └── papers/<asset_id>/   per-paper artifacts
│       └── notes.md
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## Test Asset

Single fixture for all milestones: `LSIC_Downloads/525-Video from ISRU Monthly Meeting - 2020 July.mp4`
- **58:41** (3520.96 s), 1828×944 @ 25 fps, AAC 32 kHz **mono**, h264, ~128 MB
- Topic: LSIC Lunar Surface Innovation Consortium ISRU monthly meeting, July 2020
- Multi-speaker panel discussion, low noise, English

Early milestones (M1–M4) slice with `ffmpeg`:
```
ffmpeg -ss 0    -t 60   -i "<src>" -c copy work/slice_60s.mp4
ffmpeg -ss 600  -t 300  -i "<src>" -c copy work/slice_5min.mp4
ffmpeg -ss 0    -t 900  -i "<src>" -c copy work/slice_15min.mp4
```
M5 and M6 run on the full file.

**Format reference** (not content reference): `LSIC_Downloads/650-Notes from ISRU
Monthly Meeting - 2020 August.pdf` — different meeting, but shows the LSIC
community's native notes style (bold topic heading + flat bullets, no timestamps,
no emojis). Useful as a stylistic data point only; not used for acceptance diff.

## Open Questions

- **Template style** — three options, Alex picks one before M5:
  1. **Personal briefing** (current plan): 9-section emoji-rich, with `[mm:ss]` citations, LaTeX equations
  2. **LSIC-native**: flat bulleted minutes matching the August PDF format — no emojis, no timestamps
  3. **Hybrid**: Alex's 9 sections, no emojis, keep timestamps — formal-looking briefing
- **Concept checklist for M5 acceptance** — Alex watches the July video once and writes 5–10 must-be-present concept bullets to `golden/M5_concept_checklist.md`. The diff against that is M5's binary gate. ~15 min of his time.
- **Cost ceiling for M6** — default suggestion: $1.00 per hour of video. Confirm or override.
- **Speaker labels** — generic A/B/C, or attempt name extraction from intro segments? Default A/B/C unless overridden.
- **Equation extraction source** — ASR rarely carries equations cleanly; VLM is the better source. ISRU meeting unlikely to have equations on slides anyway → low priority for this fixture. Confirm equations come only from slides.

---

## TODO

Stage-by-stage finish. Each milestone has its own fixture and binary pass gate.
Branch + Progress file created when work starts on each.

- [x] **M0** — Setup, contracts, .env <!-- progress: M0_SETUP -->
- [x] **M1** — Discover + Ingest: event grouping + per-asset dispatch (video/pptx/pdf) <!-- progress: M1_DISCOVER_INGEST -->
- [x] **M2** — Transcribe: chunking, diarization, language, clamping <!-- progress: M2_TRANSCRIBE -->
- [ ] **M3** — Visual + Deck render: scene-detect + VLM on frames, PPTX/PDF render to PNG <!-- progress: M3_VISUAL_DECKS -->
- [ ] **M4** — Align: sectioning + per-deck fingerprint-match for presentation windows <!-- progress: M4_ALIGN -->
- [ ] **M5** — Synthesize: per-event briefing with per-presentation sub-sections <!-- progress: M5_SYNTHESIZE -->
- [ ] **M5b** — Papers: standalone-paper template for reference PDFs (2994, 3148, 3160) <!-- progress: M5B_PAPERS -->
- [ ] **M6** — Hardening: retry/backoff, cost log, resume-from-cache verified <!-- progress: M6_HARDENING -->

### Per-milestone deliverables, runs, and pass gates

#### M0 — Setup & contracts (≤45 min)
- **Deliverable.** Venv, `requirements.txt`, `.env` from `.env.example`, `contracts.py` (`IngestResult`, `Segment`, `Caption`, `Section`), empty stage files that round-trip JSON through the models.
- **Run.** `python -m src.main --selftest`
- **Pass.** Smoke test imports all modules, validates a fixture JSON against every pydantic model, exits 0.

**Fixture strategy.** All milestones target the **2026-03-26 event** (LSIC IDs
3105–3109) as the gold case — it's the richest event in the corpus (1 video + host
deck + 3 guest presentations) and matches the mockup at `golden/2026-03-26_event_mockup.md`.
Early milestones run on ffmpeg-sliced subsets of the video; later milestones
process the full event.

#### M1 — Discover + Ingest (≤90 min)
- **Deliverable.**
  - `discover.py` clusters `LSIC_Downloads/*` into events by LSIC ID proximity (≤10 apart) + date-in-filename. Outputs `events.json` manifest.
  - Asset classifier: `*SPCAslides*` → `host_deck`, `*Recording*.mp4` → `video`, `*notes*.pdf` → `notes`, isolated PDFs not near a video → `paper`, all other PDFs/PPTX in an event → `presentation`.
  - Per-asset ingest: video → ffmpeg audio + ffprobe metadata; PPTX → `python-pptx` text + speaker notes + `libreoffice --headless` PNG render per slide; PDF → `pypdf` text + `pdf2image` page render.
  - sha256 hash per asset, dedupes the `3178 ×2` case.
- **Run.** `python -m src.discover LSIC_Downloads/ && python -m src.ingest LSIC_Downloads/`
- **Pass criteria:**
  1. `events.json` clusters the 26 files into the 8 events from the inventory table; the 3 standalone papers (2994, 3148, 3160) appear in a `papers` list.
  2. The 2026-03-26 event manifest lists exactly: 1 video + 1 host_deck + 3 presentations.
  3. `3178 ×2` resolves to one workdir.
  4. PPTX → PNG slide renders exist for every guest deck in the event.

#### M2 — Transcribe (≤2 h) — the heart of the build
- **Deliverable.** 10-min WAV chunking with offset math; Gemini ASR with diarization prompt (`speaker_id`); per-segment ISO language code; timestamp clamping; sorted segments.
- **Run.** Slice the 2026-03-26 video to 5 min, then `python -m src.transcribe work/slice_5min.mp4`
- **Pass criteria:**
  1. `transcript.json` validates against `Segment` schema.
  2. `speaker_id` populated; manual eyeball ≥80% correct on the multi-voice slice.
  3. `language` field populated (`en` expected throughout).
  4. Last segment's `end ≤ duration_sec` (no hallucinated tail).

#### M3 — Visual + Deck render (≤90 min)
- **Deliverable.**
  - Video: scene-change keyframes only, phash dedup at Hamming ≤ 4, downscale to 1024 px, Gemini VLM returns `{visible_text, description, has_equation, has_diagram}`, skip+log on failure.
  - Decks: PPTX/PDF page renders already in `work/events/<id>/decks/<asset_id>/`; index slide text + speaker notes for fingerprinting.
- **Run.** `python -m src.visual work/events/lsic_2026-03-26/`
- **Pass criteria:**
  1. Frame count ≤ scene count for video.
  2. `captions.json` validates against `Caption` schema.
  3. Eyeball: distinct video frames; no near-duplicates.
  4. Each deck has a `slide_index.json` with `{slide_n, text, speaker_notes, png_path}` per slide.

#### M4 — Align (≤90 min) — pure Python, no API
- **Deliverable.**
  - Section cut on silence gap >2.5 s OR 450-word cap.
  - Video keyframe attach by time range; orphan reassign to nearest section midpoint.
  - **New: per-deck fingerprint match.** For each guest deck, compute TF-IDF over slide text vs ASR transcript windows; assign each deck the contiguous time range with highest match density. Output `presentations[]` in `aligned.json`.
  - Carry `speaker_id` and `language` per segment into section payload.
- **Run.** `python -m src.align work/events/lsic_2026-03-26/`
- **Pass criteria:**
  1. `aligned.json` validates against `Section` schema.
  2. Every section has `start, end, transcript, keyframes, speakers, languages`.
  3. `presentations[]` contains 3 non-overlapping windows for the 2026-03-26 event (Amphenol, Nunez, Yank Tech).
  4. Each presentation window's transcript contains ≥3 distinct slide-text fingerprints from its assigned deck.

#### M5 — Synthesize: per-event briefing (≤2 h)
- **Deliverable.**
  - Per-presentation Claude calls (TL;DR + claims + open questions per deck) using assigned video time window + deck text + speaker notes.
  - Per-section Claude calls over the full event for every thematic section in the Output Contract.
  - 🎯 Through 5 Expert Lenses block (5 roles from `clai/.claude/Behavior/Roles.md`) under Bottom Line.
  - **Through Expert Lenses 3-role mini-blocks** appended to 🔬 What's being done, 🛠️ Engineering questions, 💰 Funding landscape.
  - **❓ Per-Question Role Analysis** section: one sub-block per 🛠️ question with 2–3 role takes.
  - **🛒 Paying Customers / Demand** section: 2–3 sentence prose intro + two-layer table with status flags (`Active funding` / `Active PO` / `Open RFP/RFI` / `Aspirational`).
  - ⚙️ TRL table assembled from per-presentation TRL fields.
  - Final title + 🎯 Bottom Line + TOC pass.
  - `[mm:ss]` citation inlining; LaTeX equations if any.
  - **All tables column-aligned** per the markdown table alignment rule.
- **Prereq.** Alex writes `golden/M5_concept_checklist.md` after one watch-through of the 2026-03-26 video.
- **Run.** `python -m src.main LSIC_Downloads/ --event lsic_2026-03-26`
- **Pass criteria:**
  1. Output structure matches `golden/2026-03-26_event_mockup.md` section-for-section.
  2. ≥1 `[mm:ss]` citation in every populated section.
  3. 🎤 Presentations has exactly 3 sub-sections, named to match the guest decks.
  4. ❓ Per-Question Role Analysis has one sub-block per 🛠️ question; each sub-block carries 2–3 role bullets.
  5. 🛒 Paying Customers table populated; status column uses only the four allowed flag values.
  6. Every Through Expert Lenses block (Bottom Line 5-role + three 3-role mini-blocks) uses roles traceable to `clai/.claude/Behavior/Roles.md`.
  7. All tables in `notes.md` pass `util.align_table()`'s round-trip check (column widths match header divider).
  8. Concept-checklist diff: ≥70% hits against `golden/M5_concept_checklist.md`.

#### M5b — Standalone papers (≤45 min)
- **Deliverable.** 5-section paper template (TL;DR · Problem · Approach · Findings · LSIC fit). Claude call per paper from extracted PDF text. No timestamps, no speakers.
- **Run.** `python -m src.main LSIC_Downloads/ --papers`
- **Pass criteria:**
  1. `work/papers/2994/notes.md`, `work/papers/3148/notes.md`, `work/papers/3160/notes.md` all exist.
  2. Each contains the 5-section structure.
  3. Each TL;DR is ≤3 sentences.

#### M6 — Hardening (≤60 min)
- **Deliverable.** Retry/backoff on `RateLimitError` / `ServiceUnavailable`; per-run cost log printed at end; resume-from-cache verified by `kill -9` mid-stage 3 then rerun. Full-corpus run.
- **Run.** `python -m src.main LSIC_Downloads/ --all` then Ctrl-C mid-event, rerun.
- **Pass criteria:**
  1. All 8 events + 3 papers complete once.
  2. Cost log printed; ≤ $1.00/hour of video.
  3. Rerun after kill skips completed events instantly (<1 s each).

**Total budget:** ~6 h, fits the 6-h window.

---

## Testing Strategy

| Layer | What it catches | When it runs |
|---|---|---|
| Pydantic at every stage seam | schema drift, missing fields | every stage call |
| `--selftest` mode | broken imports / config | M0, after any refactor |
| Per-stage CLI invocation | stage-local regression | every milestone gate |
| Concept-checklist diff | content quality (binary) | M5, M6 |
| Cache-skip after kill | idempotency / resumability | M6 only |
| Cost log per run | runaway spend | every real run |

No `pytest` tonight. Slot reserved at `tests/` for later.

---

## Implementation Outline — What to Code & In What Order

This section bridges the gap between architecture (above) and writing code.
It enumerates **modules, contracts, dependencies, and build sequence** at a
level a future agent can execute against without re-deriving design choices.

### Dependency graph (build bottom-up)

```
                        ┌────────────────┐
                        │  contracts.py  │  pydantic models — the seams
                        └────────┬───────┘  no deps on other modules
                                 │
                  ┌──────────────┼──────────────┐
                  ▼              ▼              ▼
         ┌─────────────┐  ┌────────────┐  ┌────────────┐
         │   util.py   │  │ discover.py│  │ pptx_handler│
         │ strip_fences│  │  cluster   │  │ pdf_handler │
         │ mmss_fmt    │  │  classify  │  │  text+png   │
         │ table_align │  └────────────┘  └─────┬──────┘
         └──────┬──────┘                        │
                │                               │
                ▼                               ▼
         ┌────────────┐                  ┌────────────┐
         │ ingest.py  │◄─────────────────│ (consumes  │
         │ video→wav  │                  │  per-asset │
         │ + dispatch │                  │  handlers) │
         └──────┬─────┘                  └────────────┘
                │
                ▼
         ┌────────────┐    ┌─────────────────┐
         │transcribe.py│   │   visual.py     │
         │Gemini ASR   │   │ scene-detect    │
         │chunking     │   │ + Gemini VLM    │
         │diarize+lang │   │ frame keyframes │
         └──────┬──────┘   └────────┬────────┘
                │                   │
                └─────────┬─────────┘
                          ▼
                  ┌──────────────┐
                  │  align.py    │  sectioning + per-deck
                  │              │  TF-IDF fingerprint match
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │synthesize.py │  per-presentation calls
                  │  + paper tpl │  + per-section calls
                  │  + 5 lenses  │  + table_align on output
                  │  + TRL block │
                  └──────┬───────┘
                         ▼
                   ┌───────────┐
                   │  main.py  │  CLI spine; --selftest, --event, --papers, --all
                   └───────────┘
```

### Build order

| Step | Module | Builds on | Why now |
|------|----------------|----------------------|---------|
| 1    | `contracts.py` | — | Defines `IngestResult`, `Asset`, `Event`, `Segment`, `Caption`, `Section`, `Presentation`, `TRLRow`. Lock these before any stage code. |
| 2    | `util.py`      | — | `strip_fences()`, `mmss(seconds)`, `align_table(rows)` — these are tiny and unblock everything downstream. |
| 3    | `discover.py`  | contracts | Reads `LSIC_Downloads/`, clusters by LSIC ID range + `YYYYMMDD` in filename, classifies via filename heuristics. Outputs `events.json`. No external APIs. |
| 4    | `pptx_handler.py`, `pdf_handler.py` | contracts | Pure local extraction. `python-pptx` for text + speaker notes; `libreoffice --headless` for slide PNG; `pypdf` + `pdf2image` for PDFs. Cached by file hash. |
| 5    | `ingest.py`    | contracts, util, handlers | Per-asset dispatch: video → ffmpeg WAV + ffprobe metadata; pptx/pdf → call handlers. Writes `work/events/<id>/manifest.json`. |
| 6    | `transcribe.py`| ingest        | First cloud call. Gemini 2.5 Flash with 10-min chunking, diarization prompt, language tagging, timestamp clamping. |
| 7    | `visual.py`    | ingest        | Scene-detect on video, phash dedup, downscale to 1024 px, Gemini VLM. Independent of transcribe — can be built in parallel. |
| 8    | `align.py`     | transcribe, visual, handlers | Pure Python. Sectioning + TF-IDF fingerprint match of each guest deck against transcript windows. |
| 9    | `synthesize.py`| align         | Claude per-presentation + per-section calls. Emits column-aligned tables via `util.align_table()`. Generates 5-Role Lens block from `clai/.claude/Behavior/Roles.md`. |
| 10   | `main.py`      | all above     | CLI entry: `--selftest`, `--event <id>`, `--papers`, `--all`. Thin spine; calls each stage in order with check-then-skip. |

### Module-by-module: what each file owns

**`contracts.py`** — pydantic v2 BaseModels. No methods, just typed data.
- `Asset` — kind (video / host_deck / presentation / paper / notes), path, sha256, lsic_id, date_in_filename
- `Event` — event_id, date, assets[], video_hash, duration_sec
- `IngestResult` — workdir, audio_path, video_path, fps, width, height
- `Segment` — start, end, text, speaker_id, language
- `Caption` — t, frame_path, visible_text, description, has_equation, has_diagram
- `Presentation` — asset_id, start, end, slides[], match_score
- `Section` — start, end, transcript, keyframes[], speakers, languages
- `TRLRow` — technology, trl, basis, confidence, source_timestamp
- `Briefing` — frontmatter + every section as a pydantic model so the markdown writer is data-driven

**`util.py`**
- `strip_fences(s) -> str` — drops markdown fences around LLM JSON
- `mmss(seconds: float) -> str` — `[mm:ss]` citation formatter
- `align_table(rows: list[list[str]]) -> str` — given rows including header, returns space-padded markdown table (column widths = max cell width per column)
- `slugify(name: str) -> str` — for event_id and asset_id generation

**`discover.py`**
- `discover(folder: Path) -> list[Event]` — scans `LSIC_Downloads/`, clusters by LSIC ID proximity (≤10 apart) AND date-in-filename. Classifies via filename rules: `*SPCAslides*` → host_deck, `*Recording*.mp4` → video, isolated PDFs not near a video → paper, else → presentation.
- Writes `work/events.json`

**`pptx_handler.py`**
- `extract(path: Path, out_dir: Path) -> DeckIndex` — `python-pptx` for slide text + speaker notes; subprocess `libreoffice --headless --convert-to pdf` then `pdf2image` → per-slide PNG. Idempotent via output cache.

**`pdf_handler.py`**
- `extract(path: Path, out_dir: Path) -> DocIndex` — `pypdf` text per page; `pdf2image` per-page PNG. Handles both slide-decks and papers.

**`ingest.py`**
- `ingest_event(event: Event) -> IngestResult` — for the video: ffprobe metadata, ffmpeg → 16 kHz mono WAV; for pptx/pdf assets: dispatch to handlers. Manifest at `work/events/<id>/manifest.json`.

**`transcribe.py`**
- `transcribe(job: IngestResult) -> list[Segment]` — split audio into 10-min WAV chunks via ffmpeg; per chunk Gemini ASR with prompt asking for `{start, end, text, speaker_id, language}`; offset timestamps back to absolute time; clamp to duration; sort.
- Implements `Transcriber` protocol (so WhisperX swap on GPU box is one file).

**`visual.py`**
- `extract_visual(job: IngestResult) -> list[Caption]` — `pyscenedetect` for keyframes; cv2 frame grab; PIL downscale to 1024 px longest side; phash dedup at Hamming ≤ 4; Gemini VLM with prompt asking for `{visible_text, description, has_equation, has_diagram}`.
- Implements `Describer` protocol.

**`align.py`**
- `align(event, segments, captions, deck_indexes) -> list[Section]` — section cut on silence gap >2.5 s OR 450-word cap; keyframe attach by time range; orphan reassign.
- `match_presentations(segments, deck_indexes) -> list[Presentation]` — TF-IDF over each deck's slide text vs sliding-window transcript chunks; pick max-density contiguous window per deck; assert windows don't overlap (or warn).

**`synthesize.py`**
- `synthesize(event, sections, presentations, deck_indexes) -> str` — per-presentation Claude calls → TL;DR + claims + open questions; per-section Claude calls for the 8 thematic sections; final 🎯 Bottom Line + Through 5 Expert Lenses block (role picker reads `clai/.claude/Behavior/Roles.md`); ⚙️ TRL table assembled from per-presentation TRL fields claude returns.
- Renders all tables via `util.align_table()` before writing.
- Standalone-paper path: `synthesize_paper(asset, doc_index) -> str` with the 5-section template.

**`main.py`**
- `--selftest` runs M0 smoke test (import + pydantic round-trip).
- `--event <id>` runs one event end-to-end.
- `--papers` runs all standalone papers.
- `--all` runs every event + every paper.
- Stages are check-then-skip on artifact existence. Cost log per run.

### Contract sketch — keys that lock the inter-module API

```python
class Asset(BaseModel):
    kind: Literal["video", "host_deck", "presentation", "paper", "notes"]
    path: Path
    sha256: str
    lsic_id: int           # parsed from filename prefix
    date_in_filename: date | None

class Event(BaseModel):
    event_id: str          # e.g. "lsic_2026-03-26"
    date: date
    assets: list[Asset]
    duration_sec: float | None  # only when video present

class Briefing(BaseModel):
    frontmatter: dict
    bottom_line: str
    expert_lenses: list[Lens]              # G — empty list never; always 5
    presentations: list[PresentationBlock]
    whats_being_done: list[CitedBullet]
    eng_questions: list[CitedBullet]
    constraints: list[CitedBullet]
    funding: FundingTable
    chokepoints: ChokepointsTable
    trl: TRLTable                          # D — may have just the facility row
    equations: list[Equation] | None       # None → fallback line
    speakers: list[Speaker]
    citations: list[str]
    slide_highlights: list[SlideHighlight]
```

### External dependencies

```
google-genai>=0.5         # Gemini 2.5 Flash ASR + VLM
anthropic>=0.40           # Claude Sonnet 4.6 synthesis
python-pptx>=1.0          # PPTX text + speaker notes
pypdf>=4.0                # PDF text extraction
pdf2image>=1.17           # PDF + (via libreoffice) PPTX → PNG
scenedetect>=0.6          # video scene-change detection
opencv-python>=4.10       # frame grab
imagehash>=4.3            # perceptual hash dedup
Pillow>=10.0              # downscale + JPEG encode
pydantic>=2.7             # contracts
python-dotenv>=1.0        # .env loader
```
System binaries: `ffmpeg`, `ffprobe`, `libreoffice` (for PPTX → PDF conversion).

### Implementation sequence — concrete order to follow

1. **Scaffold the repo.** Create the directory layout from "Repo Layout" above. Empty stubs for every module. Write `requirements.txt` + `.env.example` + `.gitignore`.
2. **Lock `contracts.py`.** Write every pydantic model with explicit fields. No code outside contracts compiles until these are stable.
3. **Build `util.py`.** Three tiny functions. Unit-test `align_table()` against the mockup's three tables byte-for-byte — that's its acceptance gate.
4. **Build `discover.py`.** Run against `LSIC_Downloads/`. Pass: produces the 8 events + 3 papers from the inventory table. No cloud calls.
5. **Build handlers (`pptx_handler.py`, `pdf_handler.py`).** Run against one event's decks. Pass: each deck has `slide_index.json` + per-slide PNG.
6. **Build `ingest.py`.** Run against the 2026-03-26 event. Pass: `manifest.json` exists, `audio.wav` is 16 kHz mono.
7. **Build `transcribe.py`.** This is M2 — the heart of the build. Pass criteria already specified per milestone.
8. **Build `visual.py`.** Independent of transcribe — can be parallelized.
9. **Build `align.py`.** Includes the TF-IDF fingerprint matcher for presentation windows.
10. **Build `synthesize.py`.** Last. Per-presentation Claude calls + per-section Claude calls + 5-Lens prompt + TRL prompt + `align_table()` on every emitted table. Diff result against `golden/2026-03-26_event_mockup.md`.
11. **Build `main.py`.** Thin CLI; sequencing logic only.
12. **Hardening (M6).** Retry/backoff wrappers around cloud calls; cost log; verify cache-skip after `kill -9` mid-stage.

### Cost & rate-limit posture (not yet code, but a design decision)

- Gemini: ASR call per 10-min audio chunk + VLM call per deduplicated keyframe.
- Anthropic: one Claude call per guest presentation + one per thematic section + one final TL;DR/TOC pass. For the 2026-03-26 event that's ~3 + 8 + 1 = 12 Claude calls.
- Implement bounded retry (3 tries, exponential backoff) wrapping each cloud call. No global concurrency tonight; revisit when sync version proves slow.
- Per-event cost log: tokens in/out + estimated $ per provider, printed at end. Target: ≤$1/hour of video.

---

## Known Failures

(empty — populate after first debug session per clai convention)
