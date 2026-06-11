"""Stage 06 — websearch citation enrichment: related papers/resources for a briefing.

Reads the synthesized briefing (``thematic.json`` + ``notes.md``), derives a handful of
academic search queries from its claims/methods (deterministic — no extra LLM call), queries a
**dedicated search API** behind a ``SearchClient`` seam (arXiv first; Semantic Scholar can drop
in behind the same seam), de-dupes, and writes ``references.md`` + ``references.json``.

Degrade-to-today: if the search source is unreachable or there are no queries, it writes a
skip-stub (like equations.md) and completes — the pipeline never crashes. Resume-safe via the
manifest gate. The seam (``SearchClient``) is faked in tests, so there is zero network in CI.
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Protocol

from src import util

WORK_ROOT = Path("work")
STAGE = util.STAGE_REFERENCES

_ARXIV_API = "https://export.arxiv.org/api/query"   # https — http 301-redirects and breaks SSL
_ATOM = "{http://www.w3.org/2005/Atom}"

# macOS framework Python ships without a usable CA bundle → urllib fails cert verification.
# Use certifi's bundle when available (it's a transitive dep); fall back to the default context.
try:
    import certifi
    _SSL_CTX: Optional[ssl.SSLContext] = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = None

# Filler dropped when turning a claim sentence into a keyword query (arXiv `all:` matches terms,
# not natural-language phrases, so full sentences return nothing).
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "nor", "so", "yet", "of", "to", "in", "on",
    "at", "by", "from", "with", "as", "is", "are", "was", "were", "be", "been", "being", "it",
    "its", "this", "that", "these", "those", "we", "you", "they", "i", "he", "she", "our",
    "your", "their", "not", "no", "just", "very", "much", "more", "most", "can", "will",
    "would", "should", "could", "may", "might", "do", "does", "did", "have", "has", "had",
    "about", "into", "than", "then", "them", "all", "any", "some", "such", "like", "actually",
    "really", "happens", "everything", "anything", "something", "things", "thing", "one",
    "also", "because", "which", "what", "when", "how", "why", "where", "who", "still", "even",
    "only", "now", "new", "good", "bad", "terrible", "better", "worse", "before", "after",
}


@dataclass
class Reference:
    title: str
    authors: list = field(default_factory=list)
    year: Optional[int] = None
    url: str = ""
    arxiv_id: str = ""
    summary: str = ""
    query: str = ""


class SearchClient(Protocol):
    def search(self, query: str, limit: int = 3) -> list[Reference]: ...


class NullSearchClient:
    """The skip path — returns nothing (search unavailable)."""
    def search(self, query: str, limit: int = 3) -> list[Reference]:
        return []


class ArxivClient:
    """arXiv Atom API — no key, no dependency (stdlib urllib + ElementTree). Each call is wrapped
    in ``util.retry_transient`` so a transient blip retries rather than dropping the query."""
    def search(self, query: str, limit: int = 3) -> list[Reference]:
        def _do() -> list[Reference]:
            qs = urllib.parse.urlencode(
                {"search_query": f"all:{query}", "start": 0, "max_results": limit})
            req = urllib.request.Request(f"{_ARXIV_API}?{qs}",
                                         headers={"User-Agent": "lsic-pipeline/1.0"})
            with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as r:
                return _parse_arxiv_atom(r.read().decode(), query)
        return util.retry_transient(_do)


def _parse_arxiv_atom(xml_text: str, query: str) -> list[Reference]:
    root = ET.fromstring(xml_text)
    refs: list[Reference] = []
    for e in root.findall(f"{_ATOM}entry"):
        title = (e.findtext(f"{_ATOM}title") or "").strip().replace("\n", " ")
        idu = (e.findtext(f"{_ATOM}id") or "").strip()
        arxiv_id = idu.rsplit("/", 1)[-1]
        published = (e.findtext(f"{_ATOM}published") or "")[:4]
        authors = [a.findtext(f"{_ATOM}name") for a in e.findall(f"{_ATOM}author")]
        summary = (e.findtext(f"{_ATOM}summary") or "").strip().replace("\n", " ")
        refs.append(Reference(
            title=title, authors=[a for a in authors if a],
            year=int(published) if published.isdigit() else None,
            url=idu, arxiv_id=arxiv_id, summary=summary[:300], query=query))
    return refs


def make_search_client() -> Optional[SearchClient]:
    """The live default search client (arXiv). Returns None if it can't be constructed — the
    caller treats None as 'search unavailable' → skip-stub."""
    try:
        return ArxivClient()
    except Exception:
        return None


def _keywordize(text: str, max_words: int = 6) -> str:
    """Turn a claim sentence into a short keyword query — arXiv `all:` matches terms, not
    natural-language phrases, so we drop stopwords/cites and keep the distinctive terms."""
    text = re.sub(r"`?\[[0-9:]+\]`?", " ", text.lower())          # strip [mm:ss] cites
    words = re.findall(r"[a-z][a-z0-9-]{2,}", text)
    kept = [w for w in words if w not in _STOPWORDS]
    return " ".join(kept[:max_words])


def derive_queries(thematic: dict, notes_md: str = "", k: int = 6) -> list[str]:
    """Deterministic keyword-query extraction from the structured briefing (no LLM, no network).
    Pulls the technical claims/points/methods (NOT the talk title, which is identity not topic)
    and keyword-ifies each; falls back to notes.md bullets."""
    raw: list[str] = []
    if thematic:
        for key in ("notable_claims", "key_points", "methods"):
            for item in thematic.get(key, []) or []:
                txt = (item.get("text") if isinstance(item, dict) else str(item)) or ""
                if txt.strip():
                    raw.append(txt.strip())
    if not raw and notes_md:
        raw = [ln.lstrip("-* ").strip() for ln in notes_md.splitlines()
               if ln.lstrip().startswith(("-", "*"))]
    seen: set[str] = set()
    out: list[str] = []
    for q in raw:
        kw = _keywordize(q)
        if len(kw.split()) >= 2 and kw not in seen:        # need ≥2 terms for a useful search
            seen.add(kw)
            out.append(kw)
        if len(out) >= k:
            break
    return out


def _dedupe_refs(refs: list[Reference]) -> list[Reference]:
    seen: set[str] = set()
    out: list[Reference] = []
    for r in refs:
        key = r.arxiv_id or r.title.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _render_md(event_id: str, queries: list[str], refs: list[Reference]) -> str:
    if not refs:
        reason = "no related papers found" if queries else "no queries derived"
        return (f"# References & Related Work\n\n"
                f"*Auto-suggested external resources — {reason} for {event_id}.*\n")
    by_query: dict[str, list[Reference]] = {}
    for r in refs:
        by_query.setdefault(r.query, []).append(r)
    out = ["# References & Related Work\n",
           f"*Auto-suggested from {len(queries)} quer{'y' if len(queries)==1 else 'ies'} "
           f"via arXiv — related external resources, not cited in the source.*\n"]
    for q, rs in by_query.items():
        out.append(f"## {q}")
        for r in rs:
            who = ", ".join(r.authors[:3]) + (" et al." if len(r.authors) > 3 else "")
            yr = f" ({r.year})" if r.year else ""
            out.append(f"- **{r.title}** — {who}{yr}. [arXiv:{r.arxiv_id}]({r.url})")
        out.append("")
    return "\n".join(out)


def _load_thematic(briefing_dir: Path) -> dict:
    p = briefing_dir / "thematic.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def enrich_citations(event_id: str, work_root: Path = WORK_ROOT,
                     client: Optional[SearchClient] = None, k: int = 6) -> Path:
    """Derive queries → search → references.md/.json. Resume-safe + degrade-to-today.
    ``client`` is injectable (tests pass a fake; None → live arXiv via make_search_client)."""
    workdir = work_root / "events" / event_id
    briefing = workdir / util.STAGE_BRIEFING
    ref_md = workdir / STAGE / "references.md"
    if util.is_complete(ref_md):
        print(f"  [enrich] {event_id} … CACHED", flush=True)
        return ref_md

    thematic = _load_thematic(briefing)
    notes_md = (briefing / "notes.md").read_text() if (briefing / "notes.md").exists() else ""
    queries = derive_queries(thematic, notes_md, k=k)

    if client is None:
        client = make_search_client()
    refs: list[Reference] = []
    if client is not None:
        for q in queries:
            try:
                refs.extend(client.search(q, limit=3))
            except Exception as e:               # per-query failure isolated (retry is inside)
                print(f"    [enrich] query failed ({q[:40]}…): {e}", flush=True)
    refs = _dedupe_refs(refs)

    md = _render_md(event_id, queries, refs)
    js = json.dumps({"event_id": event_id, "queries": queries,
                     "references": [asdict(r) for r in refs]}, indent=2)
    util.write_with_manifest(ref_md, md, stage="enrich_citations")
    util.write_with_manifest(workdir / STAGE / "references.json", js, stage="enrich_citations")
    # deliverable copy into 05_briefing so report.assemble_report ships it in Report/
    util.atomic_write_text(briefing / "references.md", md)
    print(f"[enrich] {event_id} → {len(refs)} refs from {len(queries)} queries", flush=True)
    return ref_md
