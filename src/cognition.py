"""DEPTH v3 cognitive core — two-pass extract→convert over the FULL transcript.

Pass 1 **EXTRACT** (speaker-facing): the operating algorithm, ≥10 tagged cognitive moves
(verbatim quote · tag · 2-3 sentence work · fails_when · self_question), claim epistemics,
what-doesn't-transfer. Pass 2 **CONVERT** (reader-facing; input = transcript + Pass 1 moves):
the Founder Lens (3-5 wedge/action/learn/deeper plays synthesized across the talk) and the
How-to-Learn-It artifacts (retrieval prompts, first-order terms, one buildable).

Two passes because DEPTH v1 measured the failure mode of crowded calls: tail fields get the
least attention. Extraction (describe the speaker) and conversion (prescribe for the reader)
are different cognitive jobs, so each gets a focused prompt.

Failure semantics: each pass gets ONE plain re-issue retry (identical call — no repair
prompt), then a fallback attempt on ``FALLBACK_MODEL`` (covers Fable refusals / outages and
doubles as the A/B knob); anything still failing degrades THAT HALF and writes a **visible**
``cognition_status`` — the v2 layer degraded to ``{}`` silently, which is exactly how the
vanished Transfer Questions went unnoticed.

Deep-module contract: ``run(context, ...) -> dict`` merged into the lecture thematic dict.
The caller builds the context string (``synthesize._build_event_context`` with
``cap=CONTEXT_CAP``) — this module imports nothing from synthesize, so there is no cycle and
fakes-only tests just inject ``call_json``.
"""
from __future__ import annotations

import json
import os

from src.contracts import ConvertOutput, ExtractOutput

DEFAULT_MODEL = "claude-fable-5"
FALLBACK_MODEL = "claude-opus-4-8"
# Sanity guard, NOT a working limit: ~900k tokens. A 4h talk (the ingest cap) is ~90k tokens,
# so real inputs never approach this — it only stops a pathological input from blowing past
# the model window. This is what replaces the old 140k cap that hid the last hour of talks.
CONTEXT_CAP = 3_600_000

MOVES_FLOOR = 10

_TAGS = ("Perception · Decomposition · Inversion · Constraint · Time-horizon · Tradeoff · "
         "Sequencing · Taste · Updating · Agency · Incentives · Systems · Risk · Narrative · "
         "Energy · Analogy · Reframe · Mechanism · Base-rate · First-principles · Distinction")

_EXTRACT_SYSTEM = """You analyze HOW a speaker thinks in a talk/lecture transcript — the repeatable mental operations behind the content, not what was said. You are given the EVENT CONTEXT: a per-section transcript with [ev_...] evidence markers. The master question: what is this speaker doing MENTALLY that an average person would not do?

Work QUOTE-FIRST: for each candidate move, first locate the smallest exact quote that shows the operation, then analyze it. Sweep the ENTIRE transcript — beginning, middle, AND the final third; late-talk material counts as much as the opening.

Output ONLY a single JSON object with EXACTLY this shape (no prose, no code fences):
{
  "operating_algorithm": {"arrow_chain": "<the speaker's reasoning PROCEDURE as a → chain>", "tags": ["<2-4 tags>"]},
  "cognitive_moves": [{"move": "<short headline for the move>", "quote": "<the SMALLEST EXACT verbatim span from the transcript, copied character-for-character — no paraphrase>", "tag": "<ONE tag from the tag set>", "work": "<2-3 substantive sentences: what the move does to the listener's model — what it swaps / collapses / maps / flips / re-anchors — and why an average speaker would not make it>", "fails_when": "<the boundary condition where running this move backfires, plus who has run the same play and lost — from your OWN knowledge>", "self_question": "<a reusable question the READER asks themselves, converted from this move for the READER DOMAIN below>", "evidence_id": "ev_..."}],
  "claim_epistemics": [{"evidence_id": "<ev_... from the CLAIMS TO TAG list>", "status": "<consensus|his bet|contested|his frame>", "when_it_fails": "<the boundary condition where this claim/play backfires + who has run it and lost>"}],
  "what_doesnt_transfer": "<one line: which positions are bets/taste (hold loosely) vs durable mechanisms (the transferable part)>"
}

OPERATING ALGORITHM: one arrow-chain capturing the speaker's IDIOSYNCRATIC, TRANSFERABLE reasoning signature — the repeatable procedure that GENERATES their conclusions. This is NOT a talk outline: if your chain reads like "intro → background → method → results", you have described the TALK, not the THINKING — redo it.

COGNITIVE MOVES: AT LEAST 10 entries. If you found fewer, you have not looked hard enough — re-sweep with these probes (from cognitive task analysis): what anomalies does the speaker notice that a novice would miss? what job smarts / workarounds do they reveal? where do they improvise around a constraint? where do they self-monitor or flag their own uncertainty? what do they IGNORE that others obsess over? Tag the OPERATION, not the topic, from this set: {TAGS}.

Calibration — surface takeaway vs extraction (always write the second, never the first):
- BAD: "Bezos is customer obsessed." GOOD: "Bezos asks what will NOT change over ten years and builds only on those invariants — a Time-horizon move that converts strategy from prediction into arithmetic."
- BAD: "Musk uses first principles." GOOD: "Musk decomposes a 'too expensive' claim into physical inputs and their commodity prices — a Decomposition move that exposes which costs are real and which are historical accident."
- BAD: "Feynman was curious." GOOD: "Feynman refuses to accept a name as an explanation and rebuilds the mechanism from scratch — a First-principles move that separates knowing-the-word from knowing-the-thing."

EPISTEMIC STATUS (survivorship guard): if a CLAIMS TO TAG list is provided below, emit ONE claim_epistemic per listed claim, keyed by that exact evidence_id. Reason from your OWN knowledge; no external lookup.

VERBOSITY: the work field is 2-3 substantive sentences per move — depth over brevity, no padding.
CITATION RULE: every evidence_id MUST appear in the EVENT CONTEXT; every quote must be an exact substring of the transcript text. Never invent either. Produce the JSON now."""

