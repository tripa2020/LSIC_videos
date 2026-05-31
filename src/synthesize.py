"""Stage 5: synthesize a strict-template notes.md from the M1-M4 artifacts.

Two entry points:
- synthesize_thin (M2.5 steel thread): single LLM call from transcript only.
- synthesize_full (M5):    per-presentation LLM calls + one thematic
                            assembly call + deterministic markdown render
                            with Evidence-grounded citations.

Backend: Gemini 2.5 Flash (unified with M2 + M3; one API key for the whole
pipeline). The Anthropic Claude backend lives in git history if needed —
swap by reverting this module's LLM client.

M5 call budget per event (3-presentation event like 2026-03-26):
  3x presentation calls + 1x thematic — well under \$1/hr ceiling.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date as _date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src import util
from src.contracts import (
    AlignmentResult, Asset, Caption, Evidence, IngestResult,
    Presentation, Segment,
)


SYNTH_MODEL = "gemini-2.5-pro"   # was flash — Pro for richer, denser briefings (~4x cost, ~3x slower)
# Pro REQUIRES thinking mode (rejects budget=0 with INVALID_ARGUMENT); Flash supports both.
THINKING_BUDGET = 0 if "flash" in SYNTH_MODEL else 4096
MAX_OUTPUT_TOKENS = 8000
TRANSCRIPT_INPUT_CAP_CHARS = 80_000   # safety cap; full M5 chunks per-section

SYSTEM_PROMPT = """You write technical engineering briefings from meeting transcripts for C'mander Alex.

You receive a transcript JSON array. Each segment has start/end (seconds),
text, speaker_id (A/B/C…), language (ISO 639-1).

Produce ONLY a `notes.md` file with the 15-section canonical structure below.
Every populated section must carry at least one `[mm:ss]` citation that maps
to a transcript timestamp. Sections without evidence must still appear with
an italic line: `*Not applicable to this clip — <one-line reason>.*`

CANONICAL STRUCTURE (this exact order, exact emojis, exact section names):

```
---
event_id: ...
date: ...
title_inferred: "..."
duration: "mm:ss"
speakers_detected: N
languages: [..]
generated: YYYY-MM-DD
---

# <Inferred Title>

## 🎯 Bottom Line for C'mander Alex
<Exactly 3 sentences framing: current state · engineering constraints · funding/chokepoints.>

### Through 5 Expert Lenses
*Roles selected from `clai/.claude/Behavior/Roles.md` based on event content.*

- 🔧 **<Role A>** — <one-sentence take> `[mm:ss]`
- 🧠 **<Role B>** — <take> `[mm:ss]`
- ✅ **<Role C>** — <take> `[mm:ss]`
- 📡 **<Role D>** — <take> `[mm:ss]`
- 🏭 **<Role E>** — <take> `[mm:ss]`

## 🗂️ Contents
- 🎤 Presentations (N)
- 🔬 What's being done right now
- 🛠️ Engineering system-design questions
- ❓ Per-Question Role Analysis
- ⚠️ Main engineering constraints
- 💰 Funding landscape
- 🛒 Paying Customers / Demand
- 🚧 Chokepoints
- ⚙️ Technology Readiness & Maturity (TRL)
- 📐 Key equations & models
- 🗣️ Speakers
- 🔖 Citations & references mentioned
- 📎 Slide highlights

## 🎤 Presentations
<one ### sub-block per presentation; stub if none in clip>

## 🔬 What's being done right now
- bullet `[mm:ss]`

## 🛠️ Engineering system-design questions
- bullet `[mm:ss]`

## ❓ Per-Question Role Analysis
**1. <question>** `[mm:ss]`
- 🔧 *Role* — take
- ✅ *Role* — take

## ⚠️ Main engineering constraints
- bullet `[mm:ss]`

## 💰 Funding landscape
| Org | Mechanism | Scale | Focus | Source |
|-----|-----------|-------|-------|--------|
| ... | ... | ... | ... | `[mm:ss]` |

## 🛒 Paying Customers / Demand
<2-3 sentence prose intro>

| Customer | Procurement mechanism | Status | Spend horizon | Source |
|----------|-----------------------|--------|---------------|--------|
| ... | ... | Active funding | ... | ... |

## 🚧 Chokepoints
| Stage | Chokepoint | Source |
|-------|------------|--------|
| Research | ... | `[mm:ss]` |
| Development | ... | `[mm:ss]` |
| Funding | ... | `[mm:ss]` |
| Implementation | ... | `[mm:ss]` |

## ⚙️ Technology Readiness & Maturity (TRL)
| Technology | TRL | Basis | Confidence | Source |
|------------|-----|-------|------------|--------|
| ... | ... | ... | inferred | `[mm:ss]` |

## 📐 Key equations & models
*Not applicable to this clip — no equations identified.*

## 🗣️ Speakers
- **A** — <role/identity if known> `[start → end]`

## 🔖 Citations & references mentioned
- *<thing cited>* `[mm:ss]`

## 📎 Slide highlights
*Not applicable to this clip — no visual frames sampled in steel-thread mode.*
```

