"""Paper profile — the notes template for a standalone research paper (arXiv PDF etc.).

Structurally the lecture profile's twin: one descriptive pass (this prompt) + the DEPTH v3
cognition core (``src/cognition.py`` — operating algorithm, cognitive moves, Founder Lens,
Learn-It), rendered into the same notes.md shape Alex reads for talks. Two paper-specific
differences:

- **Citations are pages, not times.** ``paper_align`` encodes the page number in
  ``Evidence.timestamp_start``; ``cite()`` here renders it as ``[p.N]``, and the frontmatter
  carries ``pages: N`` + ``profile: paper`` so ``synth_eval``'s page mode scores the same
  gates (decile spread across the paper, final-third coverage) in page units.
- **No speakers / chapters / description links** — those blocks are omitted, and References
  leads with the paper's own source URL.

The descriptive JSON shape deliberately mirrors the lecture profile (same keys) so the MAPRED
reduce, the cognition overlay (claims by evidence_id), and the eval all work unchanged.
"""
from __future__ import annotations

from datetime import date as _date
from typing import Callable

# The DESCRIPTIVE call (what the paper says). Cognition fields come from src/cognition.py.
THEMATIC_SYSTEM_PROMPT = """You distill a research paper (given as per-page text) into a concise, structured briefing for a technical reader deciding whether and how to act on it.

Output ONLY a single JSON object with EXACTLY this shape:
{
  "title": "<the paper's title>",
  "summary": "<3-5 sentence abstract: the problem, the approach, and what was demonstrated>",
  "expert_lenses": [
    {"role": "<an expert perspective RELEVANT TO THIS PAPER'S DOMAIN>", "emoji": "<one fitting emoji>",
     "take": "<that expert's 1-2 sentence take on the work>", "evidence_id": "ev_..."}
  ],
  "key_points":     [{"text": "<a main point or contribution>", "evidence_id": "ev_..."}],
  "methods":        [{"text": "<a method / architecture / algorithm / experimental setup used>", "evidence_id": "ev_..."}],
  "notable_claims": [{"text": "<a specific load-bearing claim or result>", "basis": "<one-line basis: the experiment/benchmark/proof behind it>", "evidence_id": "ev_..."}],
  "open_questions": [{"text": "<a limitation the authors admit, or a question the paper leaves open>", "evidence_id": "ev_..."}],
  "takeaways":      [{"text": "<an actionable takeaway for the reader>", "evidence_id": "ev_..."}],
  "field_implications": [{"text": "<what someone working IN this field should transition toward, or a skill/competency this work implies practitioners need>", "evidence_id": "ev_..."}],
  "industry_outlook": {
    "fading":   [{"text": "<an approach/tool/pipeline this work implies is declining or being displaced>", "evidence_id": "ev_..."}],
    "thriving": [{"text": "<an approach/tool/market this work implies is growing or will dominate>", "evidence_id": "ev_..."}]
  },
  "citations":      [{"text": "<a paper/tool/dataset/benchmark this paper builds on or compares against>", "evidence_id": "ev_..."}]
}

RESULTS DISCIPLINE: for notable_claims prefer NUMBERS (benchmark scores, success rates, ablation deltas) with their exact values; the "basis" names the table/experiment. Never round away a reported number.

EXPERT LENSES: choose 3-5 perspectives that genuinely fit this paper's subject (e.g. a controls paper → control theorist, systems integrator, safety engineer). Make each take substantive and distinct, not generic praise.

CITATION RULE: every evidence_id MUST be one that appears in the EVENT CONTEXT provided (they are per-page: ev_p012 = page 12). Never invent an evidence_id. A section with no support → an empty list (it renders as "Not applicable to this paper.").
Be specific and technical. Produce the JSON now."""

_NA = "*Not applicable to this paper.*"


def thematic_prompt() -> str:
    """The paper DESCRIPTIVE system prompt (the cognition layer is src/cognition.py)."""
    return THEMATIC_SYSTEM_PROMPT


