"""M5.5: topical slide book — per-slide VLM curation → slides.md + equations.md.

Reads M1's deck PNG renders (one per slide), runs a Gemini VLM filter on each
to drop title/agenda/contact/bio slides, clusters surviving slides by topic
phrase keyword overlap, and renders a single continuous markdown document
with embedded images + concise commentary.

Outputs: 05_briefing/slides.md, 05_briefing/equations.md (latter usually short).

Per-slide cache: 01_ingest/decks/<asset_id>/slide_NNN.curated.json so reruns
skip the VLM call.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from src import util
from src.contracts import CuratedSlide
from src.visual import GeminiDescriber  # reuse the Gemini client wrapper


WORK_ROOT = Path("work")

VLM_PROMPT = """Look at this slide from a meeting presentation.

Return ONLY a JSON object (no markdown fences, no prose):
{
  "is_informative": true|false,
  "topic": "<3-5 word topic phrase, lowercase, e.g. 'thermal control', 'battery sizing', 'dust mitigation', 'connector design'>",
  "commentary": "<1-2 sentences describing what the slide shows. Focus on technical content. Cite numeric values, equations, or specific features visible. Skip any references to the presenter.>",
  "contains_equation": true|false,
  "kind": "graph"|"diagram"|"model"|"image"|"table"|"equation"|"text-only"
}

is_informative=true ONLY if the slide has:
  - An equation (LaTeX or rendered math)
  - A quantitative graph or chart with axes/data
  - A system diagram, schematic, block diagram, or flow chart
  - A model figure, CAD render, or 3D visualization
  - A photograph of hardware, a test setup, or an instrument
  - A data table with numeric values

is_informative=false if the slide is:
  - Title-only / cover slide
  - Agenda or table of contents
  - Contact info, "thank you", or "questions?" slide
  - Speaker biography or headshot only
  - Pure-text bullet list without technical figures, numbers, or equations

