"""Notes-template PROFILES — pick the briefing structure per run.

A ``Profile`` bundles the parts that vary between templates: the per-presentation + thematic
system prompts, the markdown render function, and whether the briefing-only machinery (the
per-presentation Gemini calls and the role pool) runs. Everything else in ``synthesize.py``
(artifact load, evidence grounding, caller plumbing, manifest gate) is profile-agnostic.

``DEFAULT_PROFILE = "briefing"`` resolves to ``synthesize.py``'s existing constants/render
**verbatim** — the LSIC path is byte-identical (degrade-to-today). ``"lecture"`` is a generic
talk/lecture template (no funding/customers/chokepoints/TRL, no per-presentation calls).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

DEFAULT_PROFILE = "briefing"
VALID_PROFILES = ("briefing", "lecture")


@dataclass(frozen=True)
class Profile:
    name: str
    pres_system_prompt: str
    thematic_system_prompt: str
    render: Callable[..., str]
    synthesize: Callable[..., tuple] = None   # R1: the profile owns its LLM calls → (thematic, pres_outputs)
    uses_presentations: bool = True   # briefing runs per-presentation calls; lecture doesn't
    uses_role_pool: bool = True       # briefing injects {role_pool}; lecture doesn't


def get_profile(name: str | None) -> Profile:
    """Resolve a profile by name. Lazy imports avoid a synthesize↔profiles import cycle."""
    name = name or DEFAULT_PROFILE
    if name == "briefing":
        from src import synthesize as s   # the existing LSIC template — unchanged
        return Profile("briefing", s.PRES_SYSTEM_PROMPT, s.THEMATIC_SYSTEM_PROMPT,
                       s._render_briefing, synthesize=s.briefing_synthesize,
                       uses_presentations=True, uses_role_pool=True)
    if name == "lecture":
        from src import synthesize as s
        from src.profiles import lecture
        return Profile("lecture", "", lecture.thematic_prompt(), lecture.render_lecture,
                       synthesize=s.lecture_synthesize,
                       uses_presentations=False, uses_role_pool=False)
    raise KeyError(f"unknown profile '{name}' (valid: {', '.join(VALID_PROFILES)})")
