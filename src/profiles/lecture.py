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
  "notable_claims": [{"text": "<a specific claim>", "basis": "<one-line basis/evidence shown>", "status": "<consensus|his bet|contested|his frame>", "evidence_id": "ev_..."}],
  "open_questions": [{"text": "<an unresolved question raised>", "evidence_id": "ev_..."}],
  "takeaways":      [{"text": "<an actionable takeaway for the viewer>", "evidence_id": "ev_..."}],
  "field_implications": [{"text": "<what someone working IN this field should transition toward, or a skill/competency the speakers say or imply practitioners need to gain>", "evidence_id": "ev_..."}],
  "industry_outlook": {
    "fading":   [{"text": "<an approach/tool/role/market the speakers say or imply is declining or being displaced>", "evidence_id": "ev_..."}],
    "thriving": [{"text": "<an approach/tool/role/market the speakers say or imply is growing or will dominate>", "evidence_id": "ev_..."}]
  },
  "speakers":       [{"label": "A", "role": "<role/identity if inferable>", "time_range": "00:00→04:30"}],
  "citations":      [{"text": "<a paper/tool/dataset/standard the speaker cited>", "evidence_id": "ev_..."}],
  "operating_algorithm": {"arrow_chain": "<the speaker's repeatable reasoning PROCEDURE as a → chain — the procedure that generates their conclusions, NOT the conclusions>", "tags": ["<2-4 move-tags from the EXPLAINER set>"]},
  "cognitive_moves": [{"move": "<short paraphrase/quote of a repeatable mental move>", "tag": "<one EXPLAINER move-tag>", "work": "<what the move DOES to the listener's model>", "evidence_id": "ev_..."}],
  "what_doesnt_transfer": "<one line: which of the speaker's positions are bets/taste vs durable mechanisms>",
  "transfer_questions": [{"prompt": "<reusable question for the READER DOMAIN>", "from_move": "<which move it derives from>", "evidence_id": "ev_..."}]
}

FIELD IMPLICATIONS & INDUSTRY OUTLOOK: extract these even when the speakers only IMPLY them
(e.g. "we've moved entirely to X" implies the old approach is fading and X is thriving; "you
really need to understand Y now" implies a skill to gain). Be concrete about what to learn or
pivot to. If the talk genuinely has no such signal, use an empty list.

EXPERT LENSES: choose 3-5 perspectives that genuinely fit this video's subject (e.g. an ML talk →
ML researcher, systems engineer, practitioner; a history talk → historian, primary-source archivist,
economist). Make each take substantive and distinct, not generic praise.

THINKING PROCESS — extract HOW the speaker reasons, not just what they said:
- operating_algorithm: the speaker's repeatable reasoning PROCEDURE as one arrow-chain (the steps that
  generate their conclusions), then 2-4 dominant move-tags. NOT a list of conclusions.
- cognitive_moves: 4-7 repeatable mental moves. For each, tag the OPERATION (not the topic) and say what
  work the move does on the listener's model. Use ONLY the EXPLAINER tag set:
  Analogy, Reframe, Mechanism, Base-rate, Inversion, Sequencing, First-principles, Distinction.

EPISTEMIC STATUS (survivorship guard): for each notable_claim set "status" to one of consensus / his bet /
contested / his frame. Then set what_doesnt_transfer to ONE line separating the speaker's bets & taste
(hold loosely) from their durable mechanisms (the transferable part).

TRANSFER QUESTIONS: convert the cognitive moves into reusable questions for the READER DOMAIN given below.
If no READER DOMAIN is provided, return an empty transfer_questions list.

CITATION RULE: every evidence_id MUST be one that appears in the EVENT CONTEXT provided. Never invent
an evidence_id. A section with no support → an empty list (it renders as "Not applicable to this talk.").
Be specific and technical. Produce the JSON now."""


def thematic_prompt() -> str:
    """The lecture thematic system prompt, with the READER DOMAIN (env ``READER_DOMAIN``) woven in for
    Transfer Questions (section D). No env set ⇒ instruct an empty list ⇒ the section is omitted."""
    rd = os.environ.get("READER_DOMAIN", "").strip()
    if rd:
        tail = (f"\n\nREADER DOMAIN: {rd}\nGenerate 3-5 transfer_questions converting the cognitive moves "
                f"into questions a practitioner in this domain should ask themselves; ground each in an "
                f"evidence_id where possible.")
    else:
        tail = "\n\nREADER DOMAIN: (none) — return an empty transfer_questions list."
    return THEMATIC_SYSTEM_PROMPT + tail


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
        rows = [f"- **{m.get('move', '').strip()}** — *{m.get('tag', '?')}* — "
                f"{m.get('work', '').strip()}{cite(m.get('evidence_id'))}" for m in moves]
        return ["## Cognitive Moves", *rows, ""]

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
        *section(thematic.get("notable_claims", []),
                 fmt=lambda b: b.get("text", "").strip()
                 + (f" — {b['basis'].strip()}" if b.get("basis") else "")
                 + (f" `[{b['status'].strip()}]`" if b.get("status") else "")), "",  # C — status
        *wdt_lines(),                                          # C — what doesn't transfer
        "## Open Questions", *section(thematic.get("open_questions", [])), "",
        "## Takeaways", *section(thematic.get("takeaways", [])), "",
        *transfer_lines(),                                     # D — Transfer Questions
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