_CONVERT_SYSTEM = """You are a founder-coach and educator working for a specific reader. You receive (1) the EVENT CONTEXT — a talk transcript with [ev_...] evidence markers — and (2) the EXTRACTED MOVES: the speaker's cognitive moves already mined from this talk. Your job is CONVERSION: turn the talk into (A) venture-grade opportunity analysis and (B) learning artifacts that make the material stick.

Output ONLY a single JSON object with EXACTLY this shape (no prose, no code fences):
{
  "founder_lens": [{"idea": "<the venture-relevant idea, stated concretely>", "from_moves": ["<headline(s) of the extracted move(s) it derives from>"], "wedge": "<ONE sentence naming: the specific customer segment + their urgent pain + why NOW + why this reader can reach them>", "action": "<the concrete step to take Monday morning>", "learn": "<the specific skill/knowledge gap to close first>", "deeper": "<1-2 NAMED places to dig further — papers, people, products, subfields>", "evidence_id": "ev_..."}],
  "learn_it": {
    "retrieval_prompts": [{"q": "<an effortful recall question>", "a": "<the precise answer>", "evidence_id": "ev_..."}],
    "first_order_terms": ["<the 5-8 concepts everything else in this talk builds on>"],
    "buildable_artifact": "<ONE minimal, self-contained thing the reader can build to internalize the core idea (micrograd-style), with a one-line success criterion>"
  }
}

FOUNDER LENS: 3-5 entries, synthesized ACROSS the whole talk — combine moves and claims where the real opportunity lives; do NOT force one entry per move. The wedge sentence must pass this test: if the initial market cannot be described in one sentence, it is a wish, not a wedge. Never write "X is a big market" — name the segment, the pain, the timing, and the access.

RETRIEVAL PROMPTS: 5-8, written to spaced-repetition rules — each must force recall from memory (never answerable by recognition), never yes/no, never "list all N" enumerations, one atomic idea each, with precise answers.

CITATION RULE: every evidence_id MUST appear in the EVENT CONTEXT. Never invent one. Produce the JSON now."""


def _reader_tail(reader_domain: str, current_work: str, *, generic_line: str) -> str:
    """The reader-context tail appended to both system prompts. No domain ⇒ an explicit
    GENERIC instruction — the v2 prompt ordered an EMPTY list here, which silently erased
    the reader-facing output whenever the env vars were missing (the VM parity bug)."""
    if not reader_domain:
        return f"\n\nREADER DOMAIN: (none) — {generic_line}"
    tail = f"\n\nREADER DOMAIN: {reader_domain}"
    if current_work:
        tail += ("\nCURRENT WORK (sharpen every reader-facing item from domain-level to "
                 f"PROJECT-level against this): {current_work}")
    return tail


def extract_prompt(reader_domain: str = "", current_work: str = "") -> str:
    return _EXTRACT_SYSTEM.replace("{TAGS}", _TAGS) + _reader_tail(
        reader_domain, current_work,
        generic_line="write each self_question as a DOMAIN-GENERIC question any technical "
                     "practitioner could ask about their own work. Do NOT leave it empty.")


