"""CLI entry point for the LSIC briefing pipeline.

M0: --selftest only. Stage subcommands (--event, --papers, --all) land later.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from src import contracts, util


SRC_MODULES = [
    "src.contracts", "src.util", "src.discover", "src.ingest",
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="src.main")
    parser.add_argument("--selftest", action="store_true",
                        help="M0 smoke test — imports, pydantic, table alignment")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
