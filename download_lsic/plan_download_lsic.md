# Implementation Plan — `download_lsic` (Acquisition Front-End)

Self-contained acquisition stage that feeds the LSIC Event → Briefing pipeline
(`../src/`). Walks the public LSIC catalog, filters to scope, and **streams videos
through the pipeline without permanently storing them**.

- **Parent pipeline:** `../PLAN.md` (M0–M5.5 done; M5b Papers + M6 Hardening pending).
- **Agent procedures:** `../clai/CLAUDE.md` (1:1:1:1 branch/TODO/progress, crash-loud, idempotent).
- **This doc governs the `download_lsic/` task only and is the source of truth for it.**

---

## The core constraint that shapes everything

Selected scope is **714 records ≈ 372 videos** (217 unique YouTube + 155 Zoom
`.mp4`), order-of-magnitude **150–300+ GB**. Local bulk storage is **not feasible**.
But the source is a **public page reachable in one `curl`** — re-downloading any
video is cheap and repeatable.

**Therefore: videos are transient, derived artifacts are permanent.**

The hard limit is *not* "1 video at a time" — it's "**not all 372 at once**." A small
**working window** of `WINDOW = 5–10` videos on disk is fine and is the unit of the
storage budget. The window must be **≥ the largest event's video count** (Kickoff = 3)
so an event's sibling videos can co-reside and be synthesized coherently.

```
maintain a working window of WINDOW (5–10) videos on disk:
  download (up to WINDOW)
    → ingest (audio.wav + keyframes) → transcribe → visual → align
    → DELETE source video + audio.wav once that video's transcript.json validates (Q2)
  synthesize per EVENT once all its videos' transcripts exist (not per video)
    → KEEP transcript.json, captions.json, aligned.json, meta.json, notes.md, slides.md
  on-disk videos never exceed WINDOW; text/image artifacts are tiny and kept
```

Docs (PDF/PPTX) are small → downloaded once into `../LSIC_Downloads/` and **kept** (Q4).

---

## Current-state evaluation (what exists, what the new corpus breaks)

**Built and working (`../src/`, per `../PLAN.md`):** M0 contracts · M1 discover+ingest
· M2 transcribe · M3 visual · M4 align+evidence · M5 synthesize · M5.5 slide_book.
**Pending:** M5b (standalone-paper template) · M6 (hardening).

**The pipeline's load-bearing assumption:** every asset is a **file on disk** whose
filename is `<lsic_id>-<name>.<ext>`; `discover.py` parses that integer, clusters by
**ID-proximity (gap > 3)**, classifies by extension/name, dedups by sha256.
`Asset.lsic_id` is a **required int**; `Asset.path` is a **required Path**.

**Two asset populations in the 714-record selection (180 events):**

| population | events | shape | fits pipeline today? |
|---|---|---|---|
| **File-backed** (Zoom `.mp4` + PDF + PPTX) | 151 | `zoom+docs` (141), `zoom` (10), `docs` (11) | **Yes — unchanged.** 155/155 Zoom files have clean `<id>-name`; this is the existing pipeline's exact shape |
| **YouTube** (Bi-Annual / Workshop) | 29 | `yt` (11), `yt+docs` (7), + standalone | **No — new class** |

