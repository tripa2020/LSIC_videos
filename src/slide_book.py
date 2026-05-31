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
  "kind": "graph"|"diagram"|"model"|"image"|"table"|"equation"|"text-only",
  "bbox": {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0}
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

contains_equation=true only when a mathematical equation appears (not just numbers in text).

bbox is the NORMALIZED bounding box (each coordinate 0.0 to 1.0) of the
informative region of the slide. EXCLUDE: title bar at top, footer/page
number at bottom, company logos, copyright notices, branding chrome. If the
entire slide is informative with no chrome to crop, return
{"x0":0,"y0":0,"x1":1,"y1":1}. Be generous (don't crop too tight) — better to
include a sliver of margin than chop off useful content."""


_STOPWORDS = {
    "the", "and", "for", "with", "of", "in", "to", "a", "an", "from",
    "on", "by", "as", "at", "is", "are", "this", "that", "lsic", "nasa",
}


def slide_book(event_id: str, work_root: Path = WORK_ROOT) -> tuple[Path, Path, Path]:
    """Produce slides.pdf + slide_captions.md + equations.md. Returns all three paths."""
    workdir = work_root / "events" / event_id
    briefing_dir = workdir / util.STAGE_BRIEFING
    briefing_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = briefing_dir / "slides.pdf"
    captions_path = briefing_dir / "slide_captions.md"
    equations_path = briefing_dir / "equations.md"

    if all(util.is_complete(p) for p in (pdf_path, captions_path, equations_path)):
        return pdf_path, captions_path, equations_path

    decks_dir = workdir / util.STAGE_INGEST / "decks"
    deck_slides = _load_all_deck_slides(decks_dir)
    if not deck_slides:
        _render_empty_pdf(pdf_path, event_id)
        _write_pdf_manifest(pdf_path)
        util.write_with_manifest(captions_path,
            f"# Slide Captions — {event_id}\n\n*No decks available for this event.*\n",
            stage="slide_book")
        util.write_with_manifest(equations_path,
            f"# Equations — {event_id}\n\n*No decks available for this event.*\n",
            stage="slide_book")
        return pdf_path, captions_path, equations_path

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
            bbox=d.get("bbox"),
        ))

    keep = [s for s in curated
            if s.is_informative and s.kind != "text-only" and s.topic]
    print(f"  [slide_book] kept {len(keep)}/{len(curated)} after filter",
          flush=True)

    clusters = _cluster_topics(keep)
    eq_slides = [s for s in keep if s.contains_equation]

    # Crop each kept slide per its VLM bbox; emit cropped PNGs alongside originals
    cropped_dir = briefing_dir / "_cropped"
    cropped_dir.mkdir(exist_ok=True)
    ordered: list[tuple[str, CuratedSlide, Path]] = []  # (cluster_label, slide, cropped_png)
    for label, slides in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        for s in slides:
            cropped_png = _crop_slide(s, cropped_dir)
            ordered.append((label, s, cropped_png))

    _render_pdf(ordered, pdf_path, event_id)
    _write_pdf_manifest(pdf_path)
    util.write_with_manifest(
        captions_path,
        _render_captions_md(event_id, ordered),
        stage="slide_book",
    )
    util.write_with_manifest(
        equations_path,
        _render_equations_md(event_id, eq_slides),
        stage="slide_book",
    )
    return pdf_path, captions_path, equations_path


def _load_all_deck_slides(decks_dir: Path) -> list[tuple[str, int, Path]]:
    """Walk decks/ and return [(asset_id, slide_n, png_path), ...].

    Derives the PNG path from the deck directory + slide number, ignoring any
    `png_path` field in slide_index.json (which can go stale if the workdir
    was moved or refactored). Tries both `slide_NNN.png` (PPTX) and
    `page_NNN.png` (PDF) naming conventions.
    """
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
            n = int(s.get("n", 0))
            png: Optional[Path] = None
            for prefix in ("slide", "page"):
                candidate = d / f"{prefix}_{n:03d}.png"
                if candidate.exists():
                    png = candidate
                    break
            if png is None:
                print(f"  [slide_book] missing PNG for {d.name}#{n}; skipping",
                      flush=True)
                continue
            out.append((d.name, n, png))
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


# --- PDF + sidecar rendering ---

def _slide_key(label: str, slide: CuratedSlide) -> str:
    """Compact human key shown in the PDF footer + caption sidecar."""
    cluster_short = re.sub(r"\s+", "", label.title())[:18]
    return f"{cluster_short}-{slide.asset_id}#{slide.slide_n}"


def _crop_slide(slide: CuratedSlide, out_dir: Path) -> Path:
    """Crop PNG to slide.bbox (or no-op if missing/full-frame). Returns cropped path."""
    from PIL import Image
    src = Path(slide.png_path)
    out = out_dir / f"{slide.asset_id}_{slide.slide_n:03d}.png"
    if out.exists():
        return out
    img = Image.open(src)
    W, H = img.size
    bb = slide.bbox or {}
    x0 = max(0, int(float(bb.get("x0", 0.0)) * W))
    y0 = max(0, int(float(bb.get("y0", 0.0)) * H))
    x1 = min(W, int(float(bb.get("x1", 1.0)) * W))
    y1 = min(H, int(float(bb.get("y1", 1.0)) * H))
    if x1 - x0 < 50 or y1 - y0 < 50:
        # bbox returned garbage — fall back to no crop
        x0, y0, x1, y1 = 0, 0, W, H
    img.crop((x0, y0, x1, y1)).save(out, "PNG")
    return out


def _render_pdf(ordered: list[tuple[str, CuratedSlide, Path]],
                pdf_path: Path, event_id: str) -> None:
    """Vertical image-only PDF — one cropped slide per page, with a small key footer."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    PAGE_W, PAGE_H = letter
    MARGIN = 36         # 0.5 inch
    FOOTER_GAP = 14     # space for key line
    c = canvas.Canvas(str(pdf_path), pagesize=letter)

    # cover page
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 200, "Slide Book")
    c.setFont("Helvetica", 14)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 230, event_id)
    c.setFont("Helvetica", 10)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 260,
                        f"{len(ordered)} curated slides — captions in slide_captions.md")
    c.showPage()

    for label, slide, cropped_png in ordered:
        img = ImageReader(str(cropped_png))
        iw, ih = img.getSize()
        avail_w = PAGE_W - 2 * MARGIN
        avail_h = PAGE_H - 2 * MARGIN - FOOTER_GAP
        scale = min(avail_w / iw, avail_h / ih)
        w, h = iw * scale, ih * scale
        x = (PAGE_W - w) / 2
        y = MARGIN + FOOTER_GAP + (avail_h - h) / 2
        c.drawImage(img, x, y, w, h, preserveAspectRatio=True)
        # footer key
        c.setFont("Helvetica", 8)
        c.setFillGray(0.4)
        c.drawString(MARGIN, MARGIN / 2, _slide_key(label, slide))
        c.drawRightString(PAGE_W - MARGIN, MARGIN / 2,
                          f"page {c.getPageNumber()}")
        c.setFillGray(0)
        c.showPage()

    c.save()