contains_equation=true only when a mathematical equation appears (not just numbers in text)."""


_STOPWORDS = {
    "the", "and", "for", "with", "of", "in", "to", "a", "an", "from",
    "on", "by", "as", "at", "is", "are", "this", "that", "lsic", "nasa",
}


def slide_book(event_id: str, work_root: Path = WORK_ROOT) -> tuple[Path, Path]:
    """Produce slides.md + equations.md in 05_briefing/. Returns both paths."""
    workdir = work_root / "events" / event_id
    briefing_dir = workdir / util.STAGE_BRIEFING
    briefing_dir.mkdir(parents=True, exist_ok=True)
    slides_path = briefing_dir / "slides.md"
    equations_path = briefing_dir / "equations.md"

    if util.is_complete(slides_path) and util.is_complete(equations_path):
        return slides_path, equations_path

    decks_dir = workdir / util.STAGE_INGEST / "decks"
    deck_slides = _load_all_deck_slides(decks_dir)
    if not deck_slides:
        slides_md = f"# Slide Book — {event_id}\n\n*No decks available for this event.*\n"
        equations_md = f"# Equations — {event_id}\n\n*No decks available for this event.*\n"
        util.write_with_manifest(slides_path, slides_md, stage="slide_book")
        util.write_with_manifest(equations_path, equations_md, stage="slide_book")
        return slides_path, equations_path

    print(f"  [slide_book] {len(deck_slides)} total slides across "
          f"{len({s[0] for s in deck_slides})} decks", flush=True)

    describer = GeminiDescriber()
    curated: list[CuratedSlide] = []
    for i, (asset_id, slide_n, png_path) in enumerate(deck_slides, start=1):
        cache_path = png_path.with_suffix(".curated.json")
        if cache_path.exists():
            d = json.loads(cache_path.read_text())
        else:
            print(f"  [slide_book] slide {i}/{len(deck_slides)} "
                  f"{asset_id}#{slide_n}…", flush=True, end=" ")
            try:
                d = _vlm_curate(describer, png_path)
                print(f"ok ({d.get('kind', '?')})")
            except Exception as e:
                print(f"FAILED: {e}")
                d = {"is_informative": False, "topic": "", "commentary": "",
                     "contains_equation": False, "kind": "text-only"}
            cache_path.write_text(json.dumps(d, indent=2))
        curated.append(CuratedSlide(
            asset_id=asset_id, slide_n=slide_n, png_path=png_path,
            is_informative=bool(d.get("is_informative", False)),
            topic=str(d.get("topic", "")).strip().lower(),
            commentary=str(d.get("commentary", "")).strip(),
            contains_equation=bool(d.get("contains_equation", False)),
            kind=d.get("kind", "text-only"),
        ))

    keep = [s for s in curated
            if s.is_informative and s.kind != "text-only" and s.topic]
    print(f"  [slide_book] kept {len(keep)}/{len(curated)} after filter",
          flush=True)

    clusters = _cluster_topics(keep)
    eq_slides = [s for s in keep if s.contains_equation]

    util.write_with_manifest(
        slides_path,
        _render_slides_md(event_id, clusters, briefing_dir),
        stage="slide_book",
    )
    util.write_with_manifest(
        equations_path,
        _render_equations_md(event_id, eq_slides, briefing_dir),
        stage="slide_book",
    )
    return slides_path, equations_path


def _load_all_deck_slides(decks_dir: Path) -> list[tuple[str, int, Path]]:
    """Walk decks/ and return [(asset_id, slide_n, png_path), ...]."""
    out: list[tuple[str, int, Path]] = []
    if not decks_dir.is_dir():
        return out
    for d in sorted(decks_dir.iterdir()):
        if not d.is_dir():
            continue
        idx_path = d / "slide_index.json"
        if not idx_path.exists():
            idx_path = d / "doc_index.json"
        if not idx_path.exists():
            continue
        data = json.loads(idx_path.read_text())
        for s in data.get("slides", []):
            png = s.get("png_path")
            if not png:
                continue
            out.append((d.name, int(s.get("n", 0)), Path(png)))
    return out


def _vlm_curate(describer: GeminiDescriber, png_path: Path) -> dict:
    """One Gemini VLM call per slide. Returns the curated dict."""
    from google.genai import types
    img_bytes = png_path.read_bytes()
    resp = describer.client.models.generate_content(
        model=describer.model,
        contents=[
            VLM_PROMPT,
            types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
        ],
        config=types.GenerateContentConfig(
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return json.loads(util.strip_fences(resp.text or ""))


def _topic_words(t: str) -> set[str]:
    return {w for w in re.findall(r"\b[a-z]{3,}\b", t.lower())
            if w not in _STOPWORDS}


def _cluster_topics(slides: list[CuratedSlide]) -> dict[str, list[CuratedSlide]]:
    """Cluster slides by topic-keyword overlap. Returns {canonical_label: [slides]}."""
    clusters: list[dict] = []
    for s in slides:
        words = _topic_words(s.topic)
        if not words:
            continue
        matched = None
        for c in clusters:
            if words & c["words"]:
                matched = c
                break
        if matched:
            matched["slides"].append(s)
            matched["words"] |= words
            matched["topics"].append(s.topic)
        else:
            clusters.append({"slides": [s], "words": words, "topics": [s.topic]})

    # Build display dict, using most-common topic phrase in each cluster as label
    result: dict[str, list[CuratedSlide]] = {}
    for c in clusters:
        label = Counter(c["topics"]).most_common(1)[0][0]
        result[label] = c["slides"]
    return result


def _render_slides_md(event_id: str, clusters: dict[str, list[CuratedSlide]],
                      briefing_dir: Path) -> str:
    if not clusters:
        return (f"# Slide Book — {event_id}\n\n"
                f"*No informative slides identified in this event's decks.*\n")

    lines = [f"# Slide Book — {event_id}", "",
             f"*{sum(len(v) for v in clusters.values())} slides across "
             f"{len(clusters)} topics. Sorted by topic, most-populated first.*",
             "", "---", ""]
    sorted_clusters = sorted(clusters.items(), key=lambda kv: -len(kv[1]))
    for topic, slides in sorted_clusters:
        lines.append(f"## {topic.title()}")
        lines.append("")
        for s in slides:
            rel = os.path.relpath(str(s.png_path), str(briefing_dir))
            alt = f"{s.asset_id}#{s.slide_n} ({s.kind})"
            lines.append(f"![{alt}]({rel})")
            if s.commentary:
                lines.append(f"*{s.commentary}*")
            lines.append("")
    return "\n".join(lines)


def _render_equations_md(event_id: str, slides: list[CuratedSlide],
                         briefing_dir: Path) -> str:
    if not slides:
        return (f"# Equations — {event_id}\n\n"
                f"*No equations identified in this event's slides.*\n")

    lines = [f"# Equations — {event_id}", "",
             f"*{len(slides)} slide(s) flagged as containing equations.*",
             "", "---", ""]
    for s in slides:
        rel = os.path.relpath(str(s.png_path), str(briefing_dir))
        lines.append(f"### {s.topic.title() or 'equation'} "
                     f"— {s.asset_id}#{s.slide_n}")
        lines.append("")
        lines.append(f"![equation]({rel})")
        if s.commentary:
            lines.append(f"*{s.commentary}*")
        lines.append("")
    return "\n".join(lines)
