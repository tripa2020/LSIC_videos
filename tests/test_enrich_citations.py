"""Fakes-only, no-network tests for the citation-enrichment stage (src/enrich_citations.py).

Contract under test
- Intent: derive academic queries from a briefing, search a dedicated API behind a seam, write
  references.md/.json; degrade to a skip-stub when search is unavailable; resume-safe.
- Invariants: NO network (SearchClient injected); is_complete gate short-circuits (no re-spend);
  null/unavailable client → skip-stub + manifest complete (never crashes); refs de-duped;
  query derivation is deterministic and strips [mm:ss] cites.
- Oracles: returned/written files, parsed Reference fields, client call records, raised-nothing.
"""
import json

import pytest

from src import enrich_citations as ec
from src import util


# ---------- query derivation (deterministic) ----------

def test_derive_queries_from_thematic_strips_cites_and_dedupes():
    th = {"title": "RL for Grasping",
          "notable_claims": [{"text": "SAC improves efficiency `[00:12]`"}],
          "key_points": [{"text": "off-policy"}, {"text": "off-policy"}]}   # dup
    qs = ec.derive_queries(th, k=5)
    assert qs == ["RL for Grasping", "SAC improves efficiency", "off-policy"]   # cite stripped, deduped


def test_derive_queries_caps_k():
    th = {"key_points": [{"text": f"point {i}"} for i in range(20)]}
    assert len(ec.derive_queries(th, k=4)) == 4


def test_derive_queries_fallback_to_notes_bullets():
    qs = ec.derive_queries({}, notes_md="# T\n- first claim\n- second claim\nprose line\n", k=5)
    assert qs == ["first claim", "second claim"]


# ---------- arxiv atom parse ----------

def test_parse_arxiv_atom():
    xml = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
           '<title>Proximal Policy Optimization</title>'
           '<id>http://arxiv.org/abs/1707.06347v1</id>'
           '<published>2017-07-20T00:00:00Z</published>'
           '<author><name>J. Schulman</name></author><author><name>F. Wolski</name></author>'
           '<summary>PPO algorithms.</summary></entry></feed>')
    refs = ec._parse_arxiv_atom(xml, "ppo")
    assert len(refs) == 1
    r = refs[0]
    assert r.title == "Proximal Policy Optimization" and r.arxiv_id == "1707.06347v1"
    assert r.year == 2017 and r.authors == ["J. Schulman", "F. Wolski"] and r.query == "ppo"


def test_dedupe_refs_by_arxiv_id():
    a = ec.Reference(title="X", arxiv_id="1.1", query="q1")
    b = ec.Reference(title="X (v2)", arxiv_id="1.1", query="q2")     # same id
    c = ec.Reference(title="Y", arxiv_id="2.2", query="q1")
    assert [r.arxiv_id for r in ec._dedupe_refs([a, b, c])] == ["1.1", "2.2"]


# ---------- enrich_citations stage ----------

class _FakeClient:
    def __init__(self, refs):
        self._refs = refs
        self.calls: list[str] = []

    def search(self, query: str, limit: int = 3):
        self.calls.append(query)
        return [ec.Reference(title=r.title, arxiv_id=r.arxiv_id, url=r.url,
                             authors=r.authors, year=r.year, query=query) for r in self._refs]


class _BoomClient:
    def search(self, query: str, limit: int = 3):
        raise AssertionError("client should not be called when CACHED")


def _seed_briefing(work_root, event_id, thematic, notes="# notes\n"):
    d = work_root / "events" / event_id / util.STAGE_BRIEFING
    d.mkdir(parents=True, exist_ok=True)
    (d / "thematic.json").write_text(json.dumps(thematic))
    (d / "notes.md").write_text(notes)


def test_enrich_with_fake_client_writes_outputs(tmp_path):
    _seed_briefing(tmp_path, "yt_x", {"title": "RL grasping", "key_points": [{"text": "off-policy"}]})
    client = _FakeClient([ec.Reference(title="Deep RL", arxiv_id="1707.06347", url="http://arxiv.org/abs/1707.06347")])
    out = ec.enrich_citations("yt_x", work_root=tmp_path, client=client)
    assert out.exists()                                           # 06_references/references.md
    md = out.read_text()
    assert "Deep RL" in md and "arXiv:1707.06347" in md
    js = json.loads((tmp_path / "events" / "yt_x" / util.STAGE_REFERENCES / "references.json").read_text())
    assert js["event_id"] == "yt_x" and js["references"][0]["arxiv_id"] == "1707.06347"
    # deliverable copy lands in 05_briefing so report.assemble_report ships it
    assert (tmp_path / "events" / "yt_x" / util.STAGE_BRIEFING / "references.md").exists()
    assert client.calls                                           # queries were issued


def test_enrich_null_client_skip_stub_no_crash(tmp_path):
    _seed_briefing(tmp_path, "yt_x", {"title": "X"})
    out = ec.enrich_citations("yt_x", work_root=tmp_path, client=ec.NullSearchClient())
    assert out.exists()
    assert "Auto-suggested external resources" in out.read_text()   # skip-stub
    assert util.is_complete(out)                                    # manifest complete (resume-safe)


def test_enrich_skips_when_complete(tmp_path):
    _seed_briefing(tmp_path, "yt_x", {"title": "X"})
    ref_md = tmp_path / "events" / "yt_x" / util.STAGE_REFERENCES / "references.md"
    util.write_with_manifest(ref_md, "# pre-existing\n", stage="enrich_citations")
    # a client that raises if consulted — proves the cache gate short-circuits before searching
    out = ec.enrich_citations("yt_x", work_root=tmp_path, client=_BoomClient())
    assert out.read_text() == "# pre-existing\n"


def test_enrich_no_queries_skip_stub(tmp_path):
    _seed_briefing(tmp_path, "yt_x", {}, notes="")                  # nothing to derive
    out = ec.enrich_citations("yt_x", work_root=tmp_path, client=_FakeClient([]))
    assert util.is_complete(out) and "no queries derived" in out.read_text()