def _render_empty_pdf(pdf_path: Path, event_id: str) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    PAGE_W, PAGE_H = letter
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(PAGE_W / 2, PAGE_H / 2,
                        f"Slide Book — {event_id}")
    c.setFont("Helvetica", 12)
    c.drawCentredString(PAGE_W / 2, PAGE_H / 2 - 30,
                        "No decks available for this event.")
    c.save()


def _write_pdf_manifest(pdf_path: Path) -> None:
    """Manual manifest write (util.write_with_manifest is text-only)."""
    from datetime import datetime, timezone
    util.atomic_write_text(
        pdf_path.with_suffix(pdf_path.suffix + ".manifest.json"),
        json.dumps({
            "stage": "slide_book", "status": "complete",
            "artifact": pdf_path.name,
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, indent=2),
    )


def _render_captions_md(event_id: str,
                        ordered: list[tuple[str, CuratedSlide, Path]]) -> str:
    """Editable sidecar — table of key, topic, source, commentary."""
    if not ordered:
        return (f"# Slide Captions — {event_id}\n\n"
                f"*No informative slides identified in this event's decks.*\n")
    lines = [f"# Slide Captions — {event_id}", "",
             f"*{len(ordered)} curated slides. Edit any commentary below; the "
             f"key column matches the footer in `slides.pdf`. Sorted by topic.*",
             ""]
    # group by cluster label for readable sections
    current_label = None
    for label, slide, _ in ordered:
        if label != current_label:
            lines.append("")
            lines.append(f"## {label.title()}")
            lines.append("")
            current_label = label
        key = _slide_key(label, slide)
        lines.append(f"### `{key}`  ·  *{slide.kind}*")
        lines.append("")
        lines.append(slide.commentary or "_(no commentary)_")
        lines.append("")
    return "\n".join(lines)


def _render_equations_md(event_id: str, slides: list[CuratedSlide]) -> str:
    if not slides:
        return (f"# Equations — {event_id}\n\n"
                f"*No equations identified in this event's slides.*\n")
    lines = [f"# Equations — {event_id}", "",
             f"*{len(slides)} slide(s) flagged as containing equations. "
             f"See slides.pdf for the image; keys below match the PDF footer.*",
             ""]
    for s in slides:
        key = _slide_key(s.topic, s)
        lines.append(f"### `{key}`")
        lines.append("")
        lines.append(s.commentary or "_(no commentary)_")
        lines.append("")
    return "\n".join(lines)
