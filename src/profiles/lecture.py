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


# DEPTH v2: the dedicated COGNITION call (how the speaker thinks). Its own focused pass so the
# inferential work isn't crowded out by the ~11 descriptive fields. Routed to Opus 4.8 by default.
COGNITION_SYSTEM_PROMPT = """You analyze HOW a speaker thinks in a talk/lecture transcript — the repeatable mental operations behind the content, not just what was said. You are given the EVENT CONTEXT: a per-section transcript with [ev_...] evidence markers.

Output ONLY a single JSON object with EXACTLY this shape (no prose, no code fences):
{
  "operating_algorithm": {"arrow_chain": "<the speaker's reasoning PROCEDURE as a → chain>", "tags": ["<2-4 EXPLAINER tags>"]},
  "cognitive_moves": [{"move": "<short quote/paraphrase>", "tag": "<one EXPLAINER tag>", "work": "<what the move does to the listener's model>", "evidence_id": "ev_..."}],
  "claim_epistemics": [{"evidence_id": "<ev_... of a load-bearing claim present in the EVENT CONTEXT>", "status": "<consensus|his bet|contested|his frame>", "when_it_fails": "<the boundary condition where this claim/play backfires + who has run it and lost>"}],
  "what_doesnt_transfer": "<one line: which positions are bets/taste vs durable mechanisms>",
  "transfer_questions": [{"prompt": "<reusable question for the READER DOMAIN>", "from_move": "<which move it derives from>", "evidence_id": "ev_..."}]
}

OPERATING ALGORITHM: one arrow-chain capturing the speaker's IDIOSYNCRATIC, TRANSFERABLE reasoning
signature — the repeatable procedure that GENERATES their conclusions. This is NOT a talk outline or
topic sequence. If your chain reads like "intro → background → method → results", you have described
the TALK, not the THINKING — redo it as the distinctive moves only THIS speaker runs. End with 2-4
dominant move-tags.

COGNITIVE MOVES: 4-7 entries. Tag the OPERATION, not the topic. For each, say what WORK the move does
on the listener's model (what it swaps / collapses / maps / flips / re-anchors). Use ONLY the EXPLAINER
tag set: Analogy, Reframe, Mechanism, Base-rate, Inversion, Sequencing, First-principles, Distinction.

EPISTEMIC STATUS (survivorship guard): you are given a CLAIMS TO TAG list below (each is an [evidence_id]
plus the claim text). Emit ONE claim_epistemic per listed claim, keyed by that exact evidence_id (so the
judgement overlays the right claim). status ∈ consensus / his bet / contested / his frame. when_it_fails =
the boundary condition where this claim/play BACKFIRES, and who has run the same play and lost — reason
from your OWN knowledge, NO external lookup. Then what_doesnt_transfer = ONE line separating the speaker's
bets & taste (hold loosely) from their durable mechanisms (the transferable part).

TRANSFER QUESTIONS: convert the cognitive moves into reusable self-questions for the READER DOMAIN given
below — ONE question per major move, each tied to its move and grounded in an evidence_id where possible.
If no READER DOMAIN is provided, return an empty list.

VERBOSITY: match the Cognitive Moves level — one substantive sentence per item, no padding.

CITATION RULE: every evidence_id MUST appear in the EVENT CONTEXT. Never invent one. No support → an
empty list. Produce the JSON now."""


def thematic_prompt() -> str:
    """The lecture DESCRIPTIVE system prompt (the cognition fields moved to the dedicated cognition
    call — see ``cognition_prompt``)."""
    return THEMATIC_SYSTEM_PROMPT


def cognition_prompt(reader_domain: str = "", current_work: str = "") -> str:
    """The dedicated cognition system prompt, with READER DOMAIN + optional CURRENT WORK woven in for
    the Transfer Questions. No reader domain (arg or env ``READER_DOMAIN``) ⇒ an empty
    transfer_questions list ⇒ that section is omitted. ``CURRENT_WORK`` (arg or env) sharpens the
    questions from domain-level to project-level."""
    rd = (reader_domain or os.environ.get("READER_DOMAIN", "")).strip()
    cw = (current_work or os.environ.get("CURRENT_WORK", "")).strip()
    if not rd:
        tail = "\n\nREADER DOMAIN: (none) — return an empty transfer_questions list."
    else:
        tail = f"\n\nREADER DOMAIN: {rd}"
        if cw:
            tail += ("\nCURRENT WORK (sharpen each transfer_question from domain-level to PROJECT-level "
                     f"against this): {cw}")
    return COGNITION_SYSTEM_PROMPT + tail


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
