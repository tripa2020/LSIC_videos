# RECON — Stage A Harvester (LSIC site)

**Purpose:** Gather *everything* a Playwright harvester could need to walk the
authenticated LSIC site and emit one manifest row per downloadable asset. This
spec deliberately **over-collects** — capture more than you think is needed.

**You are an LLM doing recon.** You may have browser automation, or you may be
guiding a human through Chrome DevTools. Either way, your output is the filled
**`recon_findings.md`** template at the bottom, plus the saved artifacts in
`download_lsic/recon_artifacts/`. Do **not** write the harvester yet — recon only.

---

## Ground truth you must reconcile against

The downstream pipeline already holds ~26 events in `../LSIC_Downloads/`. Their
filenames are the **contract** your harvest must reproduce. Real examples:

```
2956-20251023_SPCAslides.pptx
2988-GMT20251120-160224_Recording_2880x1800.mp4
2994-Key_Power_Trade_Studies_v1.pdf
3105-GMT20260326-150218_Recording_2880x1800 (1).mp4
3178-GMT20260409-150202_Recording_1920x1080.mp4   ← appears twice (dup case)
525-Video from ISRU Monthly Meeting - 2020 July.mp4
```

Pattern: **`<LSIC_ID>-<original_title>.<ext>`**. The leading integer is parsed by
`../src/discover.py` (`^(\d+)-`). **The single most important recon goal is:
where does that integer come from on the site?** It is almost certainly an asset
/node/file ID in a URL (e.g. `/node/2956`, `/media/2956`, `?fid=2956`) or a data
attribute. Find it. Everything else is wiring.

Asset kinds seen: `.mp4` (Zoom recordings, named `GMT*Recording*`), `.pptx`
(`*SPCAslides*` = host deck; others = presentations), `.pdf` (papers/notes).
**Plus** the new finding: many videos are **public YouTube links**, not files.

---

## Output artifacts (save ALL of these)

Into `download_lsic/recon_artifacts/`:

1. `recon_findings.md` — the filled template (bottom of this doc). **Primary deliverable.**
2. `auth.json` — Playwright `storageState` after a successful login (the reusable session).
3. `list_page.html` — full HTML of one catalog/listing page (`page.content()`).
4. `detail_page.html` — full HTML of one item detail page.
5. `full_download.har` — a HAR capture of ONE complete download flow (login→list→detail→download), with "Preserve log" on.
6. `screenshots/` — list page, detail page, and the DevTools Network panel right after a download click.
7. `sample_manifest.jsonl` — 5–10 **real** rows you hand-extracted, in the target schema (see §6). Proves the selectors actually resolve.

---

## The fastest selector-capture trick

Run `npx playwright codegen <SITE_URL>` (or `python -m playwright codegen`). It
opens a real browser, **records your clicks, and prints working selectors** for
every element you touch. Do the full flow once in codegen → you get the
click-path table for free. Also use it to **save storageState** after login
(`--save-storage=auth.json`). This is faster and more accurate than hand-reading
the DOM. Fall back to F12 → Inspect only where codegen is ambiguous.

---

## Recon protocol — follow in order, record as you go

### 0. Entry & environment
- [ ] Base URL of the site, and the exact **login URL**.
- [ ] Browser used, and whether the site is behind Cloudflare / a WAF splash.

### 1. AUTH (decides the storageState strategy)
- [ ] Auth type: **username/password form**, **SSO (Google/Microsoft/SAML)**, or **token/magic-link**?
- [ ] Field selectors: username input, password input, submit button.
- [ ] Is there **2FA / MFA**? (changes whether headless reuse is possible.)
- [ ] After login, does the session **persist across a browser restart** (cookie lifetime)? Note approximate expiry if visible.
- [ ] **Save `auth.json`** via codegen `--save-storage` or `context.storage_state()`.
- [ ] Re-open the saved session in a fresh context — confirm it lands logged-in (no redirect to login).

### 2. THE CATALOG — where the 300+ items live
- [ ] URL of the listing/index/search page that enumerates items.
- [ ] Is it **search/filter-driven** (must submit a query) or a **flat browsable list**?
- [ ] **Total item count** shown anywhere? Record the exact number (this is your N/300 denominator).
- [ ] **Pagination mechanism** — pick one and record specifics:
  - URL param (`?page=2`, `&offset=50`) → record the param name + step size + max page.
  - **"Load more" button** → record its selector + how many items per click.
  - **Infinite scroll** → record the scroll trigger + items per batch.
  - Numbered page links → record the selector + total page count.
- [ ] **Item container selector** — the repeating card/row element (e.g. `div.search-result`, `tr.asset-row`). This is what the harvester loops over.
- [ ] Per card, the selectors/attributes for:
  - [ ] **Title** text.
  - [ ] **LSIC ID** (THE critical field — URL, `data-*` attr, or text). Show exactly where it lives.
  - [ ] **Link to the detail page** (`href`).
  - [ ] Date, if present.
  - [ ] Any **type/kind indicator** (icon class, label, file-extension hint).

### 3. THE ITEM DETAIL & DOWNLOAD PATH
For one item of EACH kind (YouTube video, Zoom mp4, PDF, PPTX), record the click
path and the final asset reference:

