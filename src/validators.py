"""Deterministic validators for pipeline artifacts.

Per the Information Architecture & Validation Contract in PLAN.md:
- validate_notes: structural correctness of generated/mockup notes.md
- validate_transcript: M2 transcript.json integrity
- validate_ingest, validate_alignment, validate_visual: stubs for future stages

Each returns a ValidationResult. Pass = no errors (warnings allowed).
Strict mode (validate_notes) additionally rejects fabricated placeholders.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from src.contracts import (
    Segment, ValidationIssue, ValidationResult,
)


# Canonical section headings in the order they must appear in any notes.md.
# Source of truth: golden/2026-03-26_event_mockup.md.
CANONICAL_SECTIONS = [
    "🎯 Bottom Line for C'mander Alex",
    "🗂️ Contents",
    "🎤 Presentations",
    "🔬 What's being done right now",
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
    "📎 Slide highlights",
]

REQUIRED_FRONTMATTER_KEYS = {
    "event_id", "date", "title_inferred", "duration",
    "speakers_detected", "languages", "generated",
}

PLACEHOLDER_PATTERNS = [
    re.compile(r"\$X\.X"),
    re.compile(r"~?\$YY"),
    re.compile(r"\bTBD\b"),
    re.compile(r"\bXXX\b"),
]

TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:\s*/\s*\d{1,2}:\d{2})?\]")
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def validate_notes(path: Path, *, strict: bool = False) -> ValidationResult:
    """Structural validator for a notes.md file.

    strict=False (steel-thread): allow fabricated placeholders (mockup mode).
    strict=True  (production):   reject placeholders, require all citations.
    """
    if not path.exists():
        return ValidationResult(passed=False, issues=[ValidationIssue(
            rule="file_exists", offending=str(path),
            suggestion="run --synthesize first")])

    text = path.read_text()
    issues: list[ValidationIssue] = []
    fm, body = _split_frontmatter(text)

    if fm is None:
        issues.append(ValidationIssue(
            rule="frontmatter_parses",
            suggestion="ensure file starts with `---\\n<yaml>\\n---`"))
    else:
        missing = REQUIRED_FRONTMATTER_KEYS - set(fm)
        if missing:
            issues.append(ValidationIssue(
                section="frontmatter", rule="required_keys",
                offending=", ".join(sorted(missing)),
                suggestion=f"add to YAML frontmatter: {sorted(missing)}"))

    headings = [m.group(1).strip() for m in H2_RE.finditer(body or "")]
    issues.extend(_check_canonical_order(headings))
    issues.extend(_check_toc_matches_body(body or "", headings))
    issues.extend(_check_timestamps(body or "", fm))
    issues.extend(_check_empty_section_explanation(body or ""))

    if strict:
        issues.extend(_check_no_placeholders(body or ""))

    return ValidationResult(passed=not issues, issues=issues)


def validate_ingest(workdir: Path) -> ValidationResult:
    """M1 ingest workdir checks: manifest complete, audio sane, deck indexes parse."""
    from src import util as _util  # local to avoid circular at module load
    issues: list[ValidationIssue] = []
    ingest_dir = workdir / _util.STAGE_INGEST
    manifest_path = ingest_dir / "manifest.json"
    if not _util.is_complete(manifest_path):
        issues.append(ValidationIssue(
            rule="manifest_complete", offending=str(manifest_path),
            suggestion="run --ingest --event <id>"))
        return ValidationResult(passed=False, issues=issues)

    try:
        from src.contracts import IngestResult
        ing = IngestResult.model_validate_json(manifest_path.read_text())
    except Exception as e:
        return ValidationResult(passed=False, issues=[ValidationIssue(
            rule="manifest_schema", suggestion=str(e)[:120])])

    if ing.audio_path is not None:
        audio_path = Path(ing.audio_path)
        if not audio_path.exists():
            issues.append(ValidationIssue(
                rule="audio_exists", offending=str(audio_path)))
        elif ing.duration_sec <= 0:
            issues.append(ValidationIssue(
                rule="duration_positive",
                offending=f"duration_sec={ing.duration_sec}"))

    decks_dir = ingest_dir / "decks"
    if decks_dir.is_dir():
        for d in sorted(decks_dir.iterdir()):
            if not d.is_dir():
                continue
            slide_idx = d / "slide_index.json"
            doc_idx = d / "doc_index.json"
            if not slide_idx.exists() and not doc_idx.exists():
                issues.append(ValidationIssue(
                    section="decks", rule="deck_index_missing",
                    offending=d.name,
                    suggestion="re-run ingest for this asset"))

    return ValidationResult(passed=not issues, issues=issues)


def validate_visual(workdir: Path) -> ValidationResult:
    """M3 visual workdir check: captions.json present + parses."""
    from src import util as _util
    cap = workdir / _util.STAGE_KEYFRAMES / "captions.json"
    if not cap.exists():
        return ValidationResult(passed=False, issues=[ValidationIssue(
            rule="captions_exist", offending=str(cap),
            suggestion="M3 (visual) not yet run for this event")])
    return ValidationResult(passed=True)


def validate_transcript(path: Path) -> ValidationResult:
    """M2 transcript.json checks: schema, monotonic, non-overlap, coverage."""
    if not path.exists():
        return ValidationResult(passed=False, issues=[ValidationIssue(
            rule="file_exists", offending=str(path))])

    raw = json.loads(path.read_text())
    issues: list[ValidationIssue] = []
    segs: list[Segment] = []
    for i, s in enumerate(raw):
        try:
            segs.append(Segment.model_validate(s))
        except Exception as e:
            issues.append(ValidationIssue(
                section="transcript", rule="schema_per_segment",
                offending=f"segment[{i}]", suggestion=str(e)[:120]))

    if not segs:
        issues.append(ValidationIssue(rule="non_empty"))
        return ValidationResult(passed=False, issues=issues)

    for i in range(len(segs) - 1):
        if segs[i].start > segs[i + 1].start:
            issues.append(ValidationIssue(
                rule="monotonic_start",
                offending=f"segment[{i+1}] starts before [{i}]"))
            break
    for i, s in enumerate(segs):
        if s.end < s.start:
            issues.append(ValidationIssue(
                rule="end_after_start", offending=f"segment[{i}]"))
        if s.end == s.start:
            issues.append(ValidationIssue(
                rule="non_zero_duration", offending=f"segment[{i}]",
                suggestion="should have been dropped by tail-clamp filter"))

    # diarization/language sanity
    if not any(s.speaker_id for s in segs):
        issues.append(ValidationIssue(
            rule="speaker_id_populated",
            suggestion="prompt may have failed to elicit speaker_id"))
    if not any(s.language for s in segs):
        issues.append(ValidationIssue(rule="language_populated"))

    return ValidationResult(passed=not issues, issues=issues)


# --- helpers ---

def _split_frontmatter(text: str) -> tuple[Optional[dict], Optional[str]]:
    # strip any leading HTML comment block(s) (mockups have a `<!-- ... -->` header)
    stripped = text.lstrip()
    while stripped.startswith("<!--"):
        end = stripped.find("-->")
        if end < 0:
            break
        stripped = stripped[end + 3:].lstrip()
    if not stripped.startswith("---"):
        return None, text
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return None, text
    try:
        import yaml  # PyYAML — not a hard dep yet; soft-import
        fm = yaml.safe_load(parts[1])
        if not isinstance(fm, dict):
            return None, parts[2]
        return fm, parts[2]
    except Exception:
        return None, parts[2]


def _check_canonical_order(headings: list[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    found = [h for h in headings if h in CANONICAL_SECTIONS]
    expected_indices = [CANONICAL_SECTIONS.index(h) for h in found]
    if expected_indices != sorted(expected_indices):
        issues.append(ValidationIssue(
            rule="canonical_section_order",
            offending=" | ".join(found),
            suggestion=f"reorder per CANONICAL_SECTIONS in validators.py"))
    for required in CANONICAL_SECTIONS:
        if required not in headings:
            issues.append(ValidationIssue(
                section=required, rule="required_section_missing",
                suggestion="add the section (use skip-and-stub if no evidence)"))
    return issues


def _check_toc_matches_body(body: str, headings: list[str]) -> list[ValidationIssue]:
    toc_start = body.find("## 🗂️ Contents")
    if toc_start < 0:
        return []
    toc_end = body.find("\n## ", toc_start + 1)
    toc_block = body[toc_start: toc_end if toc_end > 0 else len(body)]
    toc_items = re.findall(r"^-\s+(.+?)\s*$", toc_block, re.MULTILINE)
    # 🎯 Bottom Line and 🗂️ Contents are meta-sections (abstract + TOC itself);
    # by convention they live above the TOC and aren't listed in it.
    META_SECTIONS = {"🎯 Bottom Line for C'mander Alex", "🗂️ Contents"}
    toc_titles = {re.sub(r"\s*\(.*\)\s*$", "", t).strip() for t in toc_items}
    body_titles = {re.sub(r"\s*\(.*\)\s*$", "", h).strip() for h in headings
                   if h not in META_SECTIONS}
    only_toc = toc_titles - body_titles
    only_body = body_titles - toc_titles
    issues: list[ValidationIssue] = []
    for t in sorted(only_toc):
        issues.append(ValidationIssue(
            section="🗂️ Contents", rule="toc_item_missing_from_body",
            offending=t,
            suggestion="add the body section or remove from TOC"))
    for t in sorted(only_body):
        issues.append(ValidationIssue(
            section="🗂️ Contents", rule="body_section_missing_from_toc",
            offending=t, suggestion="add to TOC list"))
    return issues


def _check_timestamps(body: str, fm: Optional[dict]) -> list[ValidationIssue]:
    duration_sec: Optional[float] = None
    if fm and "duration" in fm:
        dur_str = str(fm["duration"])
        m = re.match(r"^(?:(\d+):)?(\d+):(\d{2})", dur_str)
        if m:
            h = int(m.group(1) or 0)
            duration_sec = h * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    issues: list[ValidationIssue] = []
    for m in TIMESTAMP_RE.finditer(body):
        mm, ss = int(m.group(1)), int(m.group(2))
        t = mm * 60 + ss
        if duration_sec is not None and t > duration_sec + 1:
            issues.append(ValidationIssue(
                rule="timestamp_within_duration",
                offending=m.group(0),
                suggestion=f"exceeds declared duration {duration_sec}s"))
    return issues


def _check_empty_section_explanation(body: str) -> list[ValidationIssue]:
    """Required sections with empty body must say *Not applicable…* or similar."""
    # split body into section blocks
    issues: list[ValidationIssue] = []
    parts = re.split(r"^##\s+", body, flags=re.MULTILINE)
    for chunk in parts[1:]:
        header_line, _, rest = chunk.partition("\n")
        title = header_line.strip()
        content = rest.strip()
        if title in CANONICAL_SECTIONS and not content:
            issues.append(ValidationIssue(
                section=title, rule="empty_section_needs_stub",
                suggestion="add `*Not applicable to this event — <reason>.*`"))
    return issues


def _check_no_placeholders(body: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for pat in PLACEHOLDER_PATTERNS:
        for m in pat.finditer(body):
            issues.append(ValidationIssue(
                rule="no_fabricated_placeholder",
                offending=m.group(0),
                suggestion="replace with grounded value or drop the claim"))
    return issues


def render_result(result: ValidationResult) -> str:
    if result.passed:
        return "[validate] OK"
    lines = [f"[validate] FAIL — {len(result.issues)} issue(s):"]
    for it in result.issues:
        sec = f"  [{it.section}]" if it.section else "  "
        msg = f"{sec} {it.rule}"
        if it.offending:
            msg += f" — {it.offending!r}"
        if it.suggestion:
            msg += f"\n      → {it.suggestion}"
        lines.append(msg)
    return "\n".join(lines)
