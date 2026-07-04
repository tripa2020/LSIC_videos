# LSIC_videos — Talk → Briefing Pipeline

Audio-first, event-shaped Python pipeline. It turns a folder of technical-talk assets
(videos, PPTX decks, PDFs) — or a single YouTube URL — into a clean, strict-template
markdown briefing with slides, equations, and citations, in one `Report/` folder.

It began as a pipeline for **LSIC events only** (Lunar Surface Innovation Consortium
briefings). The goal has since widened significantly — this README reflects what the
system is **now**.

---

## How the goal evolved

```
 2026-05-29              2026-06-09..17           2026-06-11              2026-06-25 → today
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────────┐
│ ORIGINAL          │   │ CLOUD_BATCH       │   │ EASYRUN           │   │ SYNTH_QUALITY (ACTIVE)│
│                   │   │                   │   │                   │   │                       │
│ 8 LSIC event      │──►│ scale it: GCP VM +│──►│ generalize it:    │──►│ quality first:        │
│ folders → one     │   │ Gemini Batch API, │   │ any YouTube URL / │   │ frozen A/B baseline,  │
│ 15-section        │   │ 122-event corpus  │   │ local file via    │   │ windowed map-reduce   │
│ briefing each     │   │ (5-event slice    │   │ --source, lecture │   │ (MAPRED), Opus        │
│                   │   │ validated; full   │   │ profile, --remote │   │ cognition layer       │
│                   │   │ run deferred)     │   │ on-demand VM      │   │ (DEPTH) — THEN the    │
│                   │   │                   │   │                   │   │ 122-event batch       │
└───────────────────┘   └───────────────────┘   └───────────────────┘   └───────────────────────┘
```

The current center of gravity: **measurably improve long-video synthesis quality**
(proven by A/B bundles against a frozen 146-minute YouTube lecture in `golden/`),
then run the 122-event LSIC production batch with the improved pipeline.
`plans/README.md` is the live status board.

---

## Big picture

```
  INPUTS                              PIPELINE (src/)                      DELIVERABLE
┌─────────────────────────┐                                          ┌─────────────────────┐
│ A. LSIC corpus folders  │      8 idempotent stages — each          │ Report/             │
│    videos + PPTX + PDF  │      reads the previous stage's JSON,    │   notes.md          │
│    (via download_lsic/) │ ───► writes its own JSON, and SKIPS  ───►│   slides.pdf        │
│                         │      if its artifact already exists      │   slide_captions.md │
│ B. Any YouTube URL or   │      (crash-resumable, re-run safe)      │   equations.md      │
│    local media file     │                                          │   references.md     │
│    (via --source)       │                                          │                     │
└─────────────────────────┘                                          └─────────────────────┘
```

All cross-stage data is typed as `pydantic` models in [src/contracts.py](src/contracts.py) —
schema drift is caught at the seam, not three stages later.

---

## The stage pipeline

Both input modes converge on `work/events.json` (one `Event` per LSIC-id cluster, or a
synthetic `yt_<videoid>` / `adhoc_<slug>` event for `--source`). Every stage below skips
when its output artifact already exists.

