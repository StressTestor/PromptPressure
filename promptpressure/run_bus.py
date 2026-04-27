"""
RunBus: per-run event channel with completion replay and TTL reaping.

Replaces the original EVENT_QUEUES dict whose entries were popped on SSE
disconnect, breaking auto-reconnect and creating a memory leak when
EventSource never connected at all.

Lifecycle:
- start(run_id):                creates an entry, queue, last_active=now
- publish(run_id, event):       pushes event to queue, bumps last_active
- mark_completed(run_id, evt):  pushes the final event, flips completed=True
- subscribe(run_id):            async-iterates queue items; if completed at
                                subscribe-time, replays final event and exits
- reap_once() / reaper task:    deletes entries where (completed and idle > TTL)
                                or (any state and idle > idle_ttl)
"""
import asyncio
import logging
import time
from typing import Any, AsyncIterator, Dict, Optional


class RunBus:
    def __init__(
        self,
        completed_ttl: float = 300.0,   # 5 minutes
        idle_ttl: float = 1800.0,       # 30 minutes
        reap_interval: float = 60.0,
    ) -> None:
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._completed_ttl = completed_ttl
        self._idle_ttl = idle_ttl
        self._reap_interval = reap_interval
        self._reaper_task: Optional[asyncio.Task] = None

    def start(self, run_id: str) -> None:
        self._runs[run_id] = {
            "queue": asyncio.Queue(),
            "completed": False,
            "completion_event": None,
            "last_active": time.monotonic(),
        }

    def has(self, run_id: str) -> bool:
        return run_id in self._runs

    async def publish(self, run_id: str, event: Dict[str, Any]) -> None:
        entry = self._runs.get(run_id)
        if entry is None:
            return
        entry["last_active"] = time.monotonic()
        await entry["queue"].put(event)

    async def mark_completed(self, run_id: str, completion_event: Dict[str, Any]) -> None:
        entry = self._runs.get(run_id)
        if entry is None:
            return
        # Set completed=True before enqueue. Safe because asyncio.Queue() is unbounded —
        # put() doesn't yield, so no coroutine can observe completed=True with an empty
        # queue during the critical window. If maxsize is ever added, revisit this ordering.
        entry["completed"] = True
        entry["completion_event"] = completion_event
        entry["last_active"] = time.monotonic()
        await entry["queue"].put(completion_event)

    async def subscribe(self, run_id: str) -> AsyncIterator[Dict[str, Any]]:
        entry = self._runs.get(run_id)
        if entry is None:
            raise KeyError(run_id)

        # If already completed, replay the completion event and exit.
        # (Queue may have been drained by a previous subscriber.)
        if entry["completed"] and entry["queue"].empty():
            yield entry["completion_event"]
            return

        try:
            while True:
                item = await entry["queue"].get()
                entry["last_active"] = time.monotonic()
                if item is None:
                    return
                yield item
                if entry["completed"] and entry["queue"].empty():
                    return
        except asyncio.CancelledError:
            # Subscriber went away — DO NOT pop the entry. The reaper handles eviction.
            raise

    async def reap_once(self) -> None:
        now = time.monotonic()
        to_delete = []
        for run_id, entry in self._runs.items():
            idle = now - entry["last_active"]
            if entry["completed"] and idle > self._completed_ttl:
                to_delete.append(run_id)
            elif idle > self._idle_ttl:
                to_delete.append(run_id)
        for rid in to_delete:
            entry = self._runs.get(rid)
            if entry is not None:
                # Wake any blocked subscriber with the sentinel so subscribe() exits cleanly.
                await entry["queue"].put(None)
            logging.info("RunBus reaped run %s", rid)
            self._runs.pop(rid, None)

    async def _reaper_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._reap_interval)
                await self.reap_once()
        except asyncio.CancelledError:
            return

    async def start_reaper(self) -> None:
        if self._reaper_task is None:
            self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def stop_reaper(self) -> None:
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
            self._reaper_task = None
