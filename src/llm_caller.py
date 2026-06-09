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