def render_paper(*, ing, alignment, pres_outputs, thematic: dict, slide_highlights,
                 evidence_by_id, event_date: str, n_speakers: int,
                 source_meta: dict | None = None) -> str:
    """Render the paper notes.md. Shares synthesize's uniform render kwargs (some unused);
    ``source_meta`` is the event meta (source URL + title) for video-less events."""
    source_meta = source_meta or {}
    n_pages = int(alignment.duration_sec or 0)

    def cite(eid) -> str:
        if not eid:
            return ""
        e = evidence_by_id.get(eid)
        return f" `[p.{int(e.timestamp_start)}]`" if e else ""

    def section(items, fmt: Callable[[dict], str] = lambda b: b.get("text", "").strip()) -> list[str]:
        if not items:
            return [_NA]
        return [f"- {fmt(b)}{cite(b.get('evidence_id'))}" for b in items]

    def lens(L: dict) -> str:
        return (f"- {L.get('emoji', '🔍')} **{L.get('role', '?')}** — "
                f"{L.get('take', '').strip()}{cite(L.get('evidence_id'))}")

    # --- cognition layer (same blocks as the lecture render, page-cited) ---
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

    _epi = {e.get("evidence_id"): e for e in (thematic.get("claim_epistemics") or [])
            if e.get("evidence_id")}

    def claims_lines() -> list[str]:
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
        for e in (thematic.get("claim_epistemics") or []):   # orphaned epistemics → keep them
            eid = e.get("evidence_id")
            if eid in matched or not (e.get("status") or e.get("when_it_fails")):
                continue
            tag = f" `[{e['status'].strip()}]`" if e.get("status") else ""
            rows.append(f"- *(epistemic note)*{tag}{cite(eid)}")
            if e.get("when_it_fails"):
                rows.append(f"  ↳ *fails when:* {e['when_it_fails'].strip()}")
        return rows or [_NA]

    title = thematic.get("title") or source_meta.get("title") \
        or getattr(alignment, "event_id", "Untitled")
    lenses = thematic.get("expert_lenses", [])
    source = (source_meta.get("source") or "").strip()

    out: list[str] = [
        "---",
        f"event_id: {getattr(alignment, 'event_id', '')}",
        f"date: {event_date}",
        f'title_inferred: "{title}"',
        f"pages: {n_pages}",
        "languages: [en]",
        f"generated: {_date.today().isoformat()}",
        "profile: paper",
        "---\n",
        f"# {title}\n",
        *([f"**Source:** {source}\n"] if source else []),
        "*Citations are page numbers: `[p.N]` = page N of the PDF.*\n",
        *([f"> ⚠️ *cognition degraded:* {(thematic.get('cognition_status') or '').strip()}\n"]
          if (thematic.get("cognition_status") or "").strip() else []),
        "## Summary",
        (thematic.get("summary") or _NA) + "\n",
        *algo_lines(),
        f"## Through {len(lenses)} Expert Lenses" if lenses else "## Through Expert Lenses",
        *([lens(L) for L in lenses] or [_NA]), "",
        *moves_lines(),
        "## Key Points", *section(thematic.get("key_points", [])), "",
        "## Methods / Approach", *section(thematic.get("methods", [])), "",
        "## Notable Claims & Evidence",
        *claims_lines(), "",
        *wdt_lines(),
        "## Open Questions", *section(thematic.get("open_questions", [])), "",
        "## Takeaways", *section(thematic.get("takeaways", [])), "",
        *transfer_lines(),
        *founder_lines(),
        *learnit_lines(),
        "## Field Implications — Where to Steer",
        *section(thematic.get("field_implications", [])), "",
        *_outlook_lines(thematic.get("industry_outlook") or {}, section), "",
        "## References & Resources Cited",
        *section(thematic.get("citations", [])),
        "",
    ]
    return "\n".join(out)


def _outlook_lines(outlook: dict, section) -> list[str]:
    """Render the Industry Outlook block (fading vs thriving), paper wording."""
    fading = outlook.get("fading", []) if isinstance(outlook, dict) else []
    thriving = outlook.get("thriving", []) if isinstance(outlook, dict) else []
    lines = ["## Industry Outlook — Fading vs Thriving"]
    if not fading and not thriving:
        return lines + [_NA]
    lines.append("**📉 Fading**")
    lines += section(fading)
    lines += ["", "**📈 Thriving**"]
    lines += section(thriving)
    return lines