TABLE RULE: pad columns with spaces so every `|` lines up across rows.
Use `*Not applicable to this clip — <reason>.*` for any section that lacks
evidence in the transcript.

OUTPUT: ONLY the notes.md content. No prose, no markdown code fences, no
preamble.
"""

USER_PROMPT_TEMPLATE = """\
Transcript ({n_segments} segments, duration {duration:.0f}s):

```json
{transcript}
```

Event metadata:
- event_id: {event_id}
- date: {date}
- duration: {duration_mmss}
- speakers_detected: {speaker_count}
- languages: {languages}

Generate the notes.md per the canonical structure.
"""


def synthesize_thin(
    event_id: str,
    transcript_path: Path,
    duration_sec: float,
    output_path: Path,
    event_date: str,
) -> Path:
    """Single-call Gemini synthesis. Writes notes.md and returns its path."""
    client = _gemini_client()

    segs_raw = json.loads(transcript_path.read_text())
    segs = [Segment.model_validate(s) for s in segs_raw]
    speakers = sorted({s.speaker_id for s in segs if s.speaker_id})
    languages = sorted({s.language for s in segs if s.language})

    duration_mmss = f"{int(duration_sec // 60):02d}:{int(duration_sec % 60):02d}"

    transcript_blob = json.dumps(segs_raw, indent=1)[:TRANSCRIPT_INPUT_CAP_CHARS]
    user_prompt = USER_PROMPT_TEMPLATE.format(
        n_segments=len(segs),
        duration=duration_sec,
        transcript=transcript_blob,
        event_id=event_id,
        date=event_date,
        duration_mmss=duration_mmss,
        speaker_count=len(speakers),
        languages=",".join(languages) or "en",
    )

    resp = client.models.generate_content(
        model=SYNTH_MODEL,
        contents=[user_prompt],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    notes_text = (resp.text or "").strip()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    util.write_with_manifest(output_path, notes_text, stage="synthesize")
    return output_path


# ============================================================
# M5: full per-presentation + thematic + Evidence-grounded
# ============================================================

PRES_SYSTEM_PROMPT = """You extract structured data from a single presentation given during a meeting.

You receive:
- The presentation's time window in the meeting
- The transcript segments within that window, each tagged with [ev_xxx]
- The deck text + speaker notes for that presenter's slides

Return ONLY a JSON object (no markdown fences, no prose):
{
  "title":        "<presenter's topic — refined from deck title and transcript>",
  "presenter":    "<full name + affiliation, e.g. 'Dr. Jorge Nuñez (JHU/APL)'>",
  "tldr":         "<2-4 sentences capturing the core argument>",
  "key_claims":   [{"text": "...", "evidence_id": "ev_..."}],
  "open_questions": [{"text": "...", "evidence_id": "ev_..."}],
  "trl": {
    "value":      "<e.g. '4-5' or '3'>",
    "basis":      "<one-line basis from data shown>",
    "confidence": "claimed" | "inferred"
  }
}

