"""CLI entry point for the LSIC briefing pipeline.

M0: --selftest. M1: --discover, --ingest. M2+ stages land later.
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from src import contracts, util


SRC_MODULES = [
    "src.contracts", "src.util", "src.validators", "src.discover", "src.ingest",
    "src.transcribe", "src.visual", "src.align", "src.synthesize",
    "src.slide_book", "src.report", "src.status", "src.pptx_handler", "src.pdf_handler",
    "src.adhoc", "src.profiles", "src.profiles.lecture", "src.enrich_citations",
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

    print("[selftest] status matrix on a fake work dir…", end=" ", flush=True)
    _check_status()
    print("OK")

    print("[selftest] OK")
    return 0


def _check_status() -> None:
    """Fakes-only (no network): manifest gates → correct first-incomplete stage."""
    import tempfile
    from src import status as status_mod
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "events" / "lsic_test"
        ing = root / util.STAGE_INGEST / "manifest.json"
        ing.parent.mkdir(parents=True)
        util.write_with_manifest(ing, "{}", stage="ingest")   # only ingest complete
        nxt = status_mod.first_incomplete(root)
        assert nxt == "transcribe", f"expected transcribe, got {nxt}"
        empty = Path(td) / "events" / "lsic_empty"
        empty.mkdir(parents=True)
        assert status_mod.first_incomplete(empty) == "ingest"


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


def ingest_cmd(event_id: str | None, all_flag: bool,
               cap_sec: float | None = None) -> int:
    from src import ingest as ingest_mod
    if all_flag:
        summary = ingest_mod.ingest_all()
        print(f"[ingest] {summary['events']} events + {summary['papers']} papers OK")
    elif event_id:
        result = ingest_mod.ingest_one_event(event_id, max_total_sec=cap_sec)
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


def run_event_stages(evt: str,
                     stages: list[tuple[str, Callable[[], int]]]) -> tuple[bool, Optional[str]]:
    """Run an event's (name, fn) stages in order, **exception-safe**.

    A raised exception is caught and treated as rc=1 (never propagates) so the caller's
    --keep-going loop can continue to the next event. Returns (ok, failed_stage).
    Pure control-flow over injected callables → unit-tested with fake stage fns.
    """
    for i, (name, fn) in enumerate(stages, 1):
        t0 = time.monotonic()
        print(f"  ({i}/{len(stages)}) {name} …", flush=True)
        try:
            rc = fn()
        except Exception as e:
            print(f"  ({i}/{len(stages)}) {name} EXCEPTION: {str(e)[:140]}",
                  file=sys.stderr, flush=True)
            rc = 1
        dt = time.monotonic() - t0
        print(f"  ({i}/{len(stages)}) {name} {'OK' if not rc else 'FAILED'} {dt:.0f}s", flush=True)
        if rc:
            return False, name
    return True, None


def _make_batch_caller():
    """Build a BatchCaller over a real Gemini client (used only when --batch is passed)."""
    import os

    from dotenv import load_dotenv
    from google import genai

    from src.llm_caller import BatchCaller
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set — required for --batch")
    return BatchCaller(genai.Client(api_key=api_key))


def _staged(prefill_fn, caller, cmd):
    """Wrap a stage so its batch prefill runs first when a caller is present. With caller=None
    (default) the prefill is skipped entirely → the stage's sync path is byte-identical. A
    prefill error is warned and swallowed; the sync cmd then fills any uncached item live."""
    def run() -> int:
        if caller is not None and prefill_fn is not None:
            try:
                n = prefill_fn(caller)
                print(f"    [batch] prefilled {n} cache(s)", flush=True)
            except Exception as e:
                print(f"    [batch] prefill skipped ({str(e)[:80]}) — stage will run live",
                      file=sys.stderr, flush=True)
        return cmd()
    return run


def pipeline_cmd(event_id: str | None, all_flag: bool, keep_going: bool = False,
                 batch: bool = False, cap_sec: float | None = None,
                 profile: str | None = None, references: bool = False) -> int:
    """Chain ingest→transcribe→visual→align→synthesize→slide_book→report per event.

    keep_going=False (default) aborts the batch on the first failing stage (today's
    behavior). keep_going=True continues to the next event and prints a final matrix.
    """
    from src import discover as discover_mod, ingest as ingest_mod
    events_path = Path("work/events.json")
    if not events_path.exists():
        print("[pipeline] no events.json — running --discover first…", flush=True)
        discover_mod.discover(Path("LSIC_Downloads"))

    events, _ = ingest_mod.load_events_json()
    have_video = {e.event_id for e in events
                  if any(a.kind == "video" for a in e.assets)}

    if all_flag:
        targets = sorted(have_video)
    elif event_id:
        if event_id not in {e.event_id for e in events}:
            print(f"unknown event_id '{event_id}'", file=sys.stderr)
            return 1
        if event_id not in have_video:
            print(f"{event_id} has no video — pipeline requires ingest/transcribe/visual",
                  file=sys.stderr)
            return 1
        targets = [event_id]
    else:
        print("--pipeline requires --event <id> or --all", file=sys.stderr)
        return 1

    caller = _make_batch_caller() if batch else None     # None ⇒ degrade-to-today
    if caller is not None:
        from src import slide_book as sb_mod, transcribe as tr_mod, visual as vis_mod

    failures: list[tuple[str, str]] = []   # (event_id, stage) for --keep-going summary
    for k, evt in enumerate(targets, 1):
        print(f"\n========== event {k}/{len(targets)}: {evt} ==========", flush=True)
        if caller is None:
            stages = [
                ("ingest", lambda: ingest_cmd(evt, all_flag=False, cap_sec=cap_sec)),
                ("transcribe", lambda: transcribe_cmd(evt, max_sec=None)),
                ("visual", lambda: visual_cmd(evt)),
                ("align", lambda: align_cmd(evt)),
                ("synthesize", lambda: synthesize_cmd(evt, max_sec=None, profile=profile)),
                ("slide_book", lambda: slide_book_cmd(evt)),
                ("report", lambda: report_cmd(evt)),
            ]
        else:
            ev = evt   # bind per-iteration for the closures below
            stages = [
                ("ingest", lambda: ingest_cmd(ev, all_flag=False, cap_sec=cap_sec)),
                ("transcribe", _staged(lambda c: tr_mod.batch_prefill_chunks(ev, c),
                                       caller, lambda: transcribe_cmd(ev, max_sec=None))),
                ("visual", _staged(lambda c: vis_mod.batch_prefill_captions(ev, c),
                                   caller, lambda: visual_cmd(ev))),
                ("align", lambda: align_cmd(ev)),
                ("synthesize", lambda: synthesize_cmd(ev, max_sec=None, profile=profile)),
                ("slide_book", _staged(lambda c: sb_mod.batch_prefill_slides(ev, c),
                                       caller, lambda: slide_book_cmd(ev))),
                ("report", lambda: report_cmd(ev)),
            ]
        if references:   # M3: insert the enrich stage right after synthesize (opt-in for pipeline)
            syn_idx = next(i for i, (n, _) in enumerate(stages) if n == "synthesize")
            stages.insert(syn_idx + 1, ("enrich", lambda: enrich_cmd(evt)))
        ok, failed = run_event_stages(evt, stages)
        if not ok:
            failures.append((evt, failed))
            print(f"[pipeline] FAILED at {failed} for {evt}", file=sys.stderr)
            if not keep_going:
                return 1                            # degrade-to-today: abort the batch
        else:
            print(f"========== {evt} done ==========", flush=True)

    if keep_going:
        from src import status as status_mod
        print("\n========== run complete ==========", flush=True)
        status_mod.print_status()
        if failures:
            print("failed:", ", ".join(f"{e}@{s}" for e, s in failures), file=sys.stderr)
        return 1 if failures else 0
    return 0


def align_cmd(event_id: str | None) -> int:
    """M4: sectioning + per-deck fingerprint match + Evidence Object emission."""
    from src import align as align_mod
    if not event_id:
        print("--align requires --event <id>", file=sys.stderr)
        return 1
    result = align_mod.align(event_id)
    print(f"[align] {event_id} → work/events/{event_id}/04_aligned/")
    print(f"        {len(result.sections)} sections · "
          f"{len(result.presentations)} presentations")
    for p in result.presentations:
        print(f"          • {p.asset_id} \"{p.title[:50]}\" "
              f"[{int(p.start//60):02d}:{int(p.start%60):02d} → "
              f"{int(p.end//60):02d}:{int(p.end%60):02d}] score={p.match_score:.0f}")
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


def synthesize_cmd(event_id: str | None, max_sec: float | None,
                   profile: str | None = None) -> int:
    """M5 (full event) or M2.5 thin (slice mode).

    Full event needs M4 alignment + M3 captions; slice mode falls back to
    single-call thin synthesis from transcript only.
    """
    from src import synthesize as synth_mod, util as util_mod
    from src.contracts import IngestResult
    if not event_id:
        print("--synthesize requires --event <id>", file=sys.stderr)
        return 1
    event_workdir = Path("work/events") / event_id
    ingest_manifest = event_workdir / util_mod.STAGE_INGEST / "manifest.json"
    manifest = IngestResult.model_validate_json(ingest_manifest.read_text())

    if max_sec is not None and max_sec < manifest.duration_sec:
        # slice mode — thin synth on the slice transcript
        slice_root = event_workdir / f"slice_{int(max_sec)}s"
        transcript_path = slice_root / util_mod.STAGE_TRANSCRIPT / "transcript.json"
        notes_path = slice_root / util_mod.STAGE_BRIEFING / "notes.md"
        if not transcript_path.exists():
            print(f"no transcript at {transcript_path} — run --transcribe first", file=sys.stderr)
            return 1
        synth_mod.synthesize_thin(
            event_id=event_id, transcript_path=transcript_path,
            duration_sec=float(max_sec), output_path=notes_path,
            event_date=str(manifest.event_id.replace("lsic_", "")),
        )
        print(f"[synthesize/thin] {event_id} (slice) → {notes_path}")
        return 0

    # full event — M5 path, requires M4 alignment
    aligned = event_workdir / util_mod.STAGE_ALIGNED / "aligned.json"
    if not util_mod.is_complete(aligned):
        print(f"no aligned.json at {aligned} — run --align first (M5 needs M4 output)",
              file=sys.stderr)
        return 1
    synth_mod.synthesize_full(event_id, profile=profile)
    return 0


def enrich_cmd(event_id: str | None) -> int:
    """M3: enrich the briefing with related papers → references.md (degrades to a skip-stub
    when the search source is unreachable; never fatal)."""
    if not event_id:
        print("--enrich requires --event <id>", file=sys.stderr)
        return 1
    from src import enrich_citations as enrich_mod
    enrich_mod.enrich_citations(event_id)
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


def slide_book_cmd(event_id: str | None) -> int:
    """M5.5: per-slide VLM curation + topical slides.pdf + slide_captions.md + equations.md."""
    from src import slide_book as sb_mod
    if not event_id:
        print("--slide-book requires --event <id>", file=sys.stderr)
        return 1
    pdf_path, captions_path, eq_path = sb_mod.slide_book(event_id)
    print(f"[slide_book] {event_id} → {pdf_path}")
    print(f"             {event_id} → {captions_path}")
    print(f"             {event_id} → {eq_path}")
    return 0


def report_cmd(event_id: str | None) -> int:
    """Assemble the reader-facing Report/ folder (notes.md, slides.pdf, slide_captions.md)."""
    from src import report as report_mod
    if not event_id:
        print("--report requires --event <id>", file=sys.stderr)
        return 1
    dst = report_mod.assemble_report(event_id)
    print(f"[report] {event_id} → {dst}")
    return 0


def status_cmd(event_id: str | None) -> int:
    """Print the per-event stage-completion matrix (all events, or one with --event)."""
    from src import status as status_mod
    status_mod.print_status(event_id=event_id)
    return 0


def validate_slides_cmd(event_id: str | None) -> int:
    from src.validators import validate_slides, render_result
    from src import util as util_mod
    if not event_id:
        print("--validate-slides requires --event <id>", file=sys.stderr)
        return 1
    workdir = Path("work/events") / event_id
    result = validate_slides(workdir)
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
    g.add_argument("--align", action="store_true",
                   help="M4: sectioning + Evidence Object emission")
    g.add_argument("--slide-book", action="store_true",
                   help="M5.5: per-slide VLM curation → slides.md + equations.md")
    g.add_argument("--report", action="store_true",
                   help="assemble reader-facing Report/ folder (notes.md, slides.pdf, slide_captions.md)")
    g.add_argument("--status", action="store_true",
                   help="print the per-event stage-completion matrix (optionally with --event)")
    g.add_argument("--validate-slides", action="store_true",
                   help="validate the slide_book output for an event (use --event)")
    g.add_argument("--pipeline", action="store_true",
                   help="Chain ingest→transcribe→visual→align→synthesize→slide_book (use --event or --all)")
    g.add_argument("--synthesize", action="store_true",
                   help="M2.5 thin: single Claude call → notes.md from existing transcript")
    g.add_argument("--source", type=str, default=None, metavar="URL|PATH",
                   help="ad-hoc: a YouTube URL or local video file → full pipeline → Report/")
    g.add_argument("--enrich", action="store_true",
                   help="M3: related-paper enrichment → references.md (use --event)")
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
    parser.add_argument("--keep-going", action="store_true",
                        help="--pipeline --all: continue past a failed event instead of aborting")
    parser.add_argument("--batch", action="store_true",
                        help="--pipeline: bulk-fill ASR/visual/slide caches via Gemini Batch "
                             "before each stage (off = today's synchronous calls)")
    parser.add_argument("--cap-video-hours", type=float, default=None, metavar="H",
                        help="aggregate-video cap per event (e.g. 4 = 4h); unset = no cap")
    parser.add_argument("--out", type=Path, default=None, metavar="DIR",
                        help="--source: also copy the finished Report/ bundle to this folder")
    parser.add_argument("--profile", type=str, default=None, choices=["briefing", "lecture"],
                        help="--source/--pipeline: notes template (briefing=LSIC default | lecture=generic talk)")
    parser.add_argument("--references", action="store_true",
                        help="--pipeline: also run related-paper enrichment (off by default; "
                             "on automatically for --source)")
    args = parser.parse_args()
    cap_sec = args.cap_video_hours * 3600.0 if args.cap_video_hours else None

    if args.selftest:
        return selftest()
    if args.discover:
        return discover_cmd(args.folder)
    if args.ingest:
        return ingest_cmd(args.event, args.all, cap_sec=cap_sec)
    if args.transcribe:
        return transcribe_cmd(args.event, args.max_sec)
    if args.visual:
        return visual_cmd(args.event)
    if args.align:
        return align_cmd(args.event)
    if args.slide_book:
        return slide_book_cmd(args.event)
    if args.report:
        return report_cmd(args.event)
    if args.status:
        return status_cmd(args.event)
    if args.validate_slides:
        return validate_slides_cmd(args.event)
    if args.pipeline:
        return pipeline_cmd(args.event, args.all, args.keep_going, batch=args.batch,
                            cap_sec=cap_sec, profile=args.profile, references=args.references)
    if args.synthesize:
        return synthesize_cmd(args.event, args.max_sec)
    if args.enrich:
        return enrich_cmd(args.event)
    if args.source:
        from src import adhoc
        return adhoc.run_adhoc(args.source, out=args.out, profile=args.profile)
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
