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
| M5.5 slide_book artifact | Topical `slides.md` (+ `equations.md`) in `05_briefing/`; per-slide Gemini VLM curates is_informative/topic/commentary/contains_equation; keyword-overlap cluster on topic phrases; filter drops title/agenda/contact/bio/text-only | Alex's 2026-01-29 note: notes.md's 📎 highlights are sparse/disorganized; wants a single continuous image-heavy doc filtered to equations/graphs/diagrams/models/images. Per-slide cache keeps reruns instant. ~$0.05/event for ~40-60 slides. | 2026-05-31 |
| Information Architecture Contract | Mockup at `golden/2026-03-26_event_mockup.md` is the canonical product shape; `validators.py` enforces structure deterministically | Pipeline is correct only when output satisfies the contract — running end-to-end is not the same as producing a verifiable briefing | 2026-05-30 |
| Validation philosophy | Every stage has four gates: **Schema** (pydantic) · **Evidence** (claims resolve to sources) · **Coverage** (required sections present) · **Operational** (cache, cost, retry) | Manual review reserved for subjective quality only; structural correctness must be code-enforced | 2026-05-30 |
| Evidence Object | Universal claim primitive emitted at M4; every claim in M5's notes.md routes through an `evidence_id` with kind, source_id, timestamps, speaker, asset, text, confidence, tags | Prevents fabricated-but-plausible briefing content; makes citations machine-verifiable | 2026-05-30 |
| Hybrid keyframe sampling (M3) | Trigger on scene-change OR every-60s safety OR slide-text delta OR audio cue ("this equation/diagram/figure", "as shown") | Scene-change-only misses subtle slide builds (animated bullets, equation reveals) and long static frames; hybrid is cost-defensible insurance (~+30% VLM calls) | 2026-05-30 |
| Citation grounding (M5) | Every `[mm:ss]` in notes.md must map to an evidence object within ±5s; Claude prompt instructed to omit unsupported citations | Prevents hallucinated citations; pairs with Evidence Object to make the briefing falsifiable | 2026-05-30 |
| Atomic artifact writes | Stages write `<artifact>.tmp` then rename + write `<artifact>.manifest.json` with `status: complete`; cache-skip requires manifest complete AND validator pass AND input/config hash match | "Skip if file exists" lies after a kill -9 mid-write; manifest pattern is robust | 2026-05-30 |
| Validators consolidation | One `src/validators.py` with one function per stage (`validate_notes`, `validate_transcript`, `validate_ingest`, `validate_alignment`) rather than 6 separate modules | Review proposed 6 files; we keep it one to minimize file sprawl while preserving enforcement | 2026-05-30 |

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

## Information Architecture & Validation Contract

The mockup at `golden/2026-03-26_event_mockup.md` is the canonical product
shape. **The pipeline is correct only when generated briefings satisfy this
contract — running end-to-end is not the same as producing a verifiable
briefing.**

### Core principle

> The pipeline produces a verifiable technical briefing, not a loose summary.

Each high-value statement must be backed by at least one **Evidence Object**
derived from a transcript segment, slide caption, source asset, or explicit
metadata. LLM calls synthesize and organize; deterministic validators
decide acceptance.

### Evidence Object

All claims used in the final briefing route through an evidence object,
emitted at M4 alignment alongside `aligned.json`:

```json
{
  "evidence_id": "ev_000123",
  "kind": "transcript|slide|asset|metadata",
  "source_id": "segment_0004|caption_0012|asset_3107",
  "timestamp_start": 272.0,
  "timestamp_end": 294.0,
  "speaker_id": "B",
  "source_asset": "3107-Amphenol Lunar Interconnects.pdf",
  "text": "...",
  "confidence": 0.0,
  "tags": ["constraint", "funding", "trl", "open_question"]
}
```

`evidence_id` is stable across runs (hash of `kind` + `source_id` + start).
Sections in `aligned.json` reference `evidence_id`s rather than embedding
raw segments. M5's per-section Claude prompts pass the relevant evidence;
Claude is instructed to omit any `[mm:ss]` it cannot ground in a passed
`evidence_id`.

### Four validation gates per stage

| Gate | What it checks |
|---|---|
| **Schema** | Artifact matches pydantic model |
| **Evidence** | Claims, citations, timestamps, assets resolve to sources |
| **Coverage** | Required briefing sections + expected content types present |
| **Operational** | Cache, cost, retry, runtime behavior acceptable |

