# EASYRUN — Design Rationale (frozen provenance)

> Original record of the decision-making process, captured at planning time. May have drifted
> from the current code — NOT authoritative. See the durable PLAN for current truth.

## 1. Decisions record (choice + rationale)

| # | Decision | Choice | Why |
|---|----------|--------|-----|
| D1 | Standalone vs extend | **Extend in place** (adapter pattern) | Exploration showed the 7-stage core is already source-agnostic; yt-dlp acquisition is already generic; LSIC coupling is isolated to the input layer. A standalone tool would duplicate the ingest→synth→report machinery. |
| D2 | Notes template generality | **Selectable `Profile`s** | The existing 15-section template is LSIC-telecon-specific (funding/customers/chokepoints/TRL). Default `briefing` reuses the unchanged code (byte-identical); `lecture` is a new generic template. |
| D3 | Generic template count | **One** generic template (not per-type variants, not toggles) | Simplicity; one thing to maintain and tune. |
| D4 | Expert Lenses | **Keep** "Through N Expert Lenses", domain-adapted | It's the briefing's most distinctive feature and is domain-general — the model self-selects perspectives fitting each video. |
| D5 | YouTube metadata | **Mine chapters + description links** | yt-dlp already returns them for free; chapters → Outline timeline, description URLs → References. |
| D6 | Forward-looking depth | Add **Field Implications** + **Industry Outlook** | User wants the strategic/career signal — what to transition to / skills to gain, and what's fading vs thriving — extracted even when only implied. |
| D7 | Citation source | **Dedicated search API**, arXiv-first behind a `SearchClient` seam | User chose a dedicated API over Gemini grounding for precise paper lookup; arXiv needs no key, matches the engineering domain; S2 drops in behind the same seam. |
| D8 | Enrich scope | **Opt-in** for LSIC pipeline (`--references`), **on** for `--source` | Keeps the LSIC 122-batch byte-identical; references are the point for new sources. |
| D9 | Execution | **Local by default**, `--remote` offloads | One-off YouTube clips are small and the laptop already has the deps; the VM earns its keep on heavy/long jobs and the 122-batch. |
| D10 | VM lifecycle | **Reuse the persistent standard VM**, start→run→**auto-stop** | Fast (~30s boot), disk/venv/.env persist, no preemption; auto-stop in a `finally` for cost safety. |

## 2. Q&A record (the IDEATION chat)

1. **Standalone or extend here?** → *Extend here (adapter pattern).*
2. **notes.md template for generic videos?** → *Selectable templates/profiles.*
3. **Invocation/output?** → *CLI for ad-hoc YouTube; job files (`run_corpus.sh`) for LSIC batches.*
4. **Websearch approach?** → *Dedicated search API.*
5. **Where do ad-hoc jobs run?** → *Local by default, `--remote` to offload.*
6. **On-demand VM lifecycle?** → *Reuse the persistent VM: start→run→auto-stop.*
7. **Generic template — how many?** → *One generic 'talk' template.*
8. **Keep the multi-perspective Expert Lenses?** → *Yes — keep for all videos.*
9. **Use YouTube native metadata?** → *Yes — chapters + description links.*
10. **(freeform)** Add *field implications* (skills/transitions practitioners should pursue) and
    *industry outlook* (what's dying vs thriving), per the speakers — even when only implied.

## 3. System-design hierarchy

```
EASYRUN
├── Input layer (adapters → events.json)
│   └── adhoc: URL/file → Event (+ yt-dlp metadata: chapters, description)        [M1]
├── Core (unchanged 7 stages; source-agnostic)
│   ├── synthesize + Profile selector                                            [M2]
│   │   ├── briefing  → unchanged LSIC render (byte-identical)
│   │   └── lecture   → Summary · Expert Lenses · Outline · Key Points · Methods ·
│   │                   Notable Claims · Open Questions · Takeaways ·
│   │                   Field Implications · Industry Outlook · Speakers · References  [M2/M2.1]
│   └── enrich_citations (new stage) → references.md via SearchClient(arXiv)      [M3]
├── Output: report.assemble_report(dest_dir=--out)                               [M1]
└── Execution: local (default) | remote.remote_run (gcloud lifecycle)            [M4]
```

## 4. Trade-off analysis

- **Adapter vs standalone (D1):** adapter = zero duplication, one codebase, but couples EASYRUN's
  release cadence to the LSIC repo. Accepted — the shared core is exactly what we want to reuse.
- **Briefing relocation (D2):** the Plan agent proposed moving the big prompts into `profiles/`.
  We chose to **reference the unchanged symbols** instead — lower risk, guarantees byte-identical
  default, at the cost of `profiles/__init__` importing `synthesize` lazily.
- **Deterministic vs LLM query derivation (D7):** deterministic extraction from `thematic.json`
  avoids an extra LLM call, is fully testable offline, and is robust — at the cost of less query
  refinement than an LLM would give. Acceptable; an LLM refiner can slot in later.
- **arXiv-only vs arXiv+S2 (D7):** arXiv-only ships now (no key, robust); S2 adds DOIs/venues but
  has rate limits without a key. The `SearchClient` Protocol makes S2 a pure addition.
- **Opt-in enrichment (D8):** protects the 122-batch from added latency/artifacts and keeps it
  byte-identical, at the cost of LSIC users needing `--references` to get papers.
- **Foreground ssh vs tmux remote (D9/OQ3):** foreground is simpler and testable; it ties the
  laptop to the job's lifetime and dies on disconnect. tmux-detached is the durability upgrade.

## 5. LLM instructions used to generate this

> After the IDEATION Q&A closed (§2), produce the durable `EASYRUN_PLAN.md` (milestones M1–M4
> with binary unit-test gates, LOC budgets, build order, degrade-to-today contract) and this
> frozen rationale. Ground every milestone in real seams (`Event`/`events.json`,
> `report.assemble_report`, the `Caller`/`util.retry_transient` helpers, the synthesize prompt
> constants). Extend in place; never disturb the LSIC catalog/batch path.
