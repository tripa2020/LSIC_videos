"""Stage 5 thin (M2.5 steel thread): single Claude call → notes.md.

Full per-section + Evidence-grounded version lands at M5. This module proves
the seam from transcript → notes.md without the production complexity.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from src.contracts import Segment


CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_OUTPUT_TOKENS = 8000
TRANSCRIPT_INPUT_CAP_CHARS = 80_000   # safety cap; full M5 chunks per-section

SYSTEM_PROMPT = """You write technical engineering briefings from meeting transcripts for C'mander Alex.

You receive a transcript JSON array. Each segment has start/end (seconds),
text, speaker_id (A/B/C…), language (ISO 639-1).

Produce ONLY a `notes.md` file with the 15-section canonical structure below.
Every populated section must carry at least one `[mm:ss]` citation that maps
to a transcript timestamp. Sections without evidence must still appear with
an italic line: `*Not applicable to this clip — <one-line reason>.*`

CANONICAL STRUCTURE (this exact order, exact emojis, exact section names):

```
---
event_id: ...
date: ...
title_inferred: "..."
duration: "mm:ss"
speakers_detected: N
languages: [..]
generated: YYYY-MM-DD
---

# <Inferred Title>

## 🎯 Bottom Line for C'mander Alex
<Exactly 3 sentences framing: current state · engineering constraints · funding/chokepoints.>

### Through 5 Expert Lenses
*Roles selected from `clai/.claude/Behavior/Roles.md` based on event content.*

- 🔧 **<Role A>** — <one-sentence take> `[mm:ss]`
- 🧠 **<Role B>** — <take> `[mm:ss]`
- ✅ **<Role C>** — <take> `[mm:ss]`
- 📡 **<Role D>** — <take> `[mm:ss]`
- 🏭 **<Role E>** — <take> `[mm:ss]`

## 🗂️ Contents
- 🎤 Presentations (N)
- 🔬 What's being done right now
- 🛠️ Engineering system-design questions
- ❓ Per-Question Role Analysis
- ⚠️ Main engineering constraints
- 💰 Funding landscape
- 🛒 Paying Customers / Demand
- 🚧 Chokepoints
- ⚙️ Technology Readiness & Maturity (TRL)
- 📐 Key equations & models
- 🗣️ Speakers
- 🔖 Citations & references mentioned
- 📎 Slide highlights

## 🎤 Presentations
<one ### sub-block per presentation; stub if none in clip>

## 🔬 What's being done right now
- bullet `[mm:ss]`

## 🛠️ Engineering system-design questions
- bullet `[mm:ss]`

## ❓ Per-Question Role Analysis
**1. <question>** `[mm:ss]`
- 🔧 *Role* — take
- ✅ *Role* — take

## ⚠️ Main engineering constraints
- bullet `[mm:ss]`

## 💰 Funding landscape
| Org | Mechanism | Scale | Focus | Source |
|-----|-----------|-------|-------|--------|
| ... | ... | ... | ... | `[mm:ss]` |

## 🛒 Paying Customers / Demand
<2-3 sentence prose intro>

| Customer | Procurement mechanism | Status | Spend horizon | Source |
|----------|-----------------------|--------|---------------|--------|
| ... | ... | Active funding | ... | ... |

## 🚧 Chokepoints
| Stage | Chokepoint | Source |
|-------|------------|--------|
| Research | ... | `[mm:ss]` |
| Development | ... | `[mm:ss]` |
| Funding | ... | `[mm:ss]` |
| Implementation | ... | `[mm:ss]` |

## ⚙️ Technology Readiness & Maturity (TRL)
| Technology | TRL | Basis | Confidence | Source |
|------------|-----|-------|------------|--------|
| ... | ... | ... | inferred | `[mm:ss]` |

## 📐 Key equations & models
*Not applicable to this clip — no equations identified.*

## 🗣️ Speakers
- **A** — <role/identity if known> `[start → end]`

## 🔖 Citations & references mentioned
- *<thing cited>* `[mm:ss]`

## 📎 Slide highlights
*Not applicable to this clip — no visual frames sampled in steel-thread mode.*
```

TABLE RULE: pad columns with spaces so every `|` lines up across rows.
Use `*Not applicable to this clip — <reason>.*` for any section that lacks
evidence in the transcript.

OUTPUT: ONLY the notes.md content. No prose, no markdown code fences, no
preamble.
"""

USER_PROMPT_TEMPLATE = """\
Transcript ({n_segments} segments, duration {duration:.0f}s):

```json
{transcript}
```

Event metadata:
- event_id: {event_id}
- date: {date}
- duration: {duration_mmss}
- speakers_detected: {speaker_count}
- languages: {languages}

Generate the notes.md per the canonical structure.
"""


def synthesize_thin(
    event_id: str,
    transcript_path: Path,
    duration_sec: float,
    output_path: Path,
    event_date: str,
) -> Path:
    """Single-call Claude synthesis. Writes notes.md and returns its path."""
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

    segs_raw = json.loads(transcript_path.read_text())
    segs = [Segment.model_validate(s) for s in segs_raw]
    speakers = sorted({s.speaker_id for s in segs if s.speaker_id})
    languages = sorted({s.language for s in segs if s.language})

    duration_mmss = f"{int(duration_sec // 60):02d}:{int(duration_sec % 60):02d}"

    transcript_blob = json.dumps(segs_raw, indent=1)[:TRANSCRIPT_INPUT_CAP_CHARS]
    user_prompt = USER_PROMPT_TEMPLATE.format(
        n_segments=len(segs),
        duration=duration_sec,
        transcript=transcript_blob,
        event_id=event_id,
        date=event_date,
        duration_mmss=duration_mmss,
        speaker_count=len(speakers),
        languages=",".join(languages) or "en",
    )

    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    notes_text = msg.content[0].text.strip()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(notes_text)
    return output_path


# --- M5 stubs (full per-section + Evidence-grounded) ---

def synthesize(*args, **kwargs):
    raise NotImplementedError("synthesize (full M5) lands later — see PLAN.md")


def synthesize_paper(*args, **kwargs):
    raise NotImplementedError("synthesize_paper lands at M5b — see PLAN.md")
