"""Stage 1: per-asset ingest dispatch (video → wav; pptx/pdf → handlers). Lands in M1."""


def ingest_event(*args, **kwargs):
    raise NotImplementedError("ingest_event lands in M1 — see PLAN.md")
