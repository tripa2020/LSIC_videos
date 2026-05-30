<!--
  ⚠️ MOCKUP — illustrative content only.
  This file shows the SHAPE of the final notes.md output, not real extracted data.
  Numbers, claims, and timestamps are plausible-but-fabricated for design review.
  Used to approve output structure before any code is written.
-->

---
event_id: lsic_2026-03-26
date: 2026-03-26
title_inferred: "LSIC SP-CC Meeting — Lunar Dust & Dust-Tolerant Connectors"
duration: "1:02:34"
video_hash: 5a8c2d3e9f01
assets:
  - { kind: video,        file: "3105-GMT20260326-150218_Recording_2880x1800.mp4" }
  - { kind: host_deck,    file: "3106-20260326_SPCAslides.pptx" }
  - { kind: presentation, file: "3107-Amphenol Lunar Interconnects dealing with dust 03 12 2026 update.pdf" }
  - { kind: presentation, file: "3108-Nunez LSIC Lunar Dust Environment SP-CC Meeting March 2026.pptx" }
  - { kind: presentation, file: "3109-Yank Tech - Dust-Tolerant Connector LSIC.pdf" }
speakers_detected: 4
languages: [en]
generated: 2026-05-29
---

# LSIC SP-CC Meeting — Lunar Dust & Dust-Tolerant Connectors (2026-03-26)