```
                 work/events.json
                        │
                        ▼            artifacts under work/events/<event_id>/
┌───────────────┐
│ 1  ingest     │  ffmpeg · yt-dlp · LibreOffice ──► 01_ingest/     manifest.json, audio.wav,
└───────┬───────┘  · PyMuPDF (no LLM)                               videos/, decks/<id>/*.png
        ▼
┌───────────────┐
│ 2  transcribe │  Gemini 2.5 Flash — ASR in ──────► 02_transcript/ transcript.json
└───────┬───────┘  5-min chunks + diarization
        ▼
┌───────────────┐
│ 3  visual     │  scene-detect keyframes + ───────► 03_keyframes/  captions.json, frames/
└───────┬───────┘  Gemini 2.5 Flash VLM captions
        ▼
┌───────────────┐
│ 4  align      │  no LLM — silence/word-cap ──────► 04_aligned/    aligned.json, evidence.json
└───────┬───────┘  sectioning + deck matching
        ▼
┌───────────────┐
│ 5  synthesize │  profile-owned (next diagram) ───► 05_briefing/   notes.md, thematic.json
└───────┬───────┘  Gemini 2.5 Pro (+ Opus 4.8)
        ▼
┌───────────────┐
│ 6  slide_book │  Gemini 2.5 Flash per slide — ───► 05_briefing/   slides.pdf, slide_captions.md,
└───────┬───────┘  curate, comment, crop                            equations.md
        ▼
┌───────────────┐
│ 7  enrich     │  arXiv keyword search ───────────► 06_references/ references.md, references.json
└───────┬───────┘  (no LLM; opt-in --references)
        ▼
┌───────────────┐
│ 8  report     │  copy reader-facing files ───────► Report/        notes.md, slides.pdf, slide_captions.md,
└───────────────┘                                                   equations.md, references.md
```

| Stage      | Reads                               | Writes                        | Skips when                 |
|------------|-------------------------------------|-------------------------------|----------------------------|
| ingest     | Event (events.json)                 | 01_ingest/manifest.json + av  | manifest.json complete     |
| transcribe | 01 manifest (audio.wav)             | 02_transcript/transcript.json | transcript.json exists     |
| visual     | 01 manifest + 02 transcript         | 03_keyframes/captions.json    | captions.json exists       |
| align      | 01 + 02 + 03 (+ deck indexes)       | 04_aligned/aligned+evidence   | aligned.json exists        |
| synthesize | 04 aligned + evidence + 03 + decks  | 05_briefing/notes.md          | notes.md exists            |
| slide_book | 01 deck PNGs + slide_index          | 05_briefing/slides.pdf etc.   | per-slide curated cache    |
| enrich     | 05 thematic.json + notes.md         | 06_references/references.md   | references.md exists       |
| report     | 05 + 06 deliverables                | Report/ (copies)              | never — always refreshes   |

---

## Synthesis: two profiles, one seam

Stage 5 is where the two product shapes diverge. Each profile **owns its synthesis**
(`Profile.synthesize`) — there is no mode-branching inside the stage.

```
                        5  synthesize — Profile.synthesize seam
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             ▼                                                     ▼
  profile = briefing  (default)                          profile = lecture
  LSIC events — strict 15-section                        YouTube / generic talks
  template; byte-identical to the                                  │
  original path (proven in tests)                     segment.py packs transcript
             │                                        evidence into ≤45k-char windows
  one Gemini 2.5 Pro call per                                      │
  presentation (TL;DR, key claims,                 ┌───────────────┴────────────────┐
  open questions)                                  ▼                                ▼
             │                                 1 window                        ≥2 windows
             ▼                          single thematic call               MAPRED map-reduce
  one thematic assembly call            (degrade-to-today —                (diagram below)
  (expert lenses, funding /             exactly the old path)
  customers / chokepoints /                        └───────────────┬────────────────┘
  TRL tables, equations)                                           ▼
                                                  + dedicated cognition call  (DEPTH v2)
                                                    Claude Opus 4.8 — COGNITION_MODEL knob
                                                    operating algorithm · cognitive moves ·
                                                    claim epistemics · transfer questions
```

### MAPRED — size-windowed map-reduce (long lectures)

The old single-call path truncated long transcripts (~140k-char context squeeze). MAPRED
scales with video length: windows are **token-size-bounded, not chapter-bounded**, so
every input gets ≥1 window and chapterless videos are a non-issue.

