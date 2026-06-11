"""Fakes-only tests for notes-template profiles (src/profiles).

Contract under test
- Intent: select the notes template per run; default 'briefing' = today verbatim; 'lecture'
  = one generic talk template (Expert Lenses + chapters Outline + description links).
- Invariants: briefing profile reuses synthesize's UNCHANGED render/prompt (byte-identical);
  unknown profile raises listing valid names; lecture render degrades empty sections, omits
  the Outline when no chapters, and never emits LSIC-only sections; _call_thematic honors the
  injected system prompt; briefing render tolerates the uniform source_meta kwarg.
- Oracles: identity (`is`) of relocated symbols, raised KeyError, rendered headings/strings,
  captured system-prompt argument.
"""
import inspect
import types

import pytest

from src import profiles
from src.profiles import lecture


# ---------- registry ----------

def test_default_profile_is_briefing_verbatim():
    from src import synthesize
    b = profiles.get_profile(None)                      # None → DEFAULT_PROFILE
    assert b.name == "briefing"
    assert b.render is synthesize._render_briefing      # the unchanged LSIC render
    assert b.thematic_system_prompt is synthesize.THEMATIC_SYSTEM_PROMPT
    assert b.uses_presentations and b.uses_role_pool


def test_lecture_profile_distinct():
    l = profiles.get_profile("lecture")
    assert l.name == "lecture" and l.render is lecture.render_lecture
    assert not l.uses_presentations and not l.uses_role_pool


def test_unknown_profile_raises_listing_valid():
    with pytest.raises(KeyError) as ei:
        profiles.get_profile("bogus")
    assert "briefing" in str(ei.value) and "lecture" in str(ei.value)


def test_briefing_render_accepts_source_meta_kwarg():
    # the **_kwargs sink lets synthesize_full call every profile's render uniformly
    sig = inspect.signature(profiles.get_profile("briefing").render)
    assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


# ---------- lecture render ----------

def _ing(dur=600.0):
    return types.SimpleNamespace(duration_sec=dur)

def _align(event_id="yt_abc"):
    return types.SimpleNamespace(event_id=event_id, sections=[], presentations=[])

_FULL_THEMATIC = {
    "title": "Reinforcement Learning for Grasping",
    "summary": "A talk on sample-efficient RL for robotic grasping.",
    "expert_lenses": [{"role": "ML Researcher", "emoji": "🧠",
                       "take": "Off-policy RL is the key lever.", "evidence_id": "ev_1"}],
    "key_points": [{"text": "Off-policy RL improves sample efficiency", "evidence_id": "ev_1"}],
    "methods": [{"text": "Soft Actor-Critic with HER", "evidence_id": "ev_2"}],
    "notable_claims": [{"text": "90% grasp success", "basis": "200-trial eval", "evidence_id": "ev_3"}],
    "open_questions": [], "takeaways": [{"text": "Use dense rewards", "evidence_id": "ev_1"}],
    "field_implications": [{"text": "Learn JAX for accelerator-native RL", "evidence_id": "ev_2"}],
    "industry_outlook": {"fading": [{"text": "Hand-tuned PID controllers", "evidence_id": "ev_3"}],
                         "thriving": [{"text": "Learned end-to-end policies", "evidence_id": "ev_1"}]},
    "speakers": [{"label": "A", "role": "presenter", "time_range": "00:00→09:00"}],
    "citations": [{"text": "Andrychowicz et al. HER", "evidence_id": "ev_2"}],
}
_EV = {"ev_1": types.SimpleNamespace(timestamp_start=12.0),
       "ev_2": types.SimpleNamespace(timestamp_start=130.0),
       "ev_3": types.SimpleNamespace(timestamp_start=300.0)}


def test_lecture_render_full_sections():
    sm = {"chapters": [{"title": "Intro", "start_time": 0}, {"title": "Method", "start_time": 125}],
          "description": "paper https://arxiv.org/abs/1707.06347 and https://example.com/x."}
    md = lecture.render_lecture(ing=_ing(), alignment=_align(), pres_outputs=[],
                                thematic=_FULL_THEMATIC, slide_highlights=[], evidence_by_id=_EV,
                                event_date="2026-06-11", n_speakers=1, source_meta=sm)
    for h in ["## Summary", "## Through 1 Expert Lenses", "## Outline", "## Key Points",
              "## Methods / Approach", "## Notable Claims & Evidence", "## Open Questions",
              "## Takeaways", "## Field Implications — Where to Steer",
              "## Industry Outlook — Fading vs Thriving", "## Speakers",
              "## References & Resources Mentioned"]:
        assert h in md, f"missing {h}"
    assert "Learn JAX" in md                                  # field implication
    assert "📉 Fading" in md and "Hand-tuned PID" in md        # outlook fading
    assert "📈 Thriving" in md and "Learned end-to-end" in md  # outlook thriving
    assert md.startswith("---")                              # frontmatter
    assert "profile: lecture" in md
    assert "🧠 **ML Researcher**" in md and "`[00:12]`" in md     # lens + grounded cite
    assert "**Method** `[02:05]`" in md                       # chapter Outline timestamp
    assert "200-trial eval" in md                             # notable-claim basis
    assert "arxiv.org/abs/1707.06347" in md                   # description link harvested
    assert "*(from video description)*" in md
    assert "*Not applicable to this talk.*" in md             # empty open_questions degrades
    for banned in ["Funding landscape", "Paying Customers", "Chokepoints", "TRL"]:
        assert banned not in md                               # NO LSIC sections


def test_lecture_render_no_youtube_meta_omits_outline():
    md = lecture.render_lecture(ing=_ing(), alignment=_align(), pres_outputs=[],
                                thematic={"title": "X", "summary": "Y"}, slide_highlights=[],
                                evidence_by_id={}, event_date="2026-06-11", n_speakers=0,
                                source_meta=None)
    assert "## Outline" not in md                             # no chapters → no Outline
    assert "## Summary" in md and "## Through Expert Lenses" in md
    # forward-looking sections still render, degrading cleanly when empty
    assert "## Field Implications — Where to Steer" in md
    assert "## Industry Outlook — Fading vs Thriving" in md
    assert md.count("*Not applicable to this talk.*") >= 2     # incl. empty outlook


def test_lecture_render_dedupes_description_links():
    sm = {"description": "see https://a.com/p https://a.com/p. and https://b.com/q)"}
    md = lecture.render_lecture(ing=_ing(), alignment=_align(), pres_outputs=[],
                                thematic={}, slide_highlights=[], evidence_by_id={},
                                event_date="2026-06-11", n_speakers=0, source_meta=sm)
    assert md.count("https://a.com/p") == 1                   # dedup
    assert "https://b.com/q" in md and md.count("https://b.com/q)") == 0  # trailing ) stripped


# ---------- thematic prompt threading ----------

def test_call_thematic_uses_profile_system_prompt(monkeypatch):
    from src import synthesize
    captured = {}
    monkeypatch.setattr(synthesize, "_call_gemini_json",
                        lambda client, system, user, max_tokens=0: captured.update(system=system) or {})
    synthesize._call_thematic(None, _align(), [], [], [], system_prompt="LECTURE_MARKER_PROMPT")
    assert "LECTURE_MARKER_PROMPT" in captured["system"]