## 🎯 Bottom Line for C'mander Alex
Three industry teams (Amphenol, Yank Tech, plus LSIC's own dust-environment researchers) converged on the same engineering problem: lunar connectors must survive sub-10 µm regolith abrasion across thousands of mate-demate cycles, and current MIL-DTL-38999 designs degrade unpredictably. Funding pull is from **NASA STMD Phase II SBIR**, with no single architecture emerging as a winner. The hard chokepoint is **test infrastructure** — fewer than five facilities worldwide can replicate the lunar dust environment at meaningful scale, and standards-development funding is currently falling between NIST and NASA.

### Through 5 Expert Lenses
*Roles selected from `clai/.claude/Behavior/Roles.md` based on event content.*

- 🔧 **Staff Mechatronics Systems Integrator** — Three competing connector architectures with no winner; integration cost depends on whichever lander interface freezes first. `[04:32 / 41:30]`
- 🧠 **Senior Embedded / Firmware Engineer** — None of the presentations addressed connector-status telemetry. Firmware health-monitoring of contact resistance over mission life is an unaddressed opportunity. `[15:48]`
- ✅ **Test / Reliability / Validation Engineer** — The single most actionable chokepoint is coupled thermal+dust test infrastructure. SBIR awards risk locking in flawed acceptance criteria before standards exist. `[19:30 / 29:41]`
- 📡 **Sensors / Instrumentation Engineer** — Dust environment characterization (kV electrostatic regime) directly threatens any sensor with exposed contacts. `[34:18]`
- 🏭 **Senior DFM / Manufacturing Engineer** — Au-flash plating is a manufacturability red flag at scale; cost-per-unit at >10k connector volumes is not addressed. `[15:48]`

## 🗂️ Contents
- 🎤 Presentations (3)
- 🔬 What's being done right now
- 🛠️ Engineering system-design questions
- ❓ Per-Question Role Analysis
- ⚠️ Main engineering constraints
- 💰 Funding landscape (orgs, mechanisms, scale)
- 🛒 Paying Customers / Demand
- 🚧 Chokepoints (research · development · funding · implementation)
- ⚙️ Technology Readiness & Maturity (TRL)
- 📐 Key equations & models
- 🗣️ Speakers
- 🔖 Citations & references mentioned
- 📎 Slide highlights

---

## 🎤 Presentations

### 1. Amphenol — Lunar Interconnects Dealing with Dust  `[04:32 → 22:18]`
*Source: `3107-Amphenol Lunar Interconnects... pdf` · 18 slides · Speaker B*

**TL;DR.** Amphenol's approach is a redesigned MIL-DTL-38999 derivative with a passive labyrinth seal and proprietary "dust-shedding" gold-flash plating on the pin array. They claim >2000 mate-demate cycles in simulated regolith at JSC-1A loading.

**Key claims**
- Existing MIL-DTL fails by pin-galling after ~200 cycles in lunar simulant `[07:14]`
- Their labyrinth seal architecture isolates the pin array without active power `[11:02]`
- Lab data: contact resistance increase <5 mΩ over 2000 cycles `[15:48]`

**Open questions raised**
- No data yet on thermal cycling concurrent with dust exposure `[19:30]`
- Plating durability beyond 5000 cycles is extrapolated, not measured `[20:55]`

---

### 2. Nunez (LSIC) — Lunar Dust Environment  `[22:40 → 41:12]`
*Source: `3108-Nunez LSIC Lunar Dust Environment... pptx` · 32 slides · Speaker C*

**TL;DR.** Survey of dust transport mechanisms (electrostatic levitation, plume-induced ballistic, mechanical abrasion). Argues current ground simulants under-represent the electrostatic regime; recommends new test standards before more SBIR awards lock in flawed acceptance criteria.

**Key claims**
- Apollo data shows dust adheres to anything within 10 m of surface activity `[25:02]`
- JSC-1A simulant lacks the ~50 nm submicron tail present in actual regolith `[29:41]`
- Electrostatic charging adds ~kV potentials to floating dust under UV `[34:18]`

**Open questions raised**
- Who funds the standards-development effort if it falls between NASA and NIST? `[38:55]`

---

### 3. Yank Tech — Dust-Tolerant Connector  `[41:30 → 58:02]`
*Source: `3109-Yank Tech - Dust-Tolerant Connector LSIC.pdf` · 14 slides · Speaker D*

**TL;DR.** Yank Tech proposes a hermetic blind-mate connector using a frangible cover that breaks on first engagement. Optimized for one-shot deployment (rover-to-lander umbilical, habitat-to-power-tower). Not suited to repeated mate-demate.

**Key claims**
- Single-mate architecture avoids ~80% of pin-galling failure modes `[44:20]`
- Hermetic cover protects pins from dust during transport + landing `[48:11]`
- Pass-through current rating to 100 A; verified on KC-135 parabolic `[53:02]`

**Open questions raised**
- What's the field-repair story if a single-mate connector fails post-deployment? `[56:14]`

---

## 🔬 What's being done right now
- Three parallel SBIR-funded efforts on dust-tolerant connectors `[04:32]`
- LSIC SP-CC focus group running the dust-environment standards effort `[22:40]`
- NASA STMD coordinating with the Artemis power architecture team `[54:30]`
- JPL building a 5 m³ dust-environment chamber; online Q4 2026 `[37:45]`

*Through Expert Lenses:*
- 🔧 *Staff Mechatronics Systems Integrator* — Three SBIR efforts mean three integration interfaces to track; a coordination layer between teams is the missing work-package.
- 🤖 *Staff Motion Planning Engineer* — Power-tower umbilical alignment under EVA-glove or robot-arm constraints is the manipulation problem riding shotgun with the connector spec.
- 🧰 *Mid-Level Robotics Integration Engineer* — JPL's chamber coming online Q4 2026 sets the integration-test cadence — schedule a slot before SBIR Phase II results land or you'll wait six months.

## 🛠️ Engineering system-design questions
- Mate-demate cycle count requirement is unsettled: 10? 200? 2000? Choice drives architecture `[11:50]`
- Hermetic-once vs. re-mateable is currently a binary trade — no hybrid presented `[44:20]`
- Thermal cycling and dust exposure must be coupled, not tested sequentially `[19:30]`
- Test standards lag the SBIR awards — bad acceptance criteria about to be locked in `[29:41]`

*Through Expert Lenses:*
- 🎛️ *Senior Controls Engineer* — Cycle-count and thermal-cycling spec gaps make plant identification impossible; control-law assumptions are unverifiable until the requirements settle.
- 🏭 *Senior DFM Engineer* — "No hybrid presented" likely means DFM constraints quietly kill the obvious hybrid (modular hermetic + re-mateable shield); worth surfacing as a constraint, not an oversight.
- ✅ *Test / Reliability / Validation Engineer* — Coupled thermal+dust is the missing test fixture; sequential testing will under-predict failure rates by an unknown factor.

## ❓ Per-Question Role Analysis

*Each engineering question above, viewed through 2–3 role lenses to surface where the real trade space lives.*

**1. Mate-demate cycle count requirement is unsettled (10? 200? 2000?)** `[11:50]`
- 🔧 *Staff Mechatronics Systems Integrator* — Cycle spec is the hidden interface that flips architecture between Amphenol (re-mateable) and Yank Tech (single-mate).
- ✅ *Test / Reliability / Validation Engineer* — Without a stated requirement the acceptance test cannot be defined; the standards-lag chokepoint cascades from here.
- 🧠 *Senior Embedded / Firmware Engineer* — Drives whether contact-resistance telemetry logs per-mate events or just mission-life trends.

**2. Hermetic-once vs. re-mateable is a binary trade — no hybrid presented** `[44:20]`
- 🏭 *Senior DFM Engineer* — A hybrid (one-shot hermetic plus removable dust shield) likely fails on cost-of-goods at scale; DFM may be the silent constraint, not engineering oversight.
- 🔧 *Staff Mechatronics Systems Integrator* — Hybrid changes the lander-side interface; the integrator owns the freeze decision and has the most to lose from late-binding architecture.
- 🤖 *Senior Manipulation / Motion Planning Engineer* — Re-mateable connectors need an EVA-glove or robot-arm engagement path planned upfront; hermetic doesn't.

**3. Thermal cycling and dust exposure must be coupled, not tested sequentially** `[19:30]`
- ✅ *Test / Reliability / Validation Engineer* — Sequential tests miss thermal-expansion-driven seal failure during dust ingress; a coupled rig is non-negotiable.
- 🎛️ *Senior Controls Engineer* — Seal stiffness changes with temperature; any controller commanding mate-force needs a thermal feed-forward term absent from every presenter's plant model.
- 📡 *Sensors / Instrumentation Engineer* — Coupled-stress instrumentation (strain + dust load + 4-wire contact-R) is the experimental design problem nobody has scoped yet.

**4. Test standards lag the SBIR awards — bad acceptance criteria about to be locked in** `[29:41]`
- ✅ *Test / Reliability / Validation Engineer* — First-mover writes the spec; whichever SBIR team publishes acceptance criteria first becomes the de facto standard.
- 🏭 *Senior DFM Engineer* — Premature spec lock-in may select a manufacturable architecture for the wrong reasons (e.g. what's cheap today without the dust environment fully characterized).
- 🔧 *Staff Mechatronics Systems Integrator* — Integration test cases get written from standards; if standards are wrong, integration acceptance is wrong all the way to flight.

## ⚠️ Main engineering constraints
- Lunar dust ~10 µm and below, charged to kV under UV `[34:18]`
- ±150 °C diurnal swing concurrent with dust exposure `[19:30]`
- Mass budget <250 g per connector for rover umbilicals `[50:08]`
- Vacuum + regolith abrasion accelerates all known failure modes `[07:14]`

## 💰 Funding landscape
| Org            | Mechanism                 | Scale            | Focus                       | Source    |
|----------------|---------------------------|------------------|-----------------------------|-----------|
| NASA STMD      | Phase II SBIR             | $X.X M committed | Dust-tolerant connectors    | `[05:20]` |
| NASA Artemis   | Architecture coordination | —                | Power-tower umbilicals      | `[54:30]` |
| JPL (internal) | Capital                   | ~$YY M           | 5 m³ dust chamber           | `[37:45]` |
| *(gap)*        | Standards development     | unfunded         | Falls between NIST and NASA | `[38:55]` |

*Through Expert Lenses:*
- 🏭 *Senior DFM Engineer* — SBIR Phase II at ~$X.X M funds prototype runs but not plating-cost qualification at production volumes; the real funding gap is between prototype and 10k-connector scale.
- ✅ *Test / Reliability / Validation Engineer* — JPL's chamber capital is the only line item that funds test infrastructure; standards-aligned acceptance testing has no funding home.
- 🔧 *Staff Mechatronics Systems Integrator* — Architecture-coordination role is implied by Artemis but unfunded as an explicit work-package — capture opportunity for a system integrator.

## 🛒 Paying Customers / Demand

NASA Artemis is the anchor demand signal but flows through SBIR awardees, not direct procurement. CLPS landers (Intuitive Machines, Firefly, Astrobotic) are the nearest-term BOM line item where a connector decision becomes a signed purchase order. DOD/Space Force and commercial habitat partners are scoping but not buying today, and the demand curve steepens sharply if Artemis cadence holds through 2028.

| Customer                                  | Procurement mechanism   | Status              | Spend horizon | Source       |
|-------------------------------------------|-------------------------|---------------------|---------------|--------------|
| NASA Artemis (anchor)                     | SBIR → integration BOM  | Active funding      | 2027–2030     | `[05:20]`    |
| CLPS landers (IM, Firefly, Astrobotic)    | Mission-by-mission BOM  | Active PO (implied) | 2026–2028     | inferred     |
| DOD / Space Force                         | RFI / pre-procurement   | Open RFI            | 2028+         | aspirational |
| Commercial habitats (Axiom, Sierra Space) | Pre-procurement scoping | Aspirational        | 2030+         | inferred     |

Status flags: `Active funding` · `Active PO` · `Open RFP/RFI` · `Aspirational`.

## 🚧 Chokepoints
| Stage          | Chokepoint                                    | Source    |
|----------------|-----------------------------------------------|-----------|
| Research       | Standards lag SBIR awards                     | `[29:41]` |
| Development    | <5 dust-environment test facilities worldwide | `[37:45]` |
| Funding        | Standards work falls between NIST and NASA    | `[38:55]` |
| Implementation | No field-repair story for hermetic connectors | `[56:14]` |

## ⚙️ Technology Readiness & Maturity (TRL)

NASA TRL scale 1–9. Confidence flag: *claimed* (presenter assertion) vs *inferred* (extrapolated from data shown).

| Technology                     | TRL          | Basis                                       | Confidence | Source    |
|--------------------------------|--------------|---------------------------------------------|------------|-----------|
| Amphenol labyrinth connector   | 4-5          | Lab data, JSC-1A, ambient atmosphere        | inferred   | `[15:48]` |
| Yank Tech hermetic frangible   | 3-4          | KC-135 parabolic, current pass-through only | inferred   | `[53:02]` |
| Nunez dust-standards framework | 2            | Position paper, no rig                      | claimed    | `[22:40]` |
| JPL 5 m³ dust chamber          | 6 (facility) | Under construction                          | claimed    | `[37:45]` |

**Gap to flight.** Connectors need TRL 6 (relevant environment) at minimum for any Artemis manifest. Both hardware approaches are 2–3 TRL steps from that bar.

## 📐 Key equations & models
*No equations identified — this event was primarily qualitative engineering presentations. Section retained for template consistency; will populate when a future event has math on slides.*

## 🗣️ Speakers
- **A** — Host, LSIC SP-CC focus group lead `[00:00 → 04:30]`
- **B** — Amphenol presenter `[04:32 → 22:18]`
- **C** — Nunez (LSIC dust environment) `[22:40 → 41:12]`
- **D** — Yank Tech presenter `[41:30 → 58:02]`

## 🔖 Citations & references mentioned
- *JSC-1A* — NASA standard regolith simulant `[29:41]`
- *MIL-DTL-38999* — connector spec `[07:14]`
- Apollo dust transport data (referenced, not specifically cited) `[25:02]`
- Yank Tech KC-135 parabolic flight test results, internal `[53:02]`

## 📎 Slide highlights
![Amphenol labyrinth seal cross-section](keyframes/event_2026-03-26/3107_amphenol_p11.jpg)
*Cross-section of the proposed labyrinth seal isolating pin array.* `[11:02]`

![Nunez dust transport diagram](keyframes/event_2026-03-26/3108_nunez_p17.jpg)
*Electrostatic levitation diagram showing kV charging under UV.* `[34:18]`

![Yank Tech hermetic connector cutaway](keyframes/event_2026-03-26/3109_yank_p06.jpg)
*Frangible-cover hermetic connector cutaway.* `[48:11]`

---

*Generated by LSIC briefing pipeline. Source files in `LSIC_Downloads/`; artifacts in `work/lsic_2026-03-26/`.*