CITATION RULE: Only cite evidence_id values that appear in the passed
transcript. Never invent an evidence_id. If you can't ground a claim, omit
the evidence_id field (set it to "" or null) rather than fabricating one.
"""


THEMATIC_SYSTEM_PROMPT = """You assemble a multi-section briefing from a meeting's transcript + slide text + visual captions for C'mander Alex (a robotics/firmware engineer interested in: current state of work · engineering constraints · funding mechanics · chokepoints).

You receive:
- Event context (compact per-section transcript with [ev_xxx] markers)
- The per-presentation outputs already extracted upstream
- A constrained role pool — every role you cite must come from this list

Return ONLY a JSON object (no markdown fences, no prose). Shape:

{
  "title": "<inferred event title, ~6-12 words>",
  "bottom_line": "<EXACTLY 3 sentences: current state · constraints · funding/chokepoints>",
  "expert_lenses_top": [
    {"role": "<from pool>", "emoji": "🔧", "take": "<1 sentence>", "evidence_id": "ev_..."},
    ... (exactly 5)
  ],
  "whats_being_done": [{"text": "...", "evidence_id": "ev_..."}],
  "whats_being_done_lenses": [3 lens objects],
  "eng_questions": [{"text": "...", "evidence_id": "ev_..."}],
  "eng_questions_lenses": [3 lens objects],
  "per_question_analysis": [
    {
      "question": "<verbatim from eng_questions>",
      "evidence_id": "ev_...",
      "role_takes": [{"role": "...", "emoji": "🔧", "take": "..."}, ...]  (2-3 takes)
    }
  ],
  "constraints": [{"text": "...", "evidence_id": "ev_..."}],
  "funding": {
    "rows": [{"org": "...", "mechanism": "...", "scale": "...", "focus": "...", "evidence_id": "ev_..."}]
  },
  "funding_lenses": [3 lens objects],
  "customers": {
    "intro": "<2-3 sentences on demand landscape>",
    "rows": [{"customer": "...", "mechanism": "...", "status": "<one of: Active funding|Active PO|Open RFP/RFI|Aspirational>", "horizon": "...", "evidence_id": "ev_..."}]
  },
  "chokepoints": {
    "rows": [{"stage": "<one of: Research|Development|Funding|Implementation>", "chokepoint": "...", "evidence_id": "ev_..."}]
  },
  "equations": null,  // or list of "$$...$$ — context [ev_xxx]" strings
  "speakers": [{"label": "A", "role": "<role/identity if known>", "time_range": "00:00→04:30"}],
  "citations": [{"text": "<thing mentioned, e.g. 'JSC-1A simulant'>", "evidence_id": "ev_..."}]
}

ROLE POOL (every "role" field must use one of these exact names):
{role_pool}

HARD RULES:
1. CITATION GROUNDING: only cite evidence_ids that appear in the passed
   transcript. Never invent an evidence_id.
2. NO PLACEHOLDERS: never write `$X.X`, `~$YY`, `TBD`, `XXX`. If a value
   isn't disclosed in the source, write "not disclosed" or omit the row.
3. ROLE POOL: every role name in any lens block must come from the list above.
4. Status flags for 🛒 Customers: use ONLY these four values:
   "Active funding" | "Active PO" | "Open RFP/RFI" | "Aspirational"