Manual review is reserved for subjective quality only. Structural correctness,
citation coverage, timestamp validity, asset existence, and section
completeness are code-enforced via `src/validators.py`.

### Skip-and-stub rule

Required sections that lack evidence must still appear, with an italic
`*Not applicable to this event — <one-line reason>.*` line. TOC and body
must match exactly.

### No-fabricated-placeholder rule

Production mode (`validate_notes --strict`) rejects unresolved placeholders
(`$X.X`, `~$YY`, `TBD`, "fewer than five" without source). These are allowed
only in `golden/` mockups.

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
│   ├── synthesize.py        ≤180 LOC  — event + paper templates, citation grounding
│   ├── validators.py        ≤200 LOC  — validate_notes / _transcript / _ingest / _alignment
│   ├── contracts.py                   — pydantic models (the seams) + Evidence + ValidationResult
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
- [x] **M2.5** — Steel thread: `validators.py` + thin `synthesize.py` → first end-to-end notes.md <!-- progress: M2.5_STEEL_THREAD -->
- [x] **M2.6** — Retrofit M1+M2: atomic writes + manifest gate + validate_ingest/_transcript <!-- progress: M2.6_RETROFIT -->
- [x] **M3** — Visual + Deck render: **hybrid sampling** (scene + 60s safety + audio cue) + VLM <!-- progress: M3_VISUAL_DECKS -->
- [x] **M4** — Align + **Evidence Object** emission (`aligned.json` + `evidence.json`) <!-- progress: M4_ALIGN -->
- [x] **M5** — Synthesize: per-event briefing with **citation grounding** (every `[mm:ss]` resolves to evidence_id) <!-- progress: M5_SYNTHESIZE -->
- [x] **M5.5** — Slide Book: per-slide VLM curation → topical `slides.md` + `equations.md` <!-- progress: M5.5_SLIDE_BOOK -->
- [ ] **M5b** — Papers: standalone-paper template for reference PDFs (2994, 3148, 3160) <!-- progress: M5B_PAPERS -->
- [ ] **M6** — Hardening: retry/backoff, cost log, resume-from-cache verified, `--dry-run`/`--strict` flags <!-- progress: M6_HARDENING -->

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

#### M2.5 — Steel thread (≤90 min)  ← NEW
- **Deliverable.**
  - `src/validators.py` — `validate_notes(path, *, strict)`, `validate_transcript(path)`. Steel-thread mode allows ungrounded citations; production mode forbids `$X.X`/`~$YY`/`TBD`.
  - `src/synthesize.py` (replace stub) — minimal **single** Claude Sonnet 4.6 call: full transcript in, full notes.md out using the 15-section canonical template + skip-and-stub fallback. (Per-section calls + Evidence-grounded citations come at full M5.)
  - `src/main.py` — `--synthesize --event <id> [--slice N]` and `--validate-notes <path>` flags.
- **Run.**
  - `.venv/bin/python -m src.main --synthesize --event lsic_2026-03-26 --slice 300`
  - `.venv/bin/python -m src.main --validate-notes work/events/lsic_2026-03-26/transcript_slice_300s/notes.md`
- **Pass criteria.**
  1. `notes.md` exists at the slice's workdir.
  2. All 15 canonical sections present in canonical order.
  3. TOC matches body headings exactly (catches the Phase-2-era 🛒 mismatch class).
  4. ≥1 `[mm:ss]` citation in body (steel-thread mode — full grounding deferred to M5).
  5. `validate_notes.py` exits 0 in steel-thread mode (allows placeholders).
  6. `validate_transcript.py` exits 0 on existing `transcript_slice_300s/transcript.json`.
- **Goal.** Prove the seam from transcript → notes.md works structurally BEFORE building M3/M4 polish. Catches integration drift early instead of at full-M5 launch.
- **Cost.** ~$0.04/run (5-min transcript ~1500 input + ~2500 output tokens at Sonnet 4.6 pricing).

#### M2.6 — Retrofit M1+M2: atomic writes + validators (≤45 min)  ← NEW
- **Deliverable.**
  - Add `validate_ingest(workdir)` to `validators.py`.
  - Retrofit `src/ingest.py` to write `<artifact>.tmp` then rename + `manifest.json` with `status: complete`.
  - Retrofit `src/transcribe.py` same atomic-write pattern for `transcript.json`.
  - Update cache-skip in both stages: must require manifest `complete` AND validator pass AND input/config hash match.
  - Add `--validate-ingest --event <id>` and `--validate-transcript --event <id>` flags.
