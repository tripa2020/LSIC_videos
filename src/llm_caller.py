"""LLM Caller seam (Part 1, M-B2 core).

The single place the batch ON/OFF decision lives (R2). Stages build their fan-out as a list
of :class:`LLMRequest` and call ``caller.generate_many(requests)`` exactly once; *which*
caller ``main.py`` injects decides synchronous-vs-batch. A stage never branches on "batch?".

- :class:`SyncCaller` reproduces today's call (``client.models.generate_content``) one request
  at a time, in order — the degrade-to-today path.
- :class:`BatchCaller` buffers the whole fan-out into one Gemini batch job, blocks until the
  job reaches a terminal state, then resolves ``{custom_id: response}``. Failed ids are absent
  (R4) — the stage's manifest-gate + resume re-enqueues them next run.

Both return ``{custom_id: response}`` keyed by the stage-minted ``custom_id``; the stage owns
writing those responses into its own cache (R1). Fakes-only tested, no network.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from . import batch_gemini


@dataclass
class LLMRequest:
    """One stage call. Fields mirror ``generate_content``'s args so both callers forward
    them unchanged; ``custom_id`` is the stable handle the stage maps responses back by."""

    custom_id: str
    model: str
    contents: Any
    config: Any = None


class Caller(Protocol):
    def generate_many(self, requests: list[LLMRequest]) -> dict[str, Any]: ...


def prefill(caller: "Caller", requests: list[LLMRequest], write_one) -> int:
    """Bulk-fill a stage's per-item caches through one batch (the heart of batch-mode).

    Each ``LLMRequest.custom_id`` is the stage's cache key (e.g. the cache file path).
    ``write_one(custom_id, response)`` parses that response and writes ONE cache entry —
    the stage owns its cache format (R1). Failed ids are absent from the result, so they
    stay uncached and the stage's normal (sync) loop fills them on the same run (R4).
    Returns the number of caches written. The sync loop afterward simply hits cache, so a
    stage's existing code path is byte-identical whether or not prefill ran first."""
    if not requests:
        return 0
    responses = caller.generate_many(requests)
    written = 0
    for cid, resp in responses.items():
        write_one(cid, resp)
        written += 1
    return written


def _gen_kwargs(r: LLMRequest) -> dict:
    kwargs: dict[str, Any] = {"model": r.model, "contents": r.contents}
    if r.config is not None:
        kwargs["config"] = r.config
    return kwargs


class SyncCaller:
    """Today's behavior: call each request synchronously, in order. With this caller injected
    (the default), stages run their original code path byte-for-byte."""

    def __init__(self, client):
        self.client = client

    def generate_many(self, requests: list[LLMRequest]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for r in requests:
            out[r.custom_id] = self.client.models.generate_content(**_gen_kwargs(r))
        return out


class BatchCaller:
    """Buffer the fan-out into one Gemini batch job, block until terminal, resolve.

    ``poll_interval`` and the injected ``sleep`` keep the blocking loop testable without real
    time. ``inline_threshold`` is forwarded to the hybrid submit."""

    def __init__(self, client, *, poll_interval: float = 30.0, sleep=time.sleep,
                 inline_threshold: int = batch_gemini.INLINE_THRESHOLD):
        self.client = client
        self.poll_interval = poll_interval
        self._sleep = sleep
        self.inline_threshold = inline_threshold

    def generate_many(self, requests: list[LLMRequest]) -> dict[str, Any]:
        if not requests:
            return {}
        reqs = [batch_gemini.BatchRequest(r.custom_id, r.model, r.contents, r.config)
                for r in requests]
        job_name = batch_gemini.submit(self.client, reqs,
                                       inline_threshold=self.inline_threshold)
        while not batch_gemini.is_terminal(batch_gemini.poll(self.client, job_name)):
            self._sleep(self.poll_interval)
        return batch_gemini.resolve(self.client, job_name)
