# Golden Additions — Cognitive-Core Extraction (the `lecture` profile spec)

> **What this is.** The spec for the cognition sections `src/profiles/lecture.py` adds to
> `notes.md`. The existing template extracts *what was said* (Summary, Key Points, Claims,
> Methods, References); this layer extracts **how the speaker thinks** — the repeatable mental
> operations behind the content. **Additive**: existing sections unchanged; each new section
> degrades to *Not applicable* (or is omitted) when its field is empty.
>
> The examples below illustrate **format only** and are speaker-agnostic. The real calibration
> target is the frozen baseline bundle in `golden/` — never bake any specific talk into the prompt.
>
> **Master question:** *What is this person doing mentally that an average person would not?*
> The most useful output of a talk is **a new question to ask yourself**, not a new quote.

---

## The frame — five lenses (why we extract what we extract)

| Lens | Question | Extract |
|------|----------|---------|
| **Perception** | What do they see? | The signal others dismissed; what they refuse to treat as normal. |
| **Decomposition** | How do they break it down? | The assumption destroyed; the *real* constraint vs the conventional one. |
| **Judgment** | How do they choose? | Decision rule under incomplete info; reversible vs irreversible; what they refuse to optimize. |
| **Adaptation** | How do they update? | What evidence changed their mind; failure read as information vs identity threat. |
| **Translation** | How do I test this? | The reusable self-question for the reader's own domain (→ section D). |

The output that matters is the **operating algorithm** (the procedure that generates their
conclusions, as a short arrow-chain), not the conclusions — and **tagged cognitive moves**, not topics.

---

## Move taxonomy — keyed by profile

Tag the **operation, not the topic** ("hiring"). Tag against the set matching `profile:` frontmatter.

- **Explainer** (lecture / research talk — *this profile*): `Analogy · Reframe · Mechanism ·
  Base-rate · Inversion · Sequencing · First-principles · Distinction`
- **Decision-maker** (founder / operator / investor): `Perception · Decomposition · Inversion ·
  Constraint · TimeHorizon · Tradeoff · Sequencing · Taste · Updating · Agency · Incentives ·
  Systems · Risk · Narrative · Energy`

Shared core: `Inversion · Sequencing · Decomposition/Mechanism`. The mismatch is itself signal:
a speaker who only ever runs explainer moves and never a decision move is **teaching, not
deciding**, and should be read that way.

---

## The four additions (the spec)

### A. Operating Algorithm  *(required — render after Summary)*

**Extraction instruction.** In one arrow-chain, compress the speaker's repeatable way of
reasoning about their domain — not their conclusions, the *procedure* that generates them. End
with the 2–4 dominant move-tags.

**Format** (speaker-agnostic):
> `<anchor / reference frame> → <expose where current practice falls short of it> → <re-anchor to base
> rates or hard constraints> → <the bet that follows>`
> *Tags: <2–4 from the explainer set>*

### B. Cognitive Moves  *(required — render after Through N Expert Lenses)*

**Extraction instruction.** 4–7 entries. For each: the move (short paraphrase or quote), the
move-tag, what the move *does* (the work it performs on the listener's model), and the timestamp.
Tag the operation, not the topic.

**Format** (4–7 entries, speaker-agnostic):
- **<move — short quote or paraphrase>** — *<Tag>* — <the work the move performs on the listener's model: what it swaps, collapses, maps, flips, or re-anchors> `[mm:ss]`

### C. Epistemic status  *(required — inline tag inside Notable Claims & Evidence + a closing line)*

**Extraction instruction.** Tag each claim `[consensus]`, `[his bet]`, `[contested]`, or
`[his frame]`, then add one closing line — *what doesn't transfer*. This is the **survivorship
guard**: you're hearing one unusually sharp person's strong priors, and the predictions are bets
even when the mechanisms are solid.

**Format** (inline status per claim, then one closing line):
- <claim> — <basis> `[<status>]` `[mm:ss]`
> **What doesn't transfer:** <which of the speaker's positions are bets/taste (hold loosely) vs durable
> mechanisms (the transferable part)>.

### D. Transfer Questions  *(required — render after Takeaways; needs a `reader_domain`)*

**Extraction instruction.** Convert the speaker's moves into reusable questions for the reader's
own domain. The only reader-specific section — requires a `reader_domain` input (env
`READER_DOMAIN`); emit an empty list (section omitted) when none is provided. With a current-work
context fed in, questions sharpen from domain-level to project-level.

**Format** *(reader_domain: `<e.g. embedded / robotics>`)*:
- <a cognitive move from §B> → *<a reusable question a practitioner in that domain should ask themselves>* `[mm:ss]`

---

## Size discipline

Two required sections (A, B), one inline tag + one closing line (C), one section needing a
`reader_domain` (D). Caps: algorithm = **one** arrow-chain line + tags; moves = **4–7**; transfer
questions = **3–5**. Everything is `[mm:ss]`-grounded like the rest of the template. The
*extraction guidance* (five lenses, taxonomy) lives here in the spec, **not** in rendered output.

## Deferred (not in scope here)

A cross-talk **situation index** (atoms re-keyed by their firing *trigger*, aggregated across
talks into a retrieval library) could later consume these atoms. Separate, utility-gated effort —
explicitly **out of scope** for this per-talk extraction. The atoms produced here are what it
would consume.