- [ ] **Click path** from card → asset, each step as `{what I click}` + `{selector}`.
- [ ] ⚠️ **New-tab behavior:** does any click open a **new tab/window**? (You hit this in earlier recon — it's why the Network panel looked empty.) Record which steps spawn tabs; the harvester must handle `page.expect_popup()`.
- [ ] **iframe?** Is the video/player inside an `<iframe>`? Record the frame URL/selector — Playwright must target the frame.
- [ ] **YouTube items:** is it an **embedded iframe** (`youtube.com/embed/<VIDEO_ID>`) or a **link out** to `youtube.com/watch?v=...`? Extract the canonical **watch URL or 11-char video ID**. (Public per the build decision → no cookies needed for yt-dlp.)
- [ ] **Zoom / mp4 items:** capture the **direct file request URL** from the Network/HAR. Note its `Content-Type`, status, and whether it 200s in **incognito** (i.e. needs the site cookie or not).
- [ ] **PDF / PPTX items:** the **direct file `href`**, and the filename the server suggests (`Content-Disposition`).

### 4. CLASSIFICATION RULES
- [ ] Write the rule that maps an item → `kind ∈ {youtube, zoom, pdf, pptx, other}` from what's visible (URL pattern, extension in href, icon). The harvester needs this to route to the right fetcher.

### 5. EDGE CASES, LIMITS, GROUPING (over-collect here)
- [ ] **Anti-bot:** any CAPTCHA, Cloudflare challenge, "are you human," or rate-limit/slow-down? Record what triggered it.
- [ ] **Multi-asset items:** does one event/page hold **1 video + N decks + N PDFs** together? How are they grouped on the page? (Maps to the pipeline's event clustering.)
- [ ] **Duplicates:** any items that appear twice (cf. `3178 ×2`)? How would you dedupe — by ID? by URL? by content hash?
- [ ] **Missing IDs / odd naming:** any items with no LSIC ID, or non-numeric IDs?
- [ ] **Throttle courtesy:** note any per-request delay the site seems to expect.
- [ ] **ToS / robots:** confirm bulk download of this (authorized) content is permitted.

### 6. PROVE IT — hand-extract a sample manifest
Pull **5–10 real items** spanning all kinds into `sample_manifest.jsonl`, one
JSON object per line, in the target schema the harvester will emit:

```json
{"lsic_id": 3105, "title": "20260326_event_recording", "kind": "youtube", "url": "https://www.youtube.com/watch?v=XXXXXXXXXXX", "source_page": "https://lsic.example/item/3105", "target_filename": "3105-20260326_event_recording.mp4"}
{"lsic_id": 3107, "title": "Amphenol Lunar Interconnects dealing with dust 03 12 2026 update", "kind": "pdf", "url": "https://lsic.example/files/3107.pdf", "source_page": "https://lsic.example/item/3107", "target_filename": "3107-Amphenol Lunar Interconnects dealing with dust 03 12 2026 update.pdf"}
```

If these 10 rows are correct and complete, Stage A is essentially specified.

---

## FILL-IN TEMPLATE → save as `recon_artifacts/recon_findings.md`

```markdown
# LSIC Recon Findings

## 0. Entry
- Base URL:
- Login URL:
- Cloudflare/WAF?:

## 1. Auth
- Type (form/SSO/token):
- Username selector:
- Password selector:
- Submit selector:
- 2FA/MFA?:
- Session persists across restart? approx expiry:
- auth.json saved? (y/n):

## 2. Catalog
- Listing URL:
- Search/filter-driven or flat?:
- Total item count shown:
- Pagination type (url-param / load-more / infinite / numbered):
- Pagination specifics (param name / button selector / page size / max):
- Item container selector:
- Title selector:
- **LSIC ID location (exact)**:
- Detail-link selector (href):
- Date selector:
- Kind-indicator selector:

## 3. Click path per kind
| Kind | Step | What I click | Selector | New tab? | iframe? |
|------|------|--------------|----------|----------|---------|
| youtube | 1 | | | | |
| youtube | 2 | | | | |
| zoom    | 1 | | | | |
| pdf     | 1 | | | | |
| pptx    | 1 | | | | |

- YouTube: embed iframe or watch link? → canonical URL/video-ID source:
- Zoom/mp4: direct file URL + needs-cookie? (incognito test):
- PDF/PPTX: direct href + Content-Disposition filename:

## 4. Classification rule
- youtube →
- zoom →
- pdf →
- pptx →
- other →

## 5. Edge cases & limits
- Anti-bot/CAPTCHA:
- Multi-asset grouping:
- Duplicates + dedupe key:
- Missing/odd IDs:
- Throttle delay expected:
- ToS/robots OK?:

## 6. Sample manifest
- sample_manifest.jsonl saved with N rows: (N=)
- Kinds covered: youtube / zoom / pdf / pptx

## THE TWO ANSWERS THAT DECIDE EVERYTHING
1. Where the LSIC ID comes from:
2. YouTube = embed iframe or watch link (how the harvester extracts the URL):
```

---

## Hard rules for the recon LLM
- **Recon only — do not build the harvester.** Output findings + artifacts.
- **Never hardcode credentials.** Use interactive login + saved `auth.json`.
- Capture **raw artifacts** (HTML, HAR, screenshots), not just prose — they let the build session verify your selectors without re-walking the site.
- When unsure, **record both possibilities** and flag the ambiguity. Over-collect.
- The build session needs only `recon_findings.md` + the artifacts to write Stage A end-to-end.
```
