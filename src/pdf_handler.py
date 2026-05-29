"""PDF text + page renders. Idempotent via doc_index.json cache.

Uses PyMuPDF (fitz) for both text extraction and PNG rendering — no system
deps required (poppler/pdf2image was abandoned because macOS 13 Tier 3
builds from source and stalls).
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from src.contracts import DeckIndex, Slide


def extract(path: Path, out_dir: Path, dpi: int = 120) -> DeckIndex:
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / "doc_index.json"
    if cache.exists():
        return DeckIndex.model_validate_json(cache.read_text())

    doc = fitz.open(str(path))
    try:
        slides: list[Slide] = []
        for i, page in enumerate(doc, start=1):
            text = (page.get_text() or "").strip()
            png_path = out_dir / f"page_{i:03d}.png"
            page.get_pixmap(dpi=dpi).save(str(png_path))
            slides.append(
                Slide(n=i, text=text, speaker_notes="", png_path=png_path)
            )
    finally:
        doc.close()

    idx = DeckIndex(asset_id=_asset_id_from(path), title=path.stem, slides=slides)
    cache.write_text(idx.model_dump_json(indent=2))
    return idx


def _asset_id_from(path: Path) -> str:
    return path.stem.split("-", 1)[0]
