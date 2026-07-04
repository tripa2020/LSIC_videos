"""Generic "talk" profile — one structured template for any YouTube/other video.

Per the EASYRUN template architecture (2026-06-11): a single generic template (not per-type
variants); it KEEPS the briefing's signature multi-perspective analysis as "Through N Expert
Lenses" — but **domain-adapted** (the model self-selects perspectives relevant to THIS video,
so it works on any subject, not just robotics). For YouTube sources it also mines native
metadata: chapters → an Outline timeline, and description links → References.

No funding/customers/chokepoints/TRL, no host-deck presentations, no fixed role pool. One
thematic Gemini call. Same evidence-grounding rule: every `[mm:ss]` resolves a transcript
``evidence_id``.
"""
from __future__ import annotations

import os
import re
from datetime import date as _date
from typing import Callable

from src import util

_URL_RE = re.compile(r"https?://[^\s<>)\"']+")

# DEPTH v2: the DESCRIPTIVE call (what was said). The cognition fields moved to a dedicated
# focused call — see COGNITION_SYSTEM_PROMPT / cognition_prompt below.
THEMATIC_SYSTEM_PROMPT = """You distill a talk / lecture / video transcript (plus any slide text) into a concise, structured briefing for a curious technical viewer.

Output ONLY a single JSON object with EXACTLY this shape:
{
  "title": "<inferred title, ~6-12 words>",
  "summary": "<3-5 sentence abstract of what the video covers and concludes>",
  "expert_lenses": [
    {"role": "<an expert perspective RELEVANT TO THIS VIDEO'S DOMAIN>", "emoji": "<one fitting emoji>",
     "take": "<that expert's 1-2 sentence take on the content>", "evidence_id": "ev_..."}
  ],
  "key_points":     [{"text": "<a main point made>", "evidence_id": "ev_..."}],
  "methods":        [{"text": "<a method / approach / technique used or described>", "evidence_id": "ev_..."}],
  "notable_claims": [{"text": "<a specific load-bearing claim>", "basis": "<one-line basis/evidence shown>", "evidence_id": "ev_..."}],
  "open_questions": [{"text": "<an unresolved question raised>", "evidence_id": "ev_..."}],
  "takeaways":      [{"text": "<an actionable takeaway for the viewer>", "evidence_id": "ev_..."}],
  "field_implications": [{"text": "<what someone working IN this field should transition toward, or a skill/competency the speakers say or imply practitioners need to gain>", "evidence_id": "ev_..."}],
  "industry_outlook": {
    "fading":   [{"text": "<an approach/tool/role/market the speakers say or imply is declining or being displaced>", "evidence_id": "ev_..."}],
    "thriving": [{"text": "<an approach/tool/role/market the speakers say or imply is growing or will dominate>", "evidence_id": "ev_..."}]
  },
  "speakers":       [{"label": "A", "role": "<role/identity if inferable>", "time_range": "00:00→04:30"}],
  "citations":      [{"text": "<a paper/tool/dataset/standard the speaker cited>", "evidence_id": "ev_..."}]
}

FIELD IMPLICATIONS & INDUSTRY OUTLOOK: extract these even when the speakers only IMPLY them
(e.g. "we've moved entirely to X" implies the old approach is fading and X is thriving; "you
really need to understand Y now" implies a skill to gain). Be concrete about what to learn or
pivot to. If the talk genuinely has no such signal, use an empty list.

EXPERT LENSES: choose 3-5 perspectives that genuinely fit this video's subject (e.g. an ML talk →
ML researcher, systems engineer, practitioner; a history talk → historian, primary-source archivist,
economist). Make each take substantive and distinct, not generic praise.

CITATION RULE: every evidence_id MUST be one that appears in the EVENT CONTEXT provided. Never invent
an evidence_id. A section with no support → an empty list (it renders as "Not applicable to this talk.").
Be specific and technical. Produce the JSON now."""


# DEPTH v3: the cognition prompts (extract + convert) live in src/cognition.py — the dedicated
# two-pass cognitive core. This profile keeps the DESCRIPTIVE prompt + the render.


def thematic_prompt() -> str:
    """The lecture DESCRIPTIVE system prompt (the cognition layer is src/cognition.py)."""
    return THEMATIC_SYSTEM_PROMPT