- **Run.** Kill `--ingest` with `kill -9` mid-render of a fresh event; rerun must detect incomplete manifest and redo only that step.
- **Pass criteria.**
  1. Mid-stage kill → rerun completes correctly (no half-written artifact treated as complete).
  2. `validate_ingest` passes: `audio.wav` duration within 0.5s of video, all deck `slide_index.json`/`doc_index.json` present + parse.
  3. `validate_transcript` passes: monotonic, no zero-dur, all `[start, end] ≤ duration_sec`, speakers consistent within chunks, no segment overlap > 0.25s (warn-not-fail).
  4. `--selftest` still passes.

#### M3 — Visual + Deck render (≤90 min) [HYBRID SAMPLING]
- **Deliverable.**
  - Video keyframe extraction with **hybrid sampling** (any-of trigger):
    - Scene change (`pyscenedetect`, threshold 27.0)
    - 60-second safety net (don't miss long static segments)
    - Slide-text delta (visible_text changed significantly from prior keyframe — second-pass after first VLM round)
    - Audio cue (transcript contains "this equation", "this diagram", "as shown", "look at this", "in this figure", etc.)
  - All keyframes phash-deduped at Hamming ≤ 4, downscaled to 1024 px.
  - Gemini VLM returns `{visible_text, description, has_equation, has_diagram}` per kept frame.
  - VLM failure: frame retained with `caption_status: "failed"`, not silently dropped.
  - Decks already rendered in M1 (PPTX/PDF page renders); index slide text + speaker notes for M4 fingerprinting.
- **Run.** `python -m src.main --visual --event lsic_2026-03-26`
- **Pass criteria:**
  1. `captions.json` validates against `Caption` schema.
  2. Each kept frame has a `trigger` tag indicating which hybrid rule fired (scene/safety/text-delta/audio-cue).
  3. Frame count > scene count (hybrid adds safety frames by definition).
  4. Each deck has `slide_index.json` (PPTX) or `doc_index.json` (PDF) with `{slide_n, text, speaker_notes, png_path}`.
  5. validate_visual (new in `validators.py`) passes.

#### M4 — Align + Evidence Object emission (≤90 min) — pure Python, no API
- **Deliverable.**
  - Section cut on silence gap >2.5s OR 450-word cap.
  - Video keyframe attach by time range; orphan reassign to nearest section midpoint.
  - Per-deck TF-IDF fingerprint match for presentation windows; assign each deck the contiguous time range with highest match density. Output `presentations[]` in `aligned.json`.
  - Carry `speaker_id` and `language` per segment into section payload.
  - **NEW: emit `evidence.json`** alongside `aligned.json`. Each Evidence object: stable `evidence_id` (hash of kind + source_id + start), `kind`, `source_id`, timestamps, speaker, source_asset, text, confidence, tags.
  - Sections in `aligned.json` reference `evidence_id`s rather than embedding raw segments.
- **Run.** `python -m src.main --align --event lsic_2026-03-26`
- **Pass criteria:**
  1. `aligned.json` validates against `Section` schema.
  2. `evidence.json` validates: every entry has all required fields + stable `evidence_id`.
  3. Every section's `evidence_id` list resolves to entries in `evidence.json`.
  4. Sum of section durations within 1s of `duration_sec`.
  5. No keyframe assigned to more than one section.
  6. `presentations[]` contains 3 non-overlapping windows for the 2026-03-26 event (Amphenol, Nunez, Yank Tech).
  7. Each presentation window's transcript contains ≥3 distinct slide-text fingerprints from its assigned deck.
  8. validate_alignment (new in `validators.py`) passes.

#### M5 — Synthesize: per-event briefing with citation grounding (≤2 h)
- **Deliverable.**
  - Per-presentation Claude calls (TL;DR + claims + open questions per deck) using assigned video time window + deck text + speaker notes + **relevant `evidence_id`s passed in prompt**.
  - Per-section Claude calls for the thematic sections, with relevant evidence objects passed in.
  - **Per-section prompt instruction: "Only cite `[mm:ss]` if you can ground it in a passed `evidence_id`. If unsure, omit the citation entirely."**
  - 🎯 Through 5 Expert Lenses block (5 roles from `clai/.claude/Behavior/Roles.md`) under Bottom Line.
  - Through Expert Lenses 3-role mini-blocks appended to 🔬, 🛠️, 💰.
  - ❓ Per-Question Role Analysis: one sub-block per 🛠️ question with 2–3 role takes.
  - 🛒 Paying Customers / Demand: 2–3 sentence prose intro + two-layer table with status flags.
  - ⚙️ TRL table assembled from per-presentation TRL fields.
  - Final title + 🎯 Bottom Line + TOC pass.
  - All tables column-aligned per the markdown table alignment rule.
- **Prereq.** Alex writes `golden/M5_concept_checklist.md`.
- **Run.** `python -m src.main --synthesize --event lsic_2026-03-26` (no `--slice`, full event)
- **Pass criteria (revised — 11 gates):**
  1. Output structure matches `golden/2026-03-26_event_mockup.md` section-for-section.
  2. **`validate_notes.py` passes in production mode (`--strict`)** — no placeholders allowed.
  3. ≥1 `[mm:ss]` citation in every populated section.
  4. **Every cited `[mm:ss]` resolves to an `evidence_id` in `evidence.json` within ±5s.**
  5. **No fabricated placeholders (`$X.X`, `~$YY`, `TBD`) in body.**
  6. 🎤 Presentations has exactly 3 sub-sections, named to match the guest decks.
  7. ❓ Per-Question Role Analysis has one sub-block per 🛠️ question; each carries 2–3 role bullets.
  8. 🛒 Paying Customers table populated; status uses only the four allowed flag values.
  9. Every Through Expert Lenses block uses roles traceable to `clai/.claude/Behavior/Roles.md`.
  10. All tables in `notes.md` pass `util.align_table()` round-trip check.
  11. Concept-checklist diff: ≥70% hits against `golden/M5_concept_checklist.md`.

#### M5b — Standalone papers (≤45 min)
- **Deliverable.** 5-section paper template (TL;DR · Problem · Approach · Findings · LSIC fit). Claude call per paper from extracted PDF text. No timestamps, no speakers.
- **Run.** `python -m src.main LSIC_Downloads/ --papers`
- **Pass criteria:**
  1. `work/papers/2994/notes.md`, `work/papers/3148/notes.md`, `work/papers/3160/notes.md` all exist.
  2. Each contains the 5-section structure.
  3. Each TL;DR is ≤3 sentences.

#### M6 — Hardening (≤60 min)
- **Deliverable.**
  - Retry/backoff on `RateLimitError` / `ServiceUnavailable`.
  - Per-run cost log printed at end (already partial via `src/cost.py`).
  - Resume-from-cache verified by `kill -9` mid-stage then rerun.
  - **`--dry-run` flag** — plans the artifact graph + token estimate without API spend.
  - **`--strict` flag** — fails the run if any `validate_*` returns non-zero.
  - `run.jsonl` event log (per-stage start/success/duration/io artifacts/API call telemetry).
- **Run.** `python -m src.main --ingest --synthesize --all` then Ctrl-C mid-event, rerun.
- **Pass criteria:**
  1. All 8 events + 3 papers complete once.
  2. Cost log printed; ≤ $1.00/hour of video.
  3. Rerun after kill skips completed events instantly (<1s each).
  4. `--dry-run` emits cost estimate without making any Gemini/Anthropic call.
  5. `--strict` blocks output when validators fail.

**Total budget:** ~6 h, fits the 6-h window.

---

## Testing Strategy

| Layer | What it catches | When it runs |
|---|---|---|
| Pydantic at every stage seam | schema drift, missing fields | every stage call |
| `--selftest` mode | broken imports / config | M0, after any refactor |
| **`validators.py` (Schema gate)** | artifact matches pydantic | every stage write |
| **`validators.py` (Evidence gate)** | citations/timestamps/assets resolve | M4 + M5 |
| **`validators.py` (Coverage gate)** | required sections + content types present | M2.5 + M5 |
| **`validators.py` (Operational gate)** | cache/cost/retry behavior | M2.6 + M6 |
| Per-stage CLI invocation | stage-local regression | every milestone gate |
| **Mid-stage kill test** | atomic-write + manifest gate | M2.6 + M6 |
| **`--dry-run`** | artifact graph + cost estimate w/o API spend | every real run optional |
| **`--strict`** | production-mode validator (no placeholders) | M5 + M6 |
| Concept-checklist diff | content quality (binary) | M5, M6 |
| Cost log per run | runaway spend | every real run |

`--selftest` extended to call `validate_notes` against the golden mockup as
its third check. No `pytest` yet — slot reserved at `tests/` for when the
test count exceeds 10.

---

## Implementation Outline — What to Code & In What Order

This section bridges the gap between architecture (above) and writing code.
It enumerates **modules, contracts, dependencies, and build sequence** at a
level a future agent can execute against without re-deriving design choices.

### Dependency graph (build bottom-up)

```
                        ┌────────────────┐
                        │  contracts.py  │  pydantic models — the seams
                        │  + Evidence    │  Evidence + ValidationResult added M2.5
                        │  + Validation* │
                        └────────┬───────┘  no deps on other modules
                                 │
            ┌────────────────────┼──────────────┬──────────────┐
            ▼                    ▼              ▼              ▼
       ┌────────────┐  ┌─────────────┐  ┌────────────┐  ┌────────────┐
       │  util.py   │  │ validators  │  │ discover.py│  │ pptx/pdf   │
       │ strip,mmss │  │ _notes      │  │  cluster   │  │ _handler   │
       │ align_tbl  │  │ _transcript │  │  classify  │  │  text+png  │
       └─────┬──────┘  │ _ingest     │  └────────────┘  └─────┬──────┘
             │         │ _alignment  │                        │
             │         │ _visual     │                        │
             │         └──────┬──────┘                        │
             │                │                               │
             ▼                ▼                               ▼
         ┌────────────┐  enforces gates           ┌────────────┐
         │ ingest.py  │◄──schema/evidence/cov.    │ (handlers) │
         │ video→wav  │  + atomic .tmp→rename     │            │
         │ + manifest │  + manifest status=cmplt  │            │
         └──────┬─────┘                           └────────────┘
                │
                ▼
         ┌────────────┐    ┌─────────────────┐
         │transcribe.py│   │   visual.py     │
         │Gemini ASR   │   │ HYBRID sampling │
         │chunking     │   │ scene+60s+text  │
         │diarize+lang │   │ +audio-cue+VLM  │
         └──────┬──────┘   └────────┬────────┘
                │                   │
                └─────────┬─────────┘
                          ▼
                  ┌──────────────┐
                  │  align.py    │  sectioning + TF-IDF
                  │              │  + emits evidence.json
                  └──────┬───────┘  (Evidence Object per claim)
                         ▼
                  ┌──────────────┐
                  │synthesize.py │  per-section Claude calls
                  │  + grounding │  evidence_id-gated citations
                  │  + 5 lenses  │  + table_align on output
                  │  + TRL block │
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │ cost.py      │  per-run token + $ estimator
                  └──────┬───────┘
                         ▼
                   ┌───────────┐
                   │  main.py  │  CLI spine; --selftest, --discover,
                   │           │  --ingest, --transcribe, --visual,
                   │           │  --align, --synthesize, --validate-*,
                   │           │  --dry-run, --strict
                   └───────────┘
```

### Build order

| Step | Module | Builds on | Why now |
|------|----------------|----------------------|---------|
| 1    | `contracts.py` | — | Pydantic models. **M2.5 adds:** `Evidence`, `ValidationIssue`, `ValidationResult`. |
| 2    | `util.py`      | — | `strip_fences()`, `mmss(seconds)`, `align_table(rows)`, `slugify()`. |
| 3    | `validators.py` (M2.5) | contracts | `validate_notes`, `validate_transcript`, `validate_ingest`, `validate_alignment`, `validate_visual`. Returns `ValidationResult` with actionable issues. |
| 4    | `discover.py`  | contracts | LSIC ID clustering + classification. No external APIs. |
| 5    | `pptx_handler.py`, `pdf_handler.py` | contracts | Local extraction (python-pptx + libreoffice + PyMuPDF). |
| 6    | `ingest.py`    | contracts, util, handlers | Per-asset dispatch. **M2.6 retrofits** atomic `.tmp`→rename + manifest. |
| 7    | `transcribe.py`| ingest        | Gemini ASR with chunking + diarization + language. **M2.6 retrofits** atomic write + manifest. |
| 8    | `cost.py` (M5/M6) | — | Token + $ estimator per stage. Feeds `--dry-run` and run summary. |
| 9    | `synthesize.py` (M2.5 thin → M5 full) | transcribe (M2.5); align (M5) | M2.5: single Claude call → notes.md. M5: per-section calls + Evidence-grounded citations + Through 5 Lenses block. |
| 10   | `visual.py`    | ingest, transcribe (for audio-cue trigger) | **Hybrid sampling**: scene + 60s safety + slide-text-delta + audio-cue. Gemini VLM per kept frame. |
| 11   | `align.py`     | transcribe, visual, handlers | Sectioning + TF-IDF deck match. **Emits `evidence.json`** alongside `aligned.json`. |
| 12   | `main.py`      | all above     | CLI flags: `--selftest`, `--discover`, `--ingest`, `--transcribe`, `--synthesize`, `--visual`, `--align`, `--validate-*`, `--dry-run`, `--strict`. |

### Module-by-module: what each file owns

**`contracts.py`** — pydantic v2 BaseModels. No methods, just typed data.
- `Asset` — kind (video / host_deck / presentation / paper / notes), path, sha256, lsic_id, date_in_filename
- `Event` — event_id, date, assets[], video_hash, duration_sec
- `IngestResult` — workdir, audio_path, video_path, fps, width, height
- `Segment` — start, end, text, speaker_id, language
- `Caption` — t, frame_path, visible_text, description, has_equation, has_diagram, **trigger** (scene/safety/text-delta/audio-cue — M3)
- `Presentation` — asset_id, start, end, slides[], match_score
- `Section` — start, end, transcript, keyframes[], speakers, languages, **evidence_ids[]** (M4)
- `TRLRow` — technology, trl, basis, confidence, source_timestamp
- **`Evidence` (M2.5/M4)** — evidence_id, kind, source_id, timestamp_start/end, speaker_id, source_asset, text, confidence, tags[]
- **`ValidationIssue` (M2.5)** — section?, rule, offending?, suggestion?
- **`ValidationResult` (M2.5)** — passed, issues[]
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

1. ~~Scaffold the repo.~~ ✅ M0
2. ~~Lock `contracts.py`.~~ ✅ M0 (Evidence + Validation types appended in M2.5)
3. ~~Build `util.py`.~~ ✅ M0
4. ~~Build `discover.py`.~~ ✅ M1
5. ~~Build handlers.~~ ✅ M1
6. ~~Build `ingest.py`.~~ ✅ M1 (atomic-write retrofit in M2.6)
7. ~~Build `transcribe.py`.~~ ✅ M2 (atomic-write retrofit in M2.6)
8. **M2.5 — Build `validators.py` + thin `synthesize.py` (single Claude call) + `--synthesize`/`--validate-notes` flags.** Steel thread on existing 5-min transcript. Acceptance: notes.md exists, 15 sections in canonical order, `validate_notes.py --strict=false` passes.
9. **M2.6 — Retrofit `ingest.py` + `transcribe.py` with atomic writes + manifests + cache-skip gate.** Acceptance: mid-stage kill→rerun is correct.
10. **M3 — Build `visual.py` with HYBRID sampling.** Scene + 60s safety + slide-text-delta + audio-cue triggers. Gemini VLM per kept frame. Independent of M4.
11. **M4 — Build `align.py` + emit `evidence.json`.** Sectioning + TF-IDF deck match + Evidence Object emission.
12. **M5 — Replace thin `synthesize.py` with full per-section Claude calls + citation grounding.** Evidence-gated `[mm:ss]` citations. `validate_notes.py --strict` enforces production rules.
13. **M5b — Standalone paper template** (PDFs 2994, 3148, 3160).
14. **M6 — Hardening.** Retry/backoff + cost log + `--dry-run` + `--strict` + resume-from-cache verified.

### Cost & rate-limit posture (not yet code, but a design decision)

- Gemini: ASR call per 10-min audio chunk + VLM call per deduplicated keyframe.
- Anthropic: one Claude call per guest presentation + one per thematic section + one final TL;DR/TOC pass. For the 2026-03-26 event that's ~3 + 8 + 1 = 12 Claude calls.
- Implement bounded retry (3 tries, exponential backoff) wrapping each cloud call. No global concurrency tonight; revisit when sync version proves slow.
- Per-event cost log: tokens in/out + estimated $ per provider, printed at end. Target: ≤$1/hour of video.

---

## Known Failures

(empty — populate after first debug session per clai convention)