```
  evidence.json — transcript Evidence, time-ordered
         │
         │  segment.py: greedy pack, ≤ 45,000 chars per window  (env WINDOW_BUDGET)
         ▼
  ┌──────────┐   ┌──────────┐         ┌──────────┐
  │ window 1 │   │ window 2 │   ...   │ window N │
  └────┬─────┘   └────┬─────┘         └────┬─────┘
       │ MAP          │ MAP                │ MAP       one Gemini 2.5 Pro call per window —
       ▼              ▼                    ▼           extracts LOCAL facts only (key_points,
  extract 1      extract 2            extract N        methods, notable_claims, open_questions,
       │              │                    │           citations, speakers), each grounded by
       └──────────────┼────────────────────┘           evidence_id; a failed window → {} and
                      ▼                                never sinks the reduce
        REDUCE — one Gemini 2.5 Pro call over all
        "=== WINDOW n FACTS ===" blocks; the global
        sections (summary, lenses, takeaways) are
        written exactly once, here
                      │
                      ▼
          thematic dict → render → notes.md
```

Global/synthesized fields are deliberately absent from the MAP prompt — no window can
emit a disconnected mini-summary; only REDUCE speaks with one voice.

### DEPTH — the cognition layer (lecture profile only)

A second, focused LLM call over the same event context, separated from the descriptive
call so each model does what it is best at:

| Call        | Extracts                                                        | Model                       |
|-------------|-----------------------------------------------------------------|-----------------------------|
| descriptive | what was said — key points, methods, claims, outline            | gemini-2.5-pro              |
| cognition   | how the speaker thinks — operating algorithm, cognitive moves,  | claude-opus-4-8 (default;   |
|             | epistemic status per claim, what doesn't transfer, transfer     | COGNITION_MODEL env knob    |
|             | questions for YOUR domain (READER_DOMAIN / CURRENT_WORK)        | for A/B against Gemini)     |

Degrades to `{}` on any failure — the descriptive notes still render; the cognition
sections are simply absent.

---

## Remote execution (`--remote`)

Heavy runs (ASR + VLM over hours of video) dispatch to an on-demand GCP VM with one
command. The whole sequence is machine-independent and self-bootstrapping:

```
  laptop  (--source URL --remote)                GCP  us-central1-a
  ───────────────────────────────                ──────────────────────────────────────
  1  preflight: gcloud installed + authed
  2  ensure VM ────────────────────────────────► create `lsic-batch` if absent
                                                 (infra/provision_gcp.sh, idempotent)
  3  start + wait-for-ssh ─────────────────────► boot VM, poll ssh over IAP (≤ 20 × 6s)
  4  bootstrap ────────────────────────────────► clone repo, venv (infra/vm_setup.sh),
                                                 push .env, append ANTHROPIC_API_KEY
  5  sync code ────────────────────────────────► git reset --hard origin/<LSIC_BRANCH>
  6  run job ──────────────────────────────────► python -m src.main --source ... --out
  7  fetch ◄─────────────────────────────────── scp Report/ back to local --out
  8  stop VM (unless --keep-up) ───────────────► instances stop
```

Separately, `--batch` pre-fills the ASR / caption / slide caches through the **Gemini
Batch API** ([src/batch_gemini.py](src/batch_gemini.py)) before each stage runs; any
request the batch missed is re-enqueued live by the stage's own skip gate.

---

## Models

| Call                                            | Model            | Where                                                                    |
|-------------------------------------------------|------------------|--------------------------------------------------------------------------|
| ASR (5-min chunks, diarization)                 | gemini-2.5-flash | [src/transcribe.py](src/transcribe.py)                                    |
| Keyframe + slide VLM                            | gemini-2.5-flash | [src/visual.py](src/visual.py), [src/slide_book.py](src/slide_book.py)    |
| Synthesis (presentations, thematic, MAP/REDUCE) | gemini-2.5-pro   | [src/synthesize.py](src/synthesize.py), [src/synth_mapreduce.py](src/synth_mapreduce.py) |
| Cognition (lecture profile only)                | claude-opus-4-8  | [src/anthropic_caller.py](src/anthropic_caller.py)                        |

---

## Quality method: golden A/B bundles

Every synthesis change ships **eval-first**: run OFF vs ON against the same frozen
input, diff the bundles, merge only on measured lift with no regression.