def render_lecture(*, ing, alignment, pres_outputs, thematic: dict, slide_highlights,
                   evidence_by_id, event_date: str, n_speakers: int,
                   source_meta: dict | None = None) -> str:
    """Render the generic talk notes.md. Shares synthesize._render_briefing's kwargs (some
    unused) plus ``source_meta`` (YouTube metadata: chapters + description) for the Outline +
    description-link references."""
    source_meta = source_meta or {}

    def cite(eid) -> str:
        if not eid:
            return ""
        e = evidence_by_id.get(eid)
        return f" `{util.mmss(e.timestamp_start)}`" if e else ""

    def section(items, fmt: Callable[[dict], str] = lambda b: b.get("text", "").strip()) -> list[str]:
        if not items:
            return ["*Not applicable to this talk.*"]
        return [f"- {fmt(b)}{cite(b.get('evidence_id'))}" for b in items]

    def lens(L: dict) -> str:
        return (f"- {L.get('emoji', '🔍')} **{L.get('role', '?')}** — "
                f"{L.get('take', '').strip()}{cite(L.get('evidence_id'))}")

    # --- cognition layer (additive; each section omitted when its field is empty) ---
    def algo_lines() -> list[str]:
        a = thematic.get("operating_algorithm") or {}
        chain = (a.get("arrow_chain") or "").strip()
        if not chain:
            return []
        tags = " · ".join(t for t in a.get("tags", []) if t)
        return ["## Operating Algorithm", chain + (f"\n\n*Tags: {tags}*" if tags else ""), ""]

    def moves_lines() -> list[str]:
        moves = thematic.get("cognitive_moves") or []
        if not moves:
            return []
        rows: list[str] = []
        for m in moves:
            rows.append(f"- **{m.get('move', '').strip()}** — *{m.get('tag', '?')}* — "
                        f"{m.get('work', '').strip()}{cite(m.get('evidence_id'))}")
            # v3 sub-lines — each omitted when absent (pre-v3 bundles render unchanged)
            if (m.get("quote") or "").strip():
                rows.append(f"  > “{m['quote'].strip()}”")
            if (m.get("fails_when") or "").strip():
                rows.append(f"  ↳ *fails when:* {m['fails_when'].strip()}")
            if (m.get("self_question") or "").strip():
                rows.append(f"  ↳ *ask yourself:* {m['self_question'].strip()}")
        return ["## Cognitive Moves", *rows, ""]

    def founder_lines() -> list[str]:
        plays = thematic.get("founder_lens") or []
        if not plays:
            return []
        rows: list[str] = ["## Founder Lens — To Market"]
        for p in plays:
            rows.append(f"### {p.get('idea', '').strip()}{cite(p.get('evidence_id'))}")
            frm = ", ".join(x for x in (p.get("from_moves") or []) if x)
            if frm:
                rows.append(f"*From: {frm}*")
            rows.append(f"- **Wedge:** {p.get('wedge', '').strip()}")
            rows.append(f"- **Action (Monday morning):** {p.get('action', '').strip()}")
            rows.append(f"- **Learn:** {p.get('learn', '').strip()}")
            rows.append(f"- **Go deeper:** {p.get('deeper', '').strip()}")
            rows.append("")
        return rows

    def learnit_lines() -> list[str]:
        li = thematic.get("learn_it") or {}
        prompts = li.get("retrieval_prompts") or []
        terms = [t for t in (li.get("first_order_terms") or []) if t]
        artifact = (li.get("buildable_artifact") or "").strip()
        if not (prompts or terms or artifact):
            return []
        rows: list[str] = ["## How to Learn It (So It Sticks)"]
        if terms:
            rows += [f"**First-order terms:** {' · '.join(terms)}", ""]
        if prompts:
            rows.append("**Retrieval prompts** *(cover the answer, recall from memory, check)*")
            for rp in prompts:
                rows.append(f"- Q: {rp.get('q', '').strip()}{cite(rp.get('evidence_id'))}")
                rows.append(f"  A: {rp.get('a', '').strip()}")
            rows.append("")
        if artifact:
            rows += [f"**Build to internalize:** {artifact}", ""]
        return rows

    def wdt_lines() -> list[str]:
        w = (thematic.get("what_doesnt_transfer") or "").strip()
        return [f"**What doesn't transfer:** {w}", ""] if w else []

    def transfer_lines() -> list[str]:
        qs = thematic.get("transfer_questions") or []
        if not qs:
            return []
        rows = [f"- {q.get('prompt', '').strip()}"
                + (f"  *(from: {q['from_move'].strip()})*" if q.get('from_move') else "")
                + cite(q.get('evidence_id')) for q in qs]
        return ["## Transfer Questions", *rows, ""]

    # epistemic overlay from the cognition call, matched to descriptive claims by evidence_id
    _epi = {e.get("evidence_id"): e for e in (thematic.get("claim_epistemics") or [])
            if e.get("evidence_id")}

    def claims_lines() -> list[str]:
        """Descriptive Notable Claims, overlaid with the cognition call's epistemic status +
        'fails when' survivorship sub-line (matched by evidence_id). Any cognition epistemic that
        matched NO descriptive claim is surfaced as its own note rather than silently dropped, so
        the survivorship analysis always reaches the reader."""
        claims = thematic.get("notable_claims") or []
        matched: set = set()
        rows: list[str] = []
        for b in claims:
            eid = b.get("evidence_id")
            o = _epi.get(eid, {})
            if o:
                matched.add(eid)
            line = "- " + b.get("text", "").strip()
            if b.get("basis"):
                line += f" — {b['basis'].strip()}"
            if o.get("status"):
                line += f" `[{o['status'].strip()}]`"
            rows.append(line + cite(eid))
            if o.get("when_it_fails"):
                rows.append(f"  ↳ *fails when:* {o['when_it_fails'].strip()}")
        for e in (thematic.get("claim_epistemics") or []):   # orphaned epistemics → keep the analysis
            eid = e.get("evidence_id")
            if eid in matched or not (e.get("status") or e.get("when_it_fails")):
                continue
            tag = f" `[{e['status'].strip()}]`" if e.get("status") else ""
            rows.append(f"- *(epistemic note)*{tag}{cite(eid)}")
            if e.get("when_it_fails"):
                rows.append(f"  ↳ *fails when:* {e['when_it_fails'].strip()}")
        return rows or ["*Not applicable to this talk.*"]

    title = thematic.get("title") or getattr(alignment, "event_id", "Untitled")
    dur = util.mmss(ing.duration_sec).strip("[]")
    lenses = thematic.get("expert_lenses", [])

    out: list[str] = [
        "---",
        f"event_id: {getattr(alignment, 'event_id', '')}",
        f"date: {event_date}",
        f'title_inferred: "{title}"',
        f'duration: "{dur}"',
        f"speakers_detected: {n_speakers}",
        "languages: [en]",
        f"generated: {_date.today().isoformat()}",
        "profile: lecture",
        "---\n",
        f"# {title}\n",
        # v3: a degraded cognition layer is VISIBLE, never silent (empty status → no line)
        *([f"> ⚠️ *cognition degraded:* {(thematic.get('cognition_status') or '').strip()}\n"]
          if (thematic.get("cognition_status") or "").strip() else []),
        "## Summary",
        (thematic.get("summary") or "*Not applicable to this talk.*") + "\n",
        *algo_lines(),                                          # A — Operating Algorithm
        f"## Through {len(lenses)} Expert Lenses" if lenses else "## Through Expert Lenses",
        *([lens(L) for L in lenses] or ["*Not applicable to this talk.*"]), "",
        *moves_lines(),                                         # B — Cognitive Moves
    ]

    # Outline from YouTube chapters (if present) — a timeline anchor; omitted otherwise.
    chapters = source_meta.get("chapters") or []
    if chapters:
        out.append("## Outline")
        for ch in chapters:
            ts = util.mmss(ch.get("start_time", 0) or 0)
            out.append(f"- **{str(ch.get('title', '')).strip()}** `{ts}`")
        out.append("")

    out += [
        "## Key Points", *section(thematic.get("key_points", [])), "",
        "## Methods / Approach", *section(thematic.get("methods", [])), "",
        "## Notable Claims & Evidence",
        *claims_lines(), "",                                  # C — claims + status + when_it_fails
        *wdt_lines(),                                          # C — what doesn't transfer
        "## Open Questions", *section(thematic.get("open_questions", [])), "",
        "## Takeaways", *section(thematic.get("takeaways", [])), "",
        *transfer_lines(),                                     # D — Transfer Questions (pre-v3)
        *founder_lines(),                                      # D' — Founder Lens (v3)
        *learnit_lines(),                                      # E — How to Learn It (v3)
        "## Field Implications — Where to Steer",
        *section(thematic.get("field_implications", [])), "",
        *_outlook_lines(thematic.get("industry_outlook") or {}, section), "",
        "## Speakers",
    ]
    speakers = thematic.get("speakers", [])
    if speakers:
        out += [f"- **{s.get('label', '?')}** — {s.get('role', '').strip()} `{s.get('time_range', '')}`"
                for s in speakers]
    else:
        out.append("*Not applicable to this talk.*")

    # References: transcript-cited resources + harvested description links.
    out += ["", "## References & Resources Mentioned", *section(thematic.get("citations", []))]
    desc_links = _dedupe(_URL_RE.findall(source_meta.get("description") or ""))
    for url in desc_links:
        out.append(f"- {url.rstrip('.,);')}  *(from video description)*")
    out.append("")
    return "\n".join(out)


def _outlook_lines(outlook: dict, section) -> list[str]:
    """Render the Industry Outlook block (fading vs thriving). ``section`` is the caller's
    evidence-grounded bullet renderer. Both empty → a single 'Not applicable' line."""
    fading = outlook.get("fading", []) if isinstance(outlook, dict) else []
    thriving = outlook.get("thriving", []) if isinstance(outlook, dict) else []
    lines = ["## Industry Outlook — Fading vs Thriving"]
    if not fading and not thriving:
        return lines + ["*Not applicable to this talk.*"]
    lines.append("**📉 Fading**")
    lines += section(fading)
    lines += ["", "**📈 Thriving**"]
    lines += section(thriving)
    return lines


def _dedupe(items: list[str]) -> list[str]:
    seen, keep = set(), []
    for x in items:
        x = x.rstrip(".,);")
        if x not in seen:
            seen.add(x)
            keep.append(x)
    return keep
