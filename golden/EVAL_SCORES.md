# EVAL Retro-Scores — golden bundles for `lXUZvyajciY` (Karpathy, 146 min)

Generated 2026-07-04 by `python -m src.synth_eval golden/lXUZvyajciY_*` (notes-only mode —
frozen bundles carry no `thematic.json`/`evidence.json`; in-pipeline runs additionally get
quote verification, evidence resolution, and the cross-window ratio).

| bundle       | moves | final-third cites | founder plays | retrieval Qs | decile cov | bullet cite rate | cites | status clean | gates |
|--------------|-------|-------------------|---------------|--------------|------------|------------------|-------|--------------|-------|
| baseline     | 0     | 0                 | 0             | 0            | 0.9        | 0.80             | 56    | yes          | 1/5   |
| augmented    | 6     | 0                 | 0             | 0            | 0.9        | 0.88             | 68    | yes          | 1/5   |
| v2_gemini    | 6     | 0                 | 0             | 0            | 0.9        | 0.88             | 66    | yes          | 1/5   |
| v2_opus      | 7     | 0                 | 0             | 0            | 0.9        | 0.88             | 69    | yes          | 1/5   |
| v3_mapreduce | 7     | 0                 | 0             | 0            | 1.0        | 0.86             | 67    | yes          | 1/5   |
| v4_depth3    | 13    | 2                 | 5             | 8            | 1.0        | 0.75             | 94    | yes          | 5/5   |

Reading: `v4_depth3` is the only generation passing all five v3 gates — the DEPTH v3 lift is
now a measured fact, not an eyeball. Decile coverage jumps to 1.0 exactly where map-reduce
(v3) and the uncapped cognition context (v4) land. The v4 bullet-cite-rate dip to 0.75 is by
design: Founder Lens action/learn/deeper bullets are generative (the model's own market
reasoning), not transcript-cited.

These gate columns are the regression floor for every future prompt/model change: a run that
scores below `v4_depth3` on any gate is a regression, visible before anyone reads the notes.
