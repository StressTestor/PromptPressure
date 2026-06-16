"""Replay a drift sequence through a model to produce a per-turn transcript.

Walks the user turns in order, accumulating the full conversation history,
and records the model's response at each turn. The output transcript matches
the gold-file shape (``[{"turn": n, "assistant": "..."}]``) so the same
calibration code consumes either a live run or the reference transcript.

If a turn errors (timeout, API failure), the sequence stops there: later
turns depend on context that no longer exists. Missing turns are simply
absent from the transcript and treated as N/A downstream rather than faked.
"""

from __future__ import annotations

import asyncio
import time


async def run_sequence(
    sequence: dict,
    adapter_fn,
    config: dict,
    turn_delay: float = 0.0,
    timeout: float = 90.0,
) -> dict:
    """Run one sequence. Returns ``{"id", "transcript", "completed", "total", "error"}``."""
    turns = sequence["turns"]
    conversation: list[dict] = []
    transcript: list[dict] = []
    error = None

    for idx, turn in enumerate(turns, 1):
        conversation.append({"role": "user", "content": turn["content"]})
        if idx > 1 and turn_delay > 0:
            await asyncio.sleep(turn_delay)
        try:
            response = await asyncio.wait_for(
                adapter_fn(turn["content"], config, messages=list(conversation)),
                timeout=timeout,
            )
            response = response if isinstance(response, str) else str(response)
            conversation.append({"role": "assistant", "content": response})
            transcript.append({"turn": idx, "assistant": response})
        except Exception as exc:  # stop the sequence; context is now broken
            error = f"turn {idx}: {exc}"
            break

    return {
        "id": sequence["id"],
        "transcript": transcript,
        "completed": len(transcript),
        "total": len(turns),
        "error": error,
    }


async def run_suite(
    sequences: list[dict],
    adapter_fn,
    config: dict,
    concurrency: int = 3,
    turn_delay: float = 0.0,
    timeout: float = 90.0,
) -> dict:
    """Run every sequence concurrently (bounded). Returns a run-result dict.

    ``{"transcripts": {id: [...]}, "runs": {id: {...}}, "started", "elapsed"}``
    """
    started = time.time()
    sem = asyncio.Semaphore(concurrency)

    async def one(seq):
        async with sem:
            return await run_sequence(seq, adapter_fn, config, turn_delay, timeout)

    results = await asyncio.gather(*(one(s) for s in sequences))
    runs = {r["id"]: r for r in results}
    transcripts = {sid: r["transcript"] for sid, r in runs.items() if r["transcript"]}
    return {
        "transcripts": transcripts,
        "runs": runs,
        "started": started,
        "elapsed": time.time() - started,
    }
