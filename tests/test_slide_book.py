"""Fakes-only unit tests for the slide_book VLM-failure caching fix.

Finding from the DeMattia verify run: a 503 on one slide was cached as a stub, silently
dropping that slide forever (reruns hit the cached failure). The fix caches ONLY on success
so a rerun retries (R4, matching the batch path). These pin that contract.
"""
import json

from src import slide_book


def test_curate_slide_caches_on_success(tmp_path, monkeypatch):
    cache = tmp_path / "slide_001.curated.json"
    monkeypatch.setattr(slide_book, "_vlm_curate",
                        lambda d, p: {"kind": "diagram", "is_informative": True})
    out = slide_book._curate_slide(describer=None, png_path=tmp_path / "x.png",
                                   cache_path=cache)
    assert out["kind"] == "diagram"
    assert cache.exists()                                   # success → cached
    assert json.loads(cache.read_text())["kind"] == "diagram"


def test_curate_slide_does_not_cache_failure(tmp_path, monkeypatch):
    cache = tmp_path / "slide_002.curated.json"

    def boom(describer, png):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(slide_book, "_vlm_curate", boom)
    out = slide_book._curate_slide(describer=None, png_path=tmp_path / "x.png",
                                   cache_path=cache)
    assert out == slide_book._FAILED_SLIDE_STUB             # stub for THIS run only
    assert not cache.exists()                               # R4: NOT cached → rerun retries


def test_failed_stub_is_copied_not_shared(tmp_path, monkeypatch):
    """Each failure returns its own dict so a caller mutating one can't corrupt the constant."""
    monkeypatch.setattr(slide_book, "_vlm_curate",
                        lambda d, p: (_ for _ in ()).throw(RuntimeError("boom")))
    a = slide_book._curate_slide(None, tmp_path / "a.png", tmp_path / "a.json")
    a["topic"] = "mutated"
    assert slide_book._FAILED_SLIDE_STUB["topic"] == ""     # constant untouched
