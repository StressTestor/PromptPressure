import asyncio
import time
import pytest

from promptpressure.run_bus import RunBus


@pytest.mark.asyncio
async def test_publish_and_subscribe_basic():
    bus = RunBus()
    bus.start("run1")
    await bus.publish("run1", {"event": "progress", "data": "1/10"})
    await bus.publish("run1", {"event": "progress", "data": "2/10"})

    received = []
    async def consumer():
        async for item in bus.subscribe("run1"):
            received.append(item)
            if item.get("event") == "complete":
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)
    await bus.mark_completed("run1", {"event": "complete", "data": "done"})
    await asyncio.wait_for(task, timeout=1.0)

    assert [r["data"] for r in received] == ["1/10", "2/10", "done"]


@pytest.mark.asyncio
async def test_subscribe_after_completion_replays_summary():
    bus = RunBus()
    bus.start("run2")
    await bus.publish("run2", {"event": "progress", "data": "1/1"})
    await bus.mark_completed("run2", {"event": "complete", "data": "summary"})

    received = []
    async def consumer():
        async for item in bus.subscribe("run2"):
            received.append(item)
            if item.get("event") == "complete":
                break
    await asyncio.wait_for(consumer(), timeout=1.0)

    assert any(r.get("event") == "complete" and r.get("data") == "summary" for r in received)


@pytest.mark.asyncio
async def test_disconnect_does_not_pop_entry():
    bus = RunBus()
    bus.start("run3")
    await bus.publish("run3", {"event": "progress", "data": "x"})

    async def early_disconnect():
        async for item in bus.subscribe("run3"):
            return  # Drop after first item
    await early_disconnect()

    # Entry must still exist, queue still alive for reconnect
    assert "run3" in bus._runs


@pytest.mark.asyncio
async def test_reap_evicts_completed_after_ttl():
    bus = RunBus(completed_ttl=0.05, idle_ttl=10.0, reap_interval=0.02)
    bus.start("run4")
    await bus.mark_completed("run4", {"event": "complete", "data": "done"})

    bus._runs["run4"]["last_active"] = time.monotonic() - 1.0  # Force expiration

    await bus.reap_once()
    assert "run4" not in bus._runs


@pytest.mark.asyncio
async def test_reap_evicts_idle_runs():
    bus = RunBus(completed_ttl=300.0, idle_ttl=0.05, reap_interval=0.02)
    bus.start("run5")
    bus._runs["run5"]["last_active"] = time.monotonic() - 1.0  # Force idle expiration

    await bus.reap_once()
    assert "run5" not in bus._runs


@pytest.mark.asyncio
async def test_subscribe_unknown_run_raises():
    bus = RunBus()
    with pytest.raises(KeyError):
        async for _ in bus.subscribe("nope"):
            break


@pytest.mark.asyncio
async def test_reaper_lifecycle():
    bus = RunBus(reap_interval=0.02)
    await bus.start_reaper()
    assert bus._reaper_task is not None
    await bus.stop_reaper()
    assert bus._reaper_task is None


@pytest.mark.asyncio
async def test_subscribe_after_drain_replays_completion():
    bus = RunBus()
    bus.start("run_replay")
    await bus.mark_completed("run_replay", {"event": "complete", "data": "summary"})
    # First subscriber drains the queue
    async for _ in bus.subscribe("run_replay"):
        pass
    # Second subscriber should hit the replay branch and get exactly the completion event
    received = [e async for e in bus.subscribe("run_replay")]
    assert received == [{"event": "complete", "data": "summary"}]
