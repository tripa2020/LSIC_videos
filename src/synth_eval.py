"""EVAL — pure deterministic coverage/coherence scorer (R2/R3). No LLM, no network.

Two modes sharing one score dict:
- ``score_notes(md)`` — notes.md alone (works on every golden bundle, old or new): cite
  spread across deciles, bullet cite-rate, the v3 cognition gates (moves floor, final-third
  coverage, per-move fields, Founder Lens / Learn-It presence, cognition_status).
- ``score_full(md, thematic, evidence)`` — adds what needs structured artifacts: verbatim
  quote verification against the transcript (the deterministic hallucination check),
  evidence-id resolution, and the cross-window coherence ratio (OQ4's metric).

Read-only by contract: ``evaluate_briefing`` writes ``coverage_report.{md,json}`` NEXT TO the
briefing artifacts and never mutates them; every failure degrades to "no score file" — the
pipeline runs exactly as before (the synthesize hook wraps it in try/except).

CLI (retro-scoring): ``python -m src.synth_eval <bundle-dir|notes.md>…`` prints one markdown
table row per bundle — how the golden generations get comparable numbers.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MOVES_FLOOR = 10
FINAL_THIRD_FLOOR = 2

_TS = re.compile(r"\[(\d+):(\d\d)\]")
_PAGE = re.compile(r"\[p\.(\d+)\]")   # paper mode: page-number citations


def _norm(s: str) -> str:
    """Normalize for quote matching: case/punctuation/whitespace-insensitive."""
    return re.sub(r"[\W_]+", " ", s.lower()).strip()


def _section(md: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}(.*?)(?=^## |\Z)", md, re.S | re.M)
    return m.group(1) if m else ""


def parse_duration_sec(md: str):
    m = re.search(r'^duration: "(\d+):(\d\d)"', md, re.M)
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def parse_pages(md: str):
    m = re.search(r"^pages: (\d+)", md, re.M)
    return int(m.group(1)) if m else None


def score_notes(md: str) -> dict:
    # Paper mode (frontmatter `profile: paper`, written only by the paper template): the same
    # coverage math in PAGE units — `[p.N]` cites against a `pages: N` span. Every other
    # bundle takes the [mm:ss] path below unchanged.
    paper = bool(re.search(r"^profile: paper$", md, re.M))
    ts = _PAGE if paper else _TS

    def val(m) -> int:
        return int(m.group(1)) if paper else int(m.group(1)) * 60 + int(m.group(2))

    dur = parse_pages(md) if paper else parse_duration_sec(md)
    cites = [val(m) for m in ts.finditer(md)]
    deciles = {min(int(t / dur * 10), 9) for t in cites} if (dur and cites) else set()
    bullets = re.findall(r"^- .+$", md, re.M)

    moves = _section(md, "Cognitive Moves")
    move_rows = re.findall(r"^- \*\*", moves, re.M)
    move_ts = [val(m) for m in ts.finditer(moves)]
    final_third = [t for t in move_ts if dur and t >= dur * 2 / 3]

    founder = _section(md, "Founder Lens — To Market")
    learn = _section(md, "How to Learn It (So It Sticks)")

    s = {
        "duration_sec": dur,
        "n_cites": len(cites),
        "decile_coverage": round(len(deciles) / 10, 2) if dur else None,
        "bullet_cite_rate": round(sum(1 for b in bullets if ts.search(b)) / len(bullets), 2)
                            if bullets else None,
        "moves": len(move_rows),
        "moves_with_quote": moves.count("> “"),
        "moves_with_fails_when": moves.count("*fails when:*"),
        "moves_with_self_question": moves.count("*ask yourself:*"),
        "final_third_cites": len(final_third),
        "founder_plays": len(re.findall(r"^### ", founder, re.M)),
        "retrieval_prompts": learn.count("- Q:"),
        "first_order_terms": "**First-order terms:**" in learn,
        "buildable_artifact": "**Build to internalize:**" in learn,
        "status_clean": "cognition degraded" not in md,
    }
    s["gates"] = {
        "moves_floor": s["moves"] >= MOVES_FLOOR,
        "final_third": s["final_third_cites"] >= FINAL_THIRD_FLOOR,
        "founder_lens": 3 <= s["founder_plays"] <= 5,
        "learn_it": s["retrieval_prompts"] >= 5 and s["buildable_artifact"],
        "status_clean": s["status_clean"],
    }
    return s


def score_full(md: str, thematic: dict, evidence: list[dict]) -> dict:
    """Notes score + the structured-artifact metrics (quote match, id resolution, OQ4 ratio)."""
    s = score_notes(md)
    transcript = _norm(" ".join(e.get("text", "") for e in evidence))
    quotes = [m.get("quote", "") for m in thematic.get("cognitive_moves", []) if m.get("quote")]
    s["quotes_verified"] = (round(sum(1 for q in quotes if _norm(q) in transcript) / len(quotes), 2)
                            if quotes else None)

    ev_ids = {e.get("evidence_id") for e in evidence}
    cited, resolved = 0, 0
    for v in thematic.values():
        for item in (v if isinstance(v, list) else []):
            eid = item.get("evidence_id") if isinstance(item, dict) else None
            if eid:
                cited += 1
                resolved += eid in ev_ids
    s["evidence_resolution"] = round(resolved / cited, 2) if cited else None

    s["cross_window_ratio"] = _cross_window_ratio(thematic, evidence)
    s["gates"]["quotes_verified"] = s["quotes_verified"] is None or s["quotes_verified"] >= 0.9
    return s


def _cross_window_ratio(thematic: dict, evidence: list[dict]):
    """OQ4: of the sections that cite evidence, what fraction weave ≥2 MAPRED windows."""
    from src import segment
    from src.contracts import Evidence
    ev = [Evidence.model_validate(e) for e in evidence]
    windows = segment.segment(ev)
    if len(windows) < 2:
        return None
    win_of = {e.evidence_id: i for i, w in enumerate(windows) for e in w.evidence}
    spanning = with_cites = 0
    for v in thematic.values():
        ids = {it.get("evidence_id") for it in (v if isinstance(v, list) else [])
               if isinstance(it, dict) and it.get("evidence_id")}
        wins = {win_of[i] for i in ids if i in win_of}
        if wins:
            with_cites += 1
            spanning += len(wins) >= 2
    return round(spanning / with_cites, 2) if with_cites else None


def render_report(name: str, s: dict) -> str:
    gates = " · ".join(f"{'✅' if ok else '❌'} {k}" for k, ok in s["gates"].items())
    rows = "\n".join(f"| {k} | {v} |" for k, v in s.items() if k != "gates")
    return (f"# Coverage Report — {name}\n\n{gates}\n\n"
            f"| metric | value |\n|--------|-------|\n{rows}\n")


def evaluate_briefing(briefing_dir: Path) -> Path | None:
    """Pipeline entry (read-only): score notes.md (+ thematic/evidence when present), write
    coverage_report.{md,json} beside them. Returns the report path, or None when unscoreable."""
    briefing_dir = Path(briefing_dir)
    notes = briefing_dir / "notes.md"
    if not notes.exists():
        return None
    md = notes.read_text()
    them_p = briefing_dir / "thematic.json"
    ev_p = briefing_dir.parent / "04_aligned" / "evidence.json"
    if them_p.exists() and ev_p.exists():
        s = score_full(md, json.loads(them_p.read_text()), json.loads(ev_p.read_text()))
    else:
        s = score_notes(md)
    (briefing_dir / "coverage_report.json").write_text(json.dumps(s, indent=2))
    out = briefing_dir / "coverage_report.md"
    out.write_text(render_report(briefing_dir.parent.name, s))
    return out


_TABLE_COLS = ("moves", "final_third_cites", "founder_plays", "retrieval_prompts",
               "decile_coverage", "bullet_cite_rate", "n_cites", "status_clean")


def main(argv: list[str]) -> int:
    print("| bundle | " + " | ".join(_TABLE_COLS) + " | gates |")
    print("|--------|" + "---|" * (len(_TABLE_COLS) + 1))
    for arg in argv:
        p = Path(arg)
        notes = p if p.suffix == ".md" else p / "notes.md"
        if not notes.exists():
            print(f"| {p.name} | (no notes.md) |")
            continue
        s = score_notes(notes.read_text())
        passed = sum(s["gates"].values())
        print(f"| {p.name if p.is_dir() else p.parent.name} | "
              + " | ".join(str(s[c]) for c in _TABLE_COLS)
              + f" | {passed}/{len(s['gates'])} |")
    return 0


if __name__ == "__main__":                                       # pragma: no cover
    sys.exit(main(sys.argv[1:]))