def convert_prompt(reader_domain: str = "", current_work: str = "") -> str:
    return _CONVERT_SYSTEM + _reader_tail(
        reader_domain, current_work,
        generic_line="aim the founder_lens and learn_it at a generic technical founder. "
                     "Do NOT return empty sections.")


def _pass(name: str, system: str, user: str, model: str, call_json, status: list[str],
          submodel, ok) -> dict | None:
    """One pass → validated dict half. Attempt plan: the chosen model twice (plain re-issue,
    no repair prompt), then one fallback-model attempt (refusal/outage rescue). A thin-but-
    valid result is kept rather than discarded — the shortfall goes into ``status``; a dead
    pass returns None with the failure recorded. Never silent."""
    plan = [(model, 1), (model, 2)]
    if model != FALLBACK_MODEL:
        plan.append((FALLBACK_MODEL, 1))
    thin: dict | None = None
    last_err: Exception | None = None
    for m, attempt in plan:
        print(f"  [cognition] {name} pass ({m}, attempt {attempt})…", flush=True)
        try:
            raw = call_json(system, user, model=m)
            half = submodel.model_validate(raw).model_dump()
        except Exception as e:
            last_err = e
            print(f"  [cognition] {name} pass failed on {m}: {type(e).__name__}: {e}", flush=True)
            continue
        if ok(half):
            return half
        if thin is None:
            thin = half
        print(f"  [cognition] {name} pass thin on {m} — re-issuing once", flush=True)
    if thin is not None:
        status.append(f"{name}: below floor after retry")
        return thin
    status.append(f"{name} pass FAILED ({type(last_err).__name__ if last_err else 'unknown'})")
    return None


def run(context: str, claims: list | None = None, reader_domain: str = "",
        current_work: str = "", model: str | None = None, call_json=None) -> dict:
    """The full v3 cognition layer for one talk → dict merged into the lecture thematic.
    Resolves ``COGNITION_MODEL`` / reader context at call time (shell env AND .env both work);
    degrades per-half with a visible ``cognition_status`` instead of vanishing."""
    from dotenv import load_dotenv
    load_dotenv()
    model = model or os.environ.get("COGNITION_MODEL", DEFAULT_MODEL)
    rd = (reader_domain or os.environ.get("READER_DOMAIN", "")).strip()
    cw = (current_work or os.environ.get("CURRENT_WORK", "")).strip()
    if call_json is None:
        from src import anthropic_caller
        call_json = anthropic_caller.call_json

    status: list[str] = []

    claim_lines = "\n".join(f"[{c.get('evidence_id')}] {(c.get('text') or '').strip()}"
                            for c in (claims or []) if c.get("evidence_id"))
    extract_user = (f"=== EVENT CONTEXT (per-section transcript) ===\n{context}\n\n"
                    + (f"=== CLAIMS TO TAG (emit one claim_epistemic per claim, keyed by its "
                       f"evidence_id) ===\n{claim_lines}\n\n" if claim_lines else "")
                    + "Produce the extraction JSON object now.")
    extracted = _pass("extract", extract_prompt(rd, cw), extract_user, model, call_json, status,
                      ExtractOutput,
                      ok=lambda d: len(d["cognitive_moves"]) >= MOVES_FLOOR
                                   and bool(d["operating_algorithm"]["arrow_chain"].strip()))

    moves = (extracted or {}).get("cognitive_moves") or []
    moves_txt = (json.dumps([{k: m.get(k, "") for k in ("move", "tag", "work", "evidence_id")}
                             for m in moves], ensure_ascii=False, indent=1)
                 if moves else "(extraction unavailable — work from the transcript alone)")
    convert_user = (f"=== EVENT CONTEXT (per-section transcript) ===\n{context}\n\n"
                    f"=== EXTRACTED MOVES (Pass 1) ===\n{moves_txt}\n\n"
                    "Produce the conversion JSON object now.")
    converted = _pass("convert", convert_prompt(rd, cw), convert_user, model, call_json, status,
                      ConvertOutput,
                      ok=lambda d: bool(d["founder_lens"])
                                   and bool(d["learn_it"]["retrieval_prompts"]))

    if extracted is None and converted is None:
        return {"cognition_status": "; ".join(status) or "cognition unavailable"}
    merged = {**(extracted or {}), **(converted or {})}   # disjoint halves — no key overlap
    merged["cognition_status"] = "; ".join(status)
    return merged