5. Chokepoint stage: use ONLY "Research", "Development", "Funding", "Implementation".
6. Bottom line: EXACTLY 3 sentences.
7. expert_lenses_top: EXACTLY 5 entries.
8. Each per_question_analysis entry: 2-3 role_takes."""


def synthesize_full(event_id: str, work_root: Path = Path("work")) -> Path:
    """Full M5: per-presentation + thematic Gemini calls + Evidence-grounded render."""
    from src.contracts import IngestResult
    from src.ingest import load_events_json

    client = _gemini_client()

    workdir = work_root / "events" / event_id

    # 1. Load all artifacts
    ing = IngestResult.model_validate_json(
        (workdir / util.STAGE_INGEST / "manifest.json").read_text())
    alignment = AlignmentResult.model_validate_json(
        (workdir / util.STAGE_ALIGNED / "aligned.json").read_text())
    ev_raw = json.loads((workdir / util.STAGE_ALIGNED / "evidence.json").read_text())
    evidence = [Evidence.model_validate(e) for e in ev_raw]
    ev_by_id = {e.evidence_id: e for e in evidence}

    captions: list[Caption] = []
    cap_path = workdir / util.STAGE_KEYFRAMES / "captions.json"
    if cap_path.exists():
        captions = [Caption.model_validate(c) for c in json.loads(cap_path.read_text())]

    # Identify host_deck asset_ids so we skip them in the presentation loop
    events, _ = load_events_json(work_root)
    event = next(e for e in events if e.event_id == event_id)
    host_deck_ids = {str(a.lsic_id) for a in event.assets if a.kind == "host_deck"}

    role_pool = _load_role_pool(Path("clai/.claude/Behavior/Roles.md"))
    deck_text_by_asset = _load_deck_text(workdir, event.assets)

    # 2. Per-presentation Claude calls (skip host_deck)
    guest_pres = [p for p in alignment.presentations if p.asset_id not in host_deck_ids]
    pres_outputs: list[dict] = []
    for p in guest_pres:
        print(f"  [synthesize] presentation {p.asset_id} ({int(p.start//60):02d}:"
              f"{int(p.start%60):02d}-{int(p.end//60):02d}:{int(p.end%60):02d})…",
              flush=True)
        out = _call_presentation(client, p, alignment, evidence,
                                 deck_text_by_asset.get(p.asset_id, ""))
        # carry presenter metadata through so the thematic call can reference it
        out["asset_id"] = p.asset_id
        out["window_start"] = p.start
        out["window_end"] = p.end
        pres_outputs.append(out)

    # 3. Thematic call (one big call assembling everything else)
    print("  [synthesize] thematic synthesis (1 big call)…", flush=True)
    thematic = _call_thematic(client, alignment, evidence, role_pool, pres_outputs)

    # 4. Slide highlights from has_diagram captions (deterministic pick)
    slide_highlights = _select_slide_highlights(captions, n=3)

    # 5. Render markdown
    n_speakers = len({s.speaker_id for sec in alignment.sections for s in []
                     if False}) or _count_speakers(workdir)
    notes_md = _render_briefing(
        ing=ing, alignment=alignment, pres_outputs=pres_outputs,
        thematic=thematic, slide_highlights=slide_highlights,
        evidence_by_id=ev_by_id, event_date=str(event.date),
        n_speakers=n_speakers,
    )

    # 6. Write with manifest
    out_path = workdir / util.STAGE_BRIEFING / "notes.md"
    util.write_with_manifest(out_path, notes_md, stage="synthesize")
    print(f"[synthesize] {event_id} → {out_path}", flush=True)
    return out_path


# --- helpers ---

def _count_speakers(workdir: Path) -> int:
    t_path = workdir / util.STAGE_TRANSCRIPT / "transcript.json"
    if not t_path.exists():
        return 0
    segs = json.loads(t_path.read_text())
    return len({s.get("speaker_id") for s in segs if s.get("speaker_id")})


def _load_role_pool(roles_md_path: Path) -> list[dict]:
    if not roles_md_path.exists():
        return []
    text = roles_md_path.read_text()
    return [
        {"name": m.group(1).strip(), "description": m.group(2).strip()}
        for m in re.finditer(r"^- \*\*([^*]+)\*\*\s+—\s+(.+)$", text, re.MULTILINE)
    ]


def _load_deck_text(workdir: Path, assets: list[Asset]) -> dict[str, str]:
    """Return {asset_id: concatenated_slide_text} for every deck."""
    out: dict[str, str] = {}
    decks_dir = workdir / util.STAGE_INGEST / "decks"
    for a in assets:
        d = decks_dir / str(a.lsic_id)
        idx = d / "slide_index.json"
        if not idx.exists():
            idx = d / "doc_index.json"
        if not idx.exists():
            continue
        data = json.loads(idx.read_text())
        slides = data.get("slides", [])
        out[str(a.lsic_id)] = "\n\n".join(
            f"Slide {s.get('n', '?')}:\n{s.get('text', '')}\n{s.get('speaker_notes', '')}".strip()
            for s in slides
        )
    return out


def _gemini_client() -> genai.Client:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")
    return genai.Client(api_key=api_key)


def _call_gemini_json(client: genai.Client, system: str, user: str,
                      max_tokens: int = 6000) -> dict:
    resp = client.models.generate_content(
        model=SYNTH_MODEL,
        contents=[user],
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        ),
    )
    raw = util.strip_fences(resp.text or "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        dump = Path("/tmp/synthesize_failed_response.txt")
        dump.write_text(raw)
        finish = getattr(resp.candidates[0], "finish_reason", "?") if resp.candidates else "?"
        truncated = str(finish) == "MAX_TOKENS"
        raise RuntimeError(
            f"Gemini returned invalid JSON "
            f"({'TRUNCATED at max_output_tokens' if truncated else e}); "
            f"full response dumped to {dump}"
        ) from e


def _call_presentation(client: genai.Client, p: Presentation,
                       alignment: AlignmentResult, evidence: list[Evidence],
                       deck_text: str) -> dict:
    # Pull transcript evidence inside this presentation's window
    in_window = [
        e for e in evidence
        if e.kind == "transcript" and p.start <= e.timestamp_start <= p.end
    ]
    lines = [
        f"[{util.mmss(e.timestamp_start)}] [{e.evidence_id}] "
        f"{e.speaker_id or '?'}: {e.text}"
        for e in in_window
    ]
    user = (
        f"=== PRESENTATION WINDOW ===\n"
        f"asset_id: {p.asset_id}\n"
        f"window: {util.mmss(p.start)} → {util.mmss(p.end)}\n"
        f"deck title hint: {p.title}\n"
        f"slide count: {p.slides_count}\n\n"
        f"=== TRANSCRIPT IN WINDOW ===\n" + "\n".join(lines) + "\n\n"
        f"=== DECK TEXT ===\n{deck_text[:6000]}\n\n"
        f"Produce the JSON object now."
    )
    try:
        return _call_gemini_json(client, PRES_SYSTEM_PROMPT, user, max_tokens=4000)
    except Exception as e:
        print(f"    [synthesize] presentation {p.asset_id} failed: {e}", flush=True)
        return {
            "title": p.title, "presenter": "unknown", "tldr": "",
            "key_claims": [], "open_questions": [],
            "trl": {"value": "", "basis": "", "confidence": "inferred"},
        }


def _call_thematic(client: genai.Client, alignment: AlignmentResult,
                   evidence: list[Evidence], role_pool: list[dict],
                   pres_outputs: list[dict]) -> dict:
    # Build compact context: section-summarized transcript with evidence markers
    ctx_lines = []
    transcript_ev = [e for e in evidence if e.kind == "transcript"]
    by_section: list[list[Evidence]] = [[] for _ in alignment.sections]
    for e in transcript_ev:
        for i, sec in enumerate(alignment.sections):
            if sec.start <= e.timestamp_start <= sec.end:
                by_section[i].append(e)
                break
    for i, (sec, evs) in enumerate(zip(alignment.sections, by_section)):
        ctx_lines.append(
            f"--- SECTION {i+1} [{util.mmss(sec.start)}-{util.mmss(sec.end)}] "
            f"speakers={sec.speakers} ---"
        )
        for e in evs:
            ctx_lines.append(f"[{e.evidence_id}] {e.speaker_id or '?'}: {e.text}")
    context = "\n".join(ctx_lines)
    # safety cap (Sonnet 4.6 has 200k context but we have other content too)
    context = context[:140_000]

    role_pool_lines = "\n".join(f"- {r['name']}" for r in role_pool)
    sys_prompt = THEMATIC_SYSTEM_PROMPT.replace("{role_pool}", role_pool_lines)

    pres_summary = "\n\n".join(
        f"--- PRESENTATION {p['asset_id']} ---\n{json.dumps(p, indent=2)[:1500]}"
        for p in pres_outputs
    )

    user = (
        f"=== EVENT CONTEXT (per-section transcript) ===\n{context}\n\n"
        f"=== PER-PRESENTATION OUTPUTS (from upstream calls) ===\n{pres_summary}\n\n"
        f"Produce the thematic JSON object now. Every cited evidence_id must be "
        f"present in the EVENT CONTEXT above."
    )
    return _call_gemini_json(client, sys_prompt, user, max_tokens=32000)


def _select_slide_highlights(captions: list[Caption], n: int = 3) -> list[Caption]:
    candidates = [c for c in captions
                  if c.has_diagram and c.visible_text.strip()
                  and c.caption_status == "ok"]
    if not candidates:
        return []
    if len(candidates) <= n:
        return candidates
    candidates.sort(key=lambda c: c.t)
    step = len(candidates) / n
    return [candidates[int(i * step)] for i in range(n)]


# --- markdown render ---

def _render_briefing(*, ing: IngestResult, alignment: AlignmentResult,
                     pres_outputs: list[dict], thematic: dict,
                     slide_highlights: list[Caption],
                     evidence_by_id: dict[str, Evidence],
                     event_date: str, n_speakers: int) -> str:
    def cite(eid: Optional[str]) -> str:
        if not eid:
            return ""
        e = evidence_by_id.get(eid)
        return f" `{util.mmss(e.timestamp_start)}`" if e else ""

    def bullet(b: dict) -> str:
        return f"- {b.get('text', '').strip()}{cite(b.get('evidence_id'))}"

    def lens(L: dict) -> str:
        emoji = L.get("emoji", "🔧")
        return f"- {emoji} **{L.get('role', '?')}** — {L.get('take', '').strip()}{cite(L.get('evidence_id'))}"

    duration_mmss = util.mmss(ing.duration_sec).strip("[]")
    out: list[str] = []

    # frontmatter
    out.append("---\n")
    out.append(f"event_id: {alignment.event_id}\n")
    out.append(f"date: {event_date}\n")
    out.append(f"title_inferred: \"{thematic.get('title', alignment.event_id)}\"\n")
    out.append(f"duration: \"{duration_mmss}\"\n")
    out.append(f"speakers_detected: {n_speakers}\n")
    out.append(f"languages: [en]\n")
    out.append(f"generated: {_date.today().isoformat()}\n")
    out.append("---\n\n")
    out.append(f"# {thematic.get('title', alignment.event_id)}\n\n")

    # 🎯 Bottom Line + 5 Lenses
    out.append("## 🎯 Bottom Line for C'mander Alex\n")
    out.append(f"{thematic.get('bottom_line', '').strip()}\n\n")
    out.append("### Through 5 Expert Lenses\n")
    out.append("*Roles selected from `clai/.claude/Behavior/Roles.md` based on event content.*\n\n")
    for L in thematic.get("expert_lenses_top", []):
        out.append(lens(L) + "\n")
    out.append("\n")

    # 🗂️ Contents (always 13 entries)
    out.append("## 🗂️ Contents\n")
    out.append(f"- 🎤 Presentations ({len(pres_outputs)})\n")
    for h in ["🔬 What's being done right now",
              "🛠️ Engineering system-design questions",
              "❓ Per-Question Role Analysis",
              "⚠️ Main engineering constraints",
              "💰 Funding landscape",
              "🛒 Paying Customers / Demand",
              "🚧 Chokepoints",
              "⚙️ Technology Readiness & Maturity (TRL)",
              "📐 Key equations & models",
              "🗣️ Speakers",
              "🔖 Citations & references mentioned",
              "📎 Slide highlights"]:
        out.append(f"- {h}\n")
    out.append("\n---\n\n")

    # 🎤 Presentations
    out.append("## 🎤 Presentations\n\n")
    for i, p in enumerate(pres_outputs, 1):
        out.append(f"### {i}. {p.get('title', '')} — {p.get('presenter', '')}\n")
        out.append(f"**TL;DR.** {p.get('tldr', '').strip()}\n\n")
        if p.get("key_claims"):
            out.append("**Key claims**\n")
            for c in p["key_claims"]:
                out.append(bullet(c) + "\n")
            out.append("\n")
        if p.get("open_questions"):
            out.append("**Open questions raised**\n")
            for q in p["open_questions"]:
                out.append(bullet(q) + "\n")
            out.append("\n")
        out.append("---\n\n")

    # 🔬 What's being done + lenses
    out.append("## 🔬 What's being done right now\n")
    for b in thematic.get("whats_being_done", []):
        out.append(bullet(b) + "\n")
    out.append("\n*Through Expert Lenses:*\n")
    for L in thematic.get("whats_being_done_lenses", []):
        out.append(lens(L) + "\n")
    out.append("\n")

    # 🛠️ Engineering questions + lenses
    out.append("## 🛠️ Engineering system-design questions\n")
    for b in thematic.get("eng_questions", []):
        out.append(bullet(b) + "\n")
    out.append("\n*Through Expert Lenses:*\n")
    for L in thematic.get("eng_questions_lenses", []):
        out.append(lens(L) + "\n")
    out.append("\n")

    # ❓ Per-Question Role Analysis
    out.append("## ❓ Per-Question Role Analysis\n\n")
    pqa = thematic.get("per_question_analysis", [])
    if pqa:
        for i, q in enumerate(pqa, 1):
            out.append(f"**{i}. {q.get('question', '').strip()}**{cite(q.get('evidence_id'))}\n")
            for t in q.get("role_takes", []):
                out.append(f"- {t.get('emoji', '🔧')} *{t.get('role', '?')}* — {t.get('take', '').strip()}\n")
            out.append("\n")
    else:
        out.append("*Not applicable to this event — no engineering questions surfaced.*\n\n")

    # ⚠️ Constraints
    out.append("## ⚠️ Main engineering constraints\n")
    for b in thematic.get("constraints", []):
        out.append(bullet(b) + "\n")
    out.append("\n")

    # 💰 Funding
    out.append("## 💰 Funding landscape\n")
    rows = thematic.get("funding", {}).get("rows", [])
    if rows:
        tbl = [["Org", "Mechanism", "Scale", "Focus", "Source"]]
        for r in rows:
            tbl.append([
                r.get("org", ""), r.get("mechanism", ""),
                r.get("scale", ""), r.get("focus", ""),
                cite(r.get("evidence_id")).strip() or "—",
            ])
        out.append(util.align_table(tbl) + "\n\n")
    else:
        out.append("*Not applicable to this event — no funding discussion identified.*\n\n")
    out.append("*Through Expert Lenses:*\n")
    for L in thematic.get("funding_lenses", []):
        out.append(lens(L) + "\n")
    out.append("\n")

    # 🛒 Customers
    out.append("## 🛒 Paying Customers / Demand\n")
    cust = thematic.get("customers", {})
    if cust.get("intro"):
        out.append(f"{cust['intro'].strip()}\n\n")
    rows = cust.get("rows", [])
    if rows:
        tbl = [["Customer", "Procurement mechanism", "Status", "Spend horizon", "Source"]]
        for r in rows:
            tbl.append([
                r.get("customer", ""), r.get("mechanism", ""),
                r.get("status", ""), r.get("horizon", ""),
                cite(r.get("evidence_id")).strip() or "—",
            ])
        out.append(util.align_table(tbl) + "\n\n")
        out.append("Status flags: `Active funding` · `Active PO` · `Open RFP/RFI` · `Aspirational`.\n\n")
    else:
        out.append("*Not applicable to this event — no procurement-side discussion identified.*\n\n")

    # 🚧 Chokepoints
    out.append("## 🚧 Chokepoints\n")
    rows = thematic.get("chokepoints", {}).get("rows", [])
    if rows:
        tbl = [["Stage", "Chokepoint", "Source"]]
        for r in rows:
            tbl.append([
                r.get("stage", ""), r.get("chokepoint", ""),
                cite(r.get("evidence_id")).strip() or "—",
            ])
        out.append(util.align_table(tbl) + "\n\n")
    else:
        out.append("*Not applicable to this event — no chokepoints surfaced.*\n\n")

    # ⚙️ TRL (aggregated from pres_outputs)
    out.append("## ⚙️ Technology Readiness & Maturity (TRL)\n")
    trl_tbl = [["Technology", "TRL", "Basis", "Confidence", "Source"]]
    for p in pres_outputs:
        trl = p.get("trl") or {}
        if trl.get("value"):
            trl_tbl.append([
                (p.get("title") or "")[:60], trl.get("value", ""),
                trl.get("basis", ""), trl.get("confidence", "inferred"),
                "—",
            ])
    if len(trl_tbl) > 1:
        out.append(util.align_table(trl_tbl) + "\n\n")
    else:
        out.append("*Not applicable to this event — no technology TRL discussed.*\n\n")

    # 📐 Equations
    out.append("## 📐 Key equations & models\n")
    eqs = thematic.get("equations")
    if eqs:
        for eq in eqs:
            out.append(f"{eq}\n\n")
    else:
        out.append("*Not applicable to this event — no equations identified.*\n\n")

    # 🗣️ Speakers
    out.append("## 🗣️ Speakers\n")
    spkrs = thematic.get("speakers", [])
    if spkrs:
        for s in spkrs:
            tr = f" `[{s.get('time_range')}]`" if s.get("time_range") else ""
            out.append(f"- **{s.get('label', '?')}** — {s.get('role', 'unknown')}{tr}\n")
    else:
        out.append("*Not applicable to this event.*\n")
    out.append("\n")

    # 🔖 Citations
    out.append("## 🔖 Citations & references mentioned\n")
    cits = thematic.get("citations", [])
    if cits:
        for c in cits:
            if isinstance(c, dict):
                out.append(bullet(c) + "\n")
            else:
                out.append(f"- {c}\n")
    else:
        out.append("*Not applicable to this event.*\n")
    out.append("\n")

    # 📎 Slide highlights
    out.append("## 📎 Slide highlights\n")
    if slide_highlights:
        briefing_dir = ing.workdir / util.STAGE_BRIEFING
        for sh in slide_highlights:
            rel = os.path.relpath(str(sh.frame_path), str(briefing_dir))
            cap_txt = sh.visible_text.replace("\n", " ").strip()[:140]
            out.append(f"![{cap_txt}]({rel})\n")
            out.append(f"*{cap_txt}* `{util.mmss(sh.t)}`\n\n")
    else:
        out.append("*Not applicable to this event — no diagram-bearing keyframes selected.*\n\n")

    return "".join(out)


def synthesize(*args, **kwargs):
    """Alias for synthesize_full (the M5 entry point)."""
    return synthesize_full(*args, **kwargs)


def synthesize_paper(*args, **kwargs):
    raise NotImplementedError("synthesize_paper lands at M5b — see PLAN.md")