```
golden/
  lXUZvyajciY_baseline/      BASE   — frozen "before" (146-min, 7-speaker YouTube lecture)
  lXUZvyajciY_v2_gemini/     DEPTH  — cognition call, all-Gemini arm
  lXUZvyajciY_v2_opus/       DEPTH  — cognition call, Opus arm (preferred)
  lXUZvyajciY_v3_mapreduce/  MAPRED — windowed map-reduce output
  2026-03-26_event_mockup.md        — original LSIC briefing shape reference
  golden_additions.md               — DEPTH cognition-extraction spec
```

The pending EVAL milestone turns this into a deterministic, CI-able scorer
(`synth_eval.py` — cite-spread, cross-window coverage, groundedness; no LLM judge).

---

## Repo map

```
LSIC_videos/
├── src/                    the pipeline
│   ├── main.py             CLI — all modes and stages
│   ├── contracts.py        pydantic schemas at every stage seam
│   ├── profiles/           briefing (LSIC) vs lecture (generic talk) templates + prompts
│   ├── segment.py          size-bounded windowing (WINDOW_BUDGET = 45k chars)
│   ├── synth_mapreduce.py  MAPRED map/reduce calls (fakes-injectable, no import cycle)
│   ├── anthropic_caller.py scoped Claude caller for the cognition call
│   ├── remote.py           --remote GCP VM orchestration
│   └── batch_gemini.py     Gemini Batch API cache pre-fill (--batch)
├── download_lsic/          corpus acquisition front-end (harvest catalog → fetch assets)
├── infra/                  GCP provisioning (provision_gcp.sh, vm_setup.sh, RUNBOOK.md)
├── golden/                 frozen A/B bundles + briefing shape references
├── plans/                  the living plan board — README.md there = current status
│   └── archived/           done / superseded efforts (EASYRUN, CLOUD_BATCH, SYNTH_V2)
├── tests/                  fakes-only pytest suite — no network, ever
├── PLAN.md                 master pipeline plan (original architecture, M0–M5.5)
└── AWS_batch.md            non-authoritative AWS Batch context
```

---

## Current status (SYNTH_QUALITY)

```
  [x] BASE     frozen A/B baseline (golden/lXUZvyajciY_baseline)
  [x] DEPTH    v1/v2 cognition layer + Opus model knob
  [x] MAPRED   size-windowed map-reduce  ← this branch (alex/mapred-windows), v3 bundle frozen
  [ ] FIX      corpus driver no-drop + ingest retry (blocks BATCH)
  [ ] EVAL     deterministic synth_eval.py scorer vs baseline thresholds
  [ ] RUNEASY  URL/playlist → --remote in one command
  [ ] BATCH    the 122-event LSIC production run (briefing profile, unaffected by lecture work)
```

Authoritative details: [plans/SYNTH_QUALITY_PLAN.md](plans/SYNTH_QUALITY_PLAN.md).

---

## Quick start

```bash
# One YouTube lecture → Report/ locally
python -m src.main --source 'https://www.youtube.com/watch?v=...' --profile lecture --out ~/Desktop/talk

# Same, but heavy stages run on the on-demand GCP VM
python -m src.main --source 'https://www.youtube.com/watch?v=...' --profile lecture --remote --out ~/Desktop/talk

# LSIC corpus path
python -m src.main --discover                      # scan LSIC_Downloads/ → work/events.json
python -m src.main --pipeline --event <event_id>   # full chain for one event
python -m src.main --pipeline --all --keep-going   # every event with video
python -m src.main --status                        # per-event stage-completion matrix

# Sanity
python -m src.main --selftest
pytest -q
```

---

## Engineering invariants

These hold for every addition (see [.claude/CLAUDE.md](.claude/CLAUDE.md) §3):

- **Degrade-to-today** — new flag/input unset, empty, or throwing ⇒ output byte-identical to before.
- **Stage contract** — read previous JSON, write own JSON, skip when the artifact exists.
- **Schemas at the seam** — cross-stage data is a `pydantic` model in `contracts.py`.
- **Fakes-only tests** — deterministic pytest, no live Gemini / Claude / cloud calls.
- **Eval-first** — any LLM behavior change runs OFF vs ON against `golden/` before merging.
