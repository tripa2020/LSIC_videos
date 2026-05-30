"""CLI entry point for the LSIC briefing pipeline.

M0: --selftest. M1: --discover, --ingest. M2+ stages land later.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from src import contracts, util


SRC_MODULES = [
    "src.contracts", "src.util", "src.validators", "src.discover", "src.ingest",
    "src.transcribe", "src.visual", "src.align", "src.synthesize",
    "src.pptx_handler", "src.pdf_handler",
]


def selftest() -> int:
    """Smoke test — imports, pydantic round-trips, table-alignment check.

    Exits 0 on success. Failures crash loudly with a pointer to the offending file.
    """
    print(f"[selftest] importing {len(SRC_MODULES)} src modules…", end=" ", flush=True)
    for m in SRC_MODULES:
        importlib.import_module(m)
    print("OK")

    print("[selftest] round-tripping pydantic contracts…", end=" ", flush=True)
    n = _check_pydantic_roundtrip()
    print(f"OK ({n} contracts)")

    print("[selftest] util.align_table() vs golden mockup…", end=" ", flush=True)
    n = _check_table_alignment()
    print(f"OK ({n}/3 tables match)")

    print("[selftest] OK")
    return 0


def _check_pydantic_roundtrip() -> int:
    fixtures = [
        contracts.Asset(kind="video", path="/tmp/x.mp4", sha256="a" * 12,
                        lsic_id=3105),
        contracts.Event(event_id="lsic_2026-03-26", date="2026-03-26",
                        assets=[], duration_sec=3520.96),
        contracts.IngestResult(event_id="lsic_2026-03-26",
                               workdir="/tmp", duration_sec=3520.96),
        contracts.Segment(start=0.0, end=1.0, text="hello"),
        contracts.Caption(t=0.0, frame_path="/tmp/x.jpg"),
        contracts.Slide(n=1),
        contracts.DeckIndex(asset_id="3107", slides=[]),
        contracts.Presentation(asset_id="3107", title="t",
                               start=0.0, end=1.0, slides_count=1, match_score=0.5),
        contracts.Section(start=0.0, end=1.0, transcript="t"),
        contracts.TRLRow(technology="x", trl="4-5", basis="b",
                         confidence="inferred", source_timestamp="[00:00]"),
        contracts.ExpertLens(role="r", emoji="🔧", take="t"),
        contracts.FundingRow(org="o", mechanism="m", scale="s", focus="f",
                             source_timestamp="[00:00]"),
        contracts.CustomerRow(customer="c", mechanism="m",
                              status="Active PO", horizon="h", source="s"),
        contracts.ChokepointRow(stage="Research", chokepoint="c",
                                source_timestamp="[00:00]"),
        contracts.PerQuestionBlock(question="q", source_timestamp="[00:00]",
                                   role_takes=[]),
        contracts.SlideHighlight(image_path="/tmp/x.jpg", caption="c",
                                 source_timestamp="[00:00]"),
    ]
    for instance in fixtures:
        roundtripped = type(instance).model_validate_json(instance.model_dump_json())
        if roundtripped != instance:
            raise AssertionError(f"round-trip failed for {type(instance).__name__}")
    return len(fixtures)


# Golden funding table lifted verbatim from
# golden/2026-03-26_event_mockup.md. align_table() output MUST match byte-for-byte.
_FUNDING_ROWS = [
    ["Org", "Mechanism", "Scale", "Focus", "Source"],
    ["NASA STMD", "Phase II SBIR", "$X.X M committed", "Dust-tolerant connectors", "`[05:20]`"],
    ["NASA Artemis", "Architecture coordination", "—", "Power-tower umbilicals", "`[54:30]`"],
    ["JPL (internal)", "Capital", "~$YY M", "5 m³ dust chamber", "`[37:45]`"],
    ["*(gap)*", "Standards development", "unfunded", "Falls between NIST and NASA", "`[38:55]`"],
]
_FUNDING_EXPECTED = (
    "| Org            | Mechanism                 | Scale            | Focus                       | Source    |\n"
    "|----------------|---------------------------|------------------|-----------------------------|-----------|\n"
    "| NASA STMD      | Phase II SBIR             | $X.X M committed | Dust-tolerant connectors    | `[05:20]` |\n"
    "| NASA Artemis   | Architecture coordination | —                | Power-tower umbilicals      | `[54:30]` |\n"
    "| JPL (internal) | Capital                   | ~$YY M           | 5 m³ dust chamber           | `[37:45]` |\n"
    "| *(gap)*        | Standards development     | unfunded         | Falls between NIST and NASA | `[38:55]` |"
)

# Structural-only check inputs (chokepoints + TRL — verify pipes align row-to-row).
_CHOKEPOINT_ROWS = [
    ["Stage", "Chokepoint", "Source"],
    ["Research", "Standards lag SBIR awards", "`[29:41]`"],
    ["Development", "<5 dust-environment test facilities worldwide", "`[37:45]`"],
    ["Funding", "Standards work falls between NIST and NASA", "`[38:55]`"],
    ["Implementation", "No field-repair story for hermetic connectors", "`[56:14]`"],
]
_TRL_ROWS = [
    ["Technology", "TRL", "Basis", "Confidence", "Source"],
    ["Amphenol labyrinth connector", "4-5", "Lab data, JSC-1A, ambient atmosphere", "inferred", "`[15:48]`"],
    ["Yank Tech hermetic frangible", "3-4", "KC-135 parabolic, current pass-through only", "inferred", "`[53:02]`"],
    ["Nunez dust-standards framework", "2", "Position paper, no rig", "claimed", "`[22:40]`"],
    ["JPL 5 m³ dust chamber", "6 (facility)", "Under construction", "claimed", "`[37:45]`"],
]


def _check_table_alignment() -> int:
    got = util.align_table(_FUNDING_ROWS)
    if got != _FUNDING_EXPECTED:
        raise AssertionError(
            "align_table funding mismatch:\n"
            f"---GOT---\n{got}\n"
            f"---EXPECTED---\n{_FUNDING_EXPECTED}\n"
        )
    for name, rows in [("chokepoints", _CHOKEPOINT_ROWS), ("TRL", _TRL_ROWS)]:
        out = util.align_table(rows)
        lengths = {len(line) for line in out.split("\n")}
        if len(lengths) != 1:
            raise AssertionError(
                f"align_table {name}: row lengths inconsistent {lengths}\n{out}"
            )
    return 3


def discover_cmd(folder: Path) -> int:
    from src import discover as discover_mod
    result = discover_mod.discover(folder)
    print(f"[discover] {len(result['events'])} events, {len(result['papers'])} papers")
    for e in result["events"]:
        kinds = ", ".join(a.kind for a in e.assets)
        print(f"  {e.event_id:24s} ({len(e.assets)} assets) [{kinds}]")
    for p in result["papers"]:
        print(f"  paper {p.lsic_id:5d}  {p.path.name}")
    return 0


def ingest_cmd(event_id: str | None, all_flag: bool) -> int:
    from src import ingest as ingest_mod
    if all_flag:
        summary = ingest_mod.ingest_all()
        print(f"[ingest] {summary['events']} events + {summary['papers']} papers OK")
    elif event_id:
        result = ingest_mod.ingest_one_event(event_id)
        print(f"[ingest] {result.event_id} → {result.workdir}")
        if result.audio_path:
            print(f"         audio: {result.audio_path} ({result.duration_sec:.0f} s)")
    else:
        print("--ingest requires --event <id> or --all", file=sys.stderr)
        return 1
    return 0


def transcribe_cmd(event_id: str | None, max_sec: float | None) -> int:
    from src import transcribe as transcribe_mod
    if not event_id:
        print("--transcribe requires --event <id>", file=sys.stderr)
        return 1
    out_path, segs = transcribe_mod.transcribe_one_event(event_id, max_sec=max_sec)
    speakers = sorted({s.speaker_id for s in segs if s.speaker_id})
    langs = sorted({s.language for s in segs if s.language})
    print(f"[transcribe] {event_id} → {out_path}")
    print(f"             {len(segs)} segments · speakers={speakers} · langs={langs}")
    if segs:
        print(f"             first: {util.mmss(segs[0].start)} {segs[0].text[:80]!r}")
        print(f"             last:  {util.mmss(segs[-1].start)} {segs[-1].text[:80]!r}")
    return 0


def visual_cmd(event_id: str | None) -> int:
    """M3: hybrid-sampled keyframe extraction + Gemini VLM captioning."""
    from src import visual as visual_mod
    if not event_id:
        print("--visual requires --event <id>", file=sys.stderr)
        return 1
    caps = visual_mod.extract_visual(event_id)
    workdir = Path("work/events") / event_id
    by_trigger = {}
    for c in caps:
        by_trigger[c.trigger or "?"] = by_trigger.get(c.trigger or "?", 0) + 1
    print(f"[visual] {event_id} → {workdir / 'captions.json'}")
    print(f"         {len(caps)} captioned frames · triggers={dict(by_trigger)}")
    flagged = sum(1 for c in caps if c.has_equation or c.has_diagram)
    print(f"         {flagged} frames flagged has_equation or has_diagram")
    return 0


def synthesize_cmd(event_id: str | None, max_sec: float | None) -> int:
    """M2.5 steel thread: single Claude call → notes.md from existing transcript."""
    from src import synthesize as synth_mod, util as util_mod
    from src.contracts import IngestResult
    if not event_id:
        print("--synthesize requires --event <id>", file=sys.stderr)
        return 1
    event_workdir = Path("work/events") / event_id
    ingest_manifest = event_workdir / util_mod.STAGE_INGEST / "manifest.json"
    manifest = IngestResult.model_validate_json(ingest_manifest.read_text())

    if max_sec is not None and max_sec < manifest.duration_sec:
        slice_root = event_workdir / f"slice_{int(max_sec)}s"
        transcript_path = slice_root / util_mod.STAGE_TRANSCRIPT / "transcript.json"
        notes_path = slice_root / util_mod.STAGE_BRIEFING / "notes.md"
        duration = float(max_sec)
    else:
        transcript_path = event_workdir / util_mod.STAGE_TRANSCRIPT / "transcript.json"
        notes_path = event_workdir / util_mod.STAGE_BRIEFING / "notes.md"
        duration = manifest.duration_sec
    if not transcript_path.exists():
        print(f"no transcript at {transcript_path} — run --transcribe first", file=sys.stderr)
        return 1
    synth_mod.synthesize_thin(
        event_id=event_id, transcript_path=transcript_path,
        duration_sec=duration, output_path=notes_path,
        event_date=str(manifest.event_id.replace("lsic_", "")),
    )
    print(f"[synthesize] {event_id} → {notes_path}")
    return 0


def validate_notes_cmd(path: str, strict: bool) -> int:
    from src.validators import validate_notes, render_result
    result = validate_notes(Path(path), strict=strict)
    print(render_result(result))
    return 0 if result.passed else 1


def validate_ingest_cmd(event_id: str | None) -> int:
    from src.validators import validate_ingest, render_result
    if not event_id:
        print("--validate-ingest requires --event <id>", file=sys.stderr)
        return 1
    result = validate_ingest(Path("work/events") / event_id)
    print(render_result(result))
    return 0 if result.passed else 1


def validate_transcript_cmd(event_id: str | None) -> int:
    from src.validators import validate_transcript, render_result
    from src import util as util_mod
    if not event_id:
        print("--validate-transcript requires --event <id>", file=sys.stderr)
        return 1
    path = Path("work/events") / event_id / util_mod.STAGE_TRANSCRIPT / "transcript.json"
    result = validate_transcript(path)
    print(render_result(result))
    return 0 if result.passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="src.main")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true",
                   help="M0 smoke test — imports, pydantic, table alignment")
    g.add_argument("--discover", action="store_true",
                   help="M1: scan LSIC_Downloads/, write work/events.json")
    g.add_argument("--ingest", action="store_true",
                   help="M1: per-asset ingest (use --event or --all)")
    g.add_argument("--transcribe", action="store_true",
                   help="M2: ASR via Gemini (use --event, optional --max-sec)")
    g.add_argument("--visual", action="store_true",
                   help="M3: hybrid keyframe extraction + Gemini VLM captioning")
    g.add_argument("--synthesize", action="store_true",
                   help="M2.5 thin: single Claude call → notes.md from existing transcript")
    g.add_argument("--validate-notes", type=str, default=None, metavar="PATH",
                   help="run validate_notes on a notes.md file")
    g.add_argument("--validate-ingest", action="store_true",
                   help="run validate_ingest on an event workdir (use --event)")
    g.add_argument("--validate-transcript", action="store_true",
                   help="run validate_transcript on an event's transcript.json (use --event)")
    parser.add_argument("folder", nargs="?", default="LSIC_Downloads", type=Path,
                        help="source folder for --discover (default: LSIC_Downloads)")
    parser.add_argument("--event", type=str, help="event_id for --ingest/--transcribe/--synthesize")
    parser.add_argument("--all", action="store_true",
                        help="--ingest --all: ingest every event + paper")
    parser.add_argument("--max-sec", type=float, default=None,
                        help="--transcribe/--synthesize: limit to first N seconds (test slice)")
    parser.add_argument("--strict", action="store_true",
                        help="--validate-notes --strict: reject fabricated placeholders")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if args.discover:
        return discover_cmd(args.folder)
    if args.ingest:
        return ingest_cmd(args.event, args.all)
    if args.transcribe:
        return transcribe_cmd(args.event, args.max_sec)
    if args.visual:
        return visual_cmd(args.event)
    if args.synthesize:
        return synthesize_cmd(args.event, args.max_sec)
    if args.validate_notes:
        return validate_notes_cmd(args.validate_notes, args.strict)
    if args.validate_ingest:
        return validate_ingest_cmd(args.event)
    if args.validate_transcript:
        return validate_transcript_cmd(args.event)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