**What YouTube breaks (4 assumptions), with evidence:**
1. **No file-id** — 223/223 YouTube rows have `lsic_id = None` → `discover._parse_lsic_id` returns None → asset is **silently skipped** today.
2. **Un-clusterable by ID** — YouTube row-ids live in a different namespace than file-ids; the 7 `yt+docs` events can't be ID-proximity-merged with their decks. The site's `associatedEvent` is the only authoritative link.
3. **Not on disk at scan time** — it's a URL, fetched transiently → `Asset.path` can't be set until download.
4. **`?t=` multi-row-per-video** — one recording appears as many catalog rows at different `t=` offsets (e.g. the Kickoff: ids 1930–1938 = one talk's presentations across a few videos). 223 rows → **217 unique videos**.

**Resolution that preserves Q1 (keep ID-proximity) without forcing it where it can't work:**
> **File-backed events keep `discover.py` disk-scan + ID-proximity, unchanged.**
> **YouTube events are grouped by the site's `associatedEvent`** (no ids exist to cluster on), and **the processing unit is the unique video** (`yt_video_id`), which preserves the pipeline's "1 video → 1 transcript" assumption. Each video's `?t=` rows become its `presentations[]` — seeding `align.py` directly, **no fingerprinting needed** (we already know the windows).

---

## Answered design questions (this session)

| # | Question | Answer | Consequence |
|---|---|---|---|
| Q1 | Event seam: site `associatedEvent` vs `discover.py` ID-proximity? | **Keep ID-proximity** | Applies to the 151 file-backed events (unchanged). YouTube must use `associatedEvent` — it has no ids (see evaluation) |
| Q2 | Delete `audio.wav` after transcript? | **Yes, eliminate it** | Cleanup deletes the source video, then `audio.wav` once `transcript.json` validates |
| Q3 | Stage-C concurrency? | **Window, not full parallel** | On-disk budget `WINDOW = 5–10` videos (≥ largest event's video count); processing can stay sequential. True parallel download/process is a later knob. The point is *not all 372 at once* |
| Q4 | Doc landing dir? | **`../LSIC_Downloads/`** | Where `discover.py` already looks — docs flow in with zero discover change |
| Q5 | Scholar author-enrichment? | **Later — main system needs paper support first** | Park Stage D behind M5b (papers). Build B+C first |

---

## System Integration Impact — what changes in `../src/`

| Component | Change | Detail |
|---|---|---|
| `discover.py` | **No change** | Keeps owning file-backed events via disk-scan + ID-proximity. Docs/Zoom land in `LSIC_Downloads/` and cluster as today |
| `contracts.py` | **Change** | `Asset.lsic_id: Optional[int]`; add `Asset.source_url: Optional[str]`; `Asset.path: Optional[Path]` (set post-download). YouTube video = `kind="video"`, `source_url` set, `path=None` until fetched |
| **new** `group_youtube.py` (in `download_lsic/`) | **New** | Build YouTube `Event`s from manifest `associatedEvent`, one processing unit per unique `yt_video_id`, `presentations[]` seeded from `?t=` offsets. **Merge** into `work/events.json` alongside `discover.py`'s output |
| `ingest.py` | **Change** | If a video asset has `source_url` and no `path`: `yt-dlp → scratch/<id>.mp4`, then ffmpeg audio as today. After ingest, hand the scratch path to the cleanup hook |
| `transcribe.py` / `visual.py` / `align.py` / `synthesize.py` / `slide_book.py` | **No change** | They operate on `audio.wav` / frames / decks — agnostic to video origin. (align: YouTube `presentations[]` are pre-seeded, so fingerprint match is skipped when windows are already present) |
| **new** cleanup hook (in `main.py` or `stream_videos.py`) | **New** | Post-success: `rm` scratch video; `rm audio.wav` once `transcript.json` validates (Q2). Crash-loud; never delete on partial failure |
| `main.py` | **Change** | New `--download` front-end + per-event stream loop (sequential) calling existing stage spine one video at a time |
| `validators.py` | **Add** | `validate_grouping` — cross-check `discover.py` clustering vs manifest `associatedEvent` (denser corpus; gap>3 could over-merge). `validate_cleanup` — on-disk videos ≤ WINDOW; no residual video/audio for a `processed` id. `validate_completeness` — every presentation resolves to a transcript span and vice-versa (see integrity invariants) |

**Net:** the **151 file-backed events need zero pipeline surgery** — only the doc/zoom
download + streaming-delete wrapper. The **29 YouTube events** need the contract
widening + `group_youtube.py` + the ingest URL-fetch branch. Everything downstream of
`audio.wav` is untouched.

### Metadata enrichment — carry catalog truth into the pipeline

The video is transient, but its **catalog metadata is permanent and should be kept**.
`discover.py` only recovers `lsic_id` + `date` from the filename; the manifest already
holds richer, authoritative fields the pipeline currently *infers* (or skips). Join the
manifest onto `events.json` (by `lsic_id` for file-backed, by row for YouTube) so each
asset/event carries a `meta` block:

| Catalog field | Pipeline use today | With metadata |
|---|---|---|
| `speaker` | generic `Speaker A/B/C` (M2 + a `../PLAN.md` open question) | **real presenter names** in the briefing — resolves that open question |
| `event_name`, `title` | filename-derived event_id | authoritative title / 🎯 header |
| `release_date` | YYYYMMDD regex on filename | authoritative date (YouTube has none in filename) |
| `topics` (capability areas) | not captured | tags the briefing's capability framing for free |
| `description` | — | abstract seed for TL;DR / paper template (helps Q5) |
| `associatedUrl?t=` | fingerprint-matched windows | **presentation windows seeded directly** for YouTube |

**Persistence:** keep the per-event slice of the manifest as `work/events/<event>/meta.json`
(survives video deletion). This is the durable record of "what the page said" — exactly
the metadata tracking the video can't provide once it's gone.

**Contract:** add an optional `meta: dict` (or typed `AssetMeta`) to `Asset`/`Event` in
`contracts.py`; populate in the enrichment step; read in `transcribe.py` (speaker hints)
and `synthesize.py` (title, date, speakers, topics, abstract).

### Referential integrity — Event ⊇ Video ⊇ Presentation (don't lose "who/which talk")

The catalog is a **3-level hierarchy**, not a flat list. One event has 1..N videos;
one video has 1..N presentations (catalog rows with their own speaker/title/topic and a
`t=` start). In the selection: **3 of 217 videos carry >1 presentation (max 4); event
100 = 3 videos / 9 presentations.** Rare, but the schema and delete logic must hold it
or those talks vanish.

```
Event (associatedEvent=100)
  └─ Video (yt_video_id, the yt-dlp unit)          event 100 → 3 videos
       └─ Presentation (row: speaker,title,topic,t_start)   one video → up to 4
```

**Five break points** where "processing 1 without the other" loses data:

| # | Link that can break | What's lost |
|---|---|---|
| A | Presentation metadata ↔ its transcript span | content survives, **attribution gone** (no who/which talk) |
| B | A video's *sibling* presentations (1 video→N talks) | only 1 of N rows attached → the rest silently dropped |
| C | An event's *sibling* videos (1 event→N videos) | briefing fragments or synthesizes half-blind |
| D | `t=` **end** boundary (`t=` is start-only) | wrong end → metadata lands on the wrong words |
| E | Schema shape "1 video = 1 meta row" | one-to-one contract **structurally can't hold** N presentations |

**Resolution — split the unit of work** (this is *why* the window must hold an event):
> **Download + transcribe unit = the video** (then delete it; keep the transcript).
> **Synthesis unit = the event** — fires only once *all* its videos' transcripts exist.
> Synthesis needs the *transcript*, not the *video* → storage stays bounded, events stay whole.

**Invariants the code must guarantee (kills A–E):**
1. `work/events/<event>/meta.json` is the **durable ledger** — every presentation `{video_id, t_start, t_end, speaker, title, topic, description}`, written before download, never deleted. (`t_end` = next sibling's `t_start`, else video duration → fixes D.)
2. A video is **deleted only after its `transcript.json` validates** (fixes the B race).
3. An event is **synthesized only after every `video_id` in its `meta.json` has a transcript** and every presentation resolves to a non-empty span (fixes C, E).
4. **`validate_completeness` gate (new):** *fails the run* if any presentation in `meta.json` has no transcript span, or any large span maps to no presentation ("unattributed gap"). Turns "info might be lost" into "the run fails if it would be" — crash-loud, matching the repo's evidence-grounded philosophy.

---

## Architecture

```
Products.php (public, one GET)
   ▼
harvest.py ─► download_manifest.json (1184)
   ▼
select.py  ─► selected_manifest.json (714, 180 events)
   ├──────────────► Stage B: fetch DOCS (228 pdf + 92 pptx) → ../LSIC_Downloads/ (kept)
   │                    discover.py clusters file-backed events UNCHANGED
   │
   └──────────────► Stage C: STREAM VIDEOS (working window of 5–10 on disk)
         file-backed (155 Zoom):           YouTube (217 unique):
           requests → scratch/<id>.mp4        group_youtube.py → events.json + meta.json
           ↘                                   yt-dlp → scratch/<vid>.mp4
            └─► per video: ingest → transcribe → visual → align ; rm video+audio once transcript valid
            └─► per EVENT (all its videos done): synthesize → slide_book → validate_completeness
                         → KEEP work/events/<event>/{transcript,captions,aligned,meta,notes,slides}
                         → video_state.json marks processed ; resumable
```

---

## Stages & Status

- [x] **A — Harvest** — `harvest.py` → `download_manifest.json` (1184). DONE.
- [x] **A.2 — Select** — `select.py` → `selected_manifest.json` (714 / 180 events). DONE.
- [ ] **B — Fetch docs** — 228 PDF + 92 PPTX → `../LSIC_Downloads/`, `<id>-name`, idempotent, results log. *Small, low-risk, first.*
- [ ] **C0 — Contract widening** — `contracts.py`: `lsic_id`/`path` optional + `source_url` + optional `meta`. `--selftest` still green.
- [ ] **C1 — YouTube grouping** — `group_youtube.py`: manifest `associatedEvent` → Events keyed by unique `yt_video_id`, `presentations[]` from `?t=`; merge into `events.json`.
- [ ] **C1.5 — Metadata enrichment** — join manifest onto `events.json`; write `work/events/<event>/meta.json` (speaker, title, date, topics, description). Wire `synthesize.py` to use real speaker names + title/date/topics.
- [ ] **C2 — Ingest URL branch** — `ingest.py`: `source_url` video → yt-dlp → audio; hand path to cleanup.
- [ ] **C3 — Stream loop + cleanup** — `stream_videos.py`: event-scheduled working window (5–10); per-video download→ingest→transcribe→visual→align→delete; per-event synthesize→`validate_completeness`; `video_state.json`; resumable.
- [ ] **D — (parked, after M5b) Author enrichment** — per-speaker Google Scholar lookup → related papers → fold in. Needs main-system paper support first (Q5).

### Stage B — Fetch docs (next up)
- `fetch_docs.py`: from `selected_manifest.json`, take `kind ∈ {pdf, pptx, otherfile}`.
- Download `BASE + filePath` → `../LSIC_Downloads/<target_filename>`; skip if exists.
- `download_results.json` (`ok[]`/`failed[]`); retry failures once; log `N/320`.
- **Verify:** on-disk count == expected; PDFs have `%PDF` header, PPTX are valid zips; `discover.py` re-run still clusters cleanly (`validate_grouping`).

### Stage C — Stream videos (working window of 5–10)
- Dedup YouTube by `yt_video_id` (223 → 217). State file `video_state.json`: `{id, kind, event_id, status, artifacts[], error}`.
- **Schedule by event**, so an event's sibling videos land in the window together (enables event-coherent synthesis).
- Per video: fetch → `scratch/<id>.mp4` (yt-dlp / requests) → ingest → transcribe → visual → align → **rm video + audio.wav once `transcript.json` validates**.
- Per event (all videos done): synthesize → slide_book → **`validate_completeness`** → mark event `processed`.
- Failure → mark `failed`, continue, re-runnable. Kill mid-run resumes cleanly.
- **Verify:** on-disk videos ≤ WINDOW at all times; every presentation in `meta.json` resolves to a transcript span; no residual video/audio for a `processed` event.

---

## Open Questions (remaining)

1. **Event briefing across sibling videos** — *processing* unit is the video; *synthesis* unit is the event (resolved above). Remaining product call: does a multi-video event (Kickoff = 3 videos) become **one** notes.md stitched across all three, or one per video cross-linked? Affects `synthesize.py` only.
2. **Cleanup vs. visual stage ordering** — the *video* (not audio) is needed by M3 visual for keyframes. So delete order is: extract keyframes (M3) → **then** rm video → rm audio after transcript (M2) validates. Confirm M3 runs before deletion in the per-video sequence.
3. **`WINDOW` value + eviction** — pick 5 or 10; eviction policy when full (block until an event completes vs. LRU by video). Sequential v1 makes this simple; revisit with concurrency.
4. **discover density** — 480 file-backed files vs today's 26; gap>3 may over-merge adjacent events. `validate_grouping` against `associatedEvent` is the guard.
5. **Zoom-video auth** — confirmed catalog + a sample PDF are public; **not yet confirmed** the Zoom `.mp4` `filePath`s serve without a cookie (the HEAD test was interrupted). Verify before Stage C.

---

## Risks & Gaps (resolve before Stage C)

| # | Gap | Why it bites | Mitigation |
|---|---|---|---|
| G1 | **Processing cost/time ≫ download** | 372 videos ≈ **500+ hours of audio** → Gemini ASR + VLM + Claude synth = likely **hundreds of $ and multi-day wall-clock**. Storage was never the main cost | Add a cost/time estimate + a `--limit`/per-batch budget gate *before* a full run; do a 5-event pilot first |
| G2 | **`discover.py` disk-scan vs. streaming-delete** | Zoom videos live in `scratch/` (transient), **not** `LSIC_Downloads/` — so a disk-scan won't see them, and the event has decks but no video asset | Build `events.json` for video assets from the **manifest** (keep the ID-proximity *algorithm*, change the *input source*); discover.py owns only the kept docs. **Contradicts the current "discover unchanged" line — needs a decision** |
| G3 | **YouTube anti-bot at volume** | "Public" ≠ "bulk-downloadable." 217 pulls can trigger "sign in to confirm you're not a bot" / throttling | Plan for `yt-dlp --cookies-from-browser`, rate-limit/sleep, retry; treat YT auth as *maybe-needed* not *never* |
| G4 | **Deck-less YouTube events break the M5 template** | M5 is built around per-presentation **deck** alignment (Amphenol/Nunez/Yank Tech). Many YT Bi-Annual talks have **no deck** → slide_book/📐/fingerprinting empty | Add a deck-less event variant of the synth template; align uses `t=` windows only |
| G5 | **Zoom `.mp4` reachability/auth unverified** | HEAD test was interrupted; old recordings may 404 or need a cookie | Probe a sample of Zoom `filePath`s (HEAD) before committing Stage C |
| G6 | **Video-less "docs" events (11)** | Pipeline is **audio-first**; an event with no video has no spine to synthesize against | Route these to the **paper** path (M5b), not the event path |
| G7 | **Overlap with existing 26-event corpus** | The selection re-includes events already processed (e.g. 3105–3109) | Idempotency must skip already-`processed` events, not just existing files |
| G8 | **YouTube ToS** | Bulk yt-dlp may conflict with YouTube ToS even for public, member-relevant content | User-authorized personal research use; note it, don't scale-abuse |

---

## Files

| File | Role | Status |
|---|---|---|
| `RECON.md` | Recon spec (answered: catalog public + embedded) | done |
| `harvest.py` | Stage A — catalog → `download_manifest.json` | ✅ |
| `select.py` | Stage A.2 — filter → `selected_manifest.json` | ✅ |
| `download_manifest.json` / `selected_manifest.json` | 1184 / 714 tagged records | ✅ |
| `catalog_summary.md` | Breakdown by kind/category/topic/year | ✅ |
| `fetch_docs.py` | Stage B — download PDFs/PPTX → `../LSIC_Downloads/` | TODO |
| `group_youtube.py` | Stage C1 — YouTube events from `associatedEvent` | TODO |
| `stream_videos.py` | Stage C3 — bounded download→process→delete loop | TODO |
| `recon_artifacts/` | `allResults.json`, `products.html` | ✅ |

_Commander Alex — plan merged with the live pipeline. The 151 file-backed events need
no pipeline surgery; only YouTube (29 events) widens the contract. Say "code it" to
build Stage B (docs first); Stage C follows._
