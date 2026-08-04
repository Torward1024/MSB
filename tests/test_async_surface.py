"""The asynchronous surface, and the reason it is shaped the way it is.

The obvious way to make an orchestrator asynchronous is to make its entry point `async def`
and leave everything below it alone. That does nothing, and the first test here is the
measurement that says so: `await` does not create concurrency, it marks a point where control
*may* be yielded, and a synchronous handler has no such point. An event loop stays blocked for
the whole operation either way.

So the work leaves the loop instead. The synchronous API is untouched -- every signature is
what it was -- and an `a`-prefixed twin of each facade runs the same pipeline on an executor
the framework owns.

The tests use `asyncio.run` rather than an async test plugin, because the framework has no
dependencies and its test suite should not need one either.
"""
import asyncio
import time

import pytest

from msb_arch import (BaseEntity,
                      Manipulator,
                      RequestJournal,
                      RequestMetrics,
                      errors)


class Job(BaseEntity):
    size: int

    def crunch(self) -> int:
        return sum(index * index for index in range(self.size))

    def double(self) -> int:
        self.size *= 2
        return self.size

    async def fetch(self) -> str:
        await asyncio.sleep(0.01)
        return "fetched"

    def explode(self) -> None:
        raise RuntimeError("boom")


class Bench(Manipulator):
    pass


@pytest.fixture
def bench():
    orchestrator = Bench(base_classes=[Job])
    yield orchestrator
    orchestrator.close()


async def heartbeat_during(coroutine_or_call):
    """Run something and count how often the event loop got to do anything else."""
    stop = asyncio.Event()

    async def ticking():
        ticks = 0
        while not stop.is_set():
            ticks += 1
            await asyncio.sleep(0.001)
        return ticks

    counter = asyncio.create_task(ticking())
    outcome = coroutine_or_call()
    if asyncio.iscoroutine(outcome):
        outcome = await outcome
    stop.set()
    return outcome, await counter


# --- the point of the whole item ----------------------------------------------------------

def test_the_synchronous_call_blocks_the_loop_and_the_asynchronous_one_does_not(bench):
    """The measurement the design rests on. An `async def` entry point over a synchronous
    handler would score the same zero as the plain call: awaiting work that never suspends
    holds the loop exactly as long as doing it does."""
    job = Job(name="j", size=2_000_000)

    async def scenario():
        _, blocked = await heartbeat_during(lambda: bench.inspect(job, crunch=None))
        _, free = await heartbeat_during(lambda: bench.ainspect(job, crunch=None))
        return blocked, free

    blocked, free = asyncio.run(scenario())
    assert blocked == 0, "the synchronous call is supposed to block; the premise changed"
    assert free > 0, f"the loop ran {free} times during the asynchronous call"


# --- the surface --------------------------------------------------------------------------

def test_an_async_facade_returns_what_the_sync_one_returns(bench):
    job = Job(name="j", size=100)
    assert asyncio.run(bench.ainspect(job, crunch=None)) == bench.inspect(job, crunch=None)


def test_every_operation_gets_an_async_twin(bench):
    for operation in ("inspect", "configure"):
        assert hasattr(bench, operation)
        assert hasattr(bench, f"a{operation}")


def test_the_synchronous_api_is_untouched(bench):
    """Additive means additive: nothing about the old surface changed."""
    job = Job(name="j", size=10)
    assert bench.inspect(job, crunch=None) == 285
    bench.configure(job, double=None)
    assert job.size == 20


def test_aprocess_request_takes_the_same_request(bench):
    job = Job(name="j", size=10)
    response = asyncio.run(bench.aprocess_request(
        {"operation": "inspect", "obj": job, "attributes": {"crunch": None}}))
    assert response["status"] is True
    assert response["result"]["crunch"]["result"] == 285


def test_abatch_runs_a_batch(bench):
    job = Job(name="j", size=4)
    responses = asyncio.run(bench.abatch([
        {"operation": "configure", "obj": job, "attributes": {"double": None}},
        {"operation": "inspect", "obj": job, "attributes": {"crunch": None}},
    ]))
    assert len(responses) == 2
    assert job.size == 8


# --- methods that are themselves coroutines -----------------------------------------------

def test_an_async_method_on_an_entity_is_awaited(bench):
    """Applying it on a worker thread produces a coroutine; it is awaited back on the loop."""
    job = Job(name="j", size=1)
    assert asyncio.run(bench.ainspect(job, fetch=None)) == "fetched"


def test_an_async_method_is_awaited_inside_a_batch(bench):
    job = Job(name="j", size=1)
    responses = asyncio.run(bench.abatch([
        {"operation": "inspect", "obj": job, "attributes": {"fetch": None}},
    ]))
    assert responses["0"]["result"]["fetch"]["result"] == "fetched"


# --- failures behave the same -------------------------------------------------------------

def test_a_failure_raises_the_same_way(bench):
    job = Job(name="j", size=1)
    with pytest.raises(errors.HandlerError):
        asyncio.run(bench.aconfigure(job, explode=None))


def test_a_failure_can_be_reported_instead(bench):
    job = Job(name="j", size=1)
    response = asyncio.run(bench.aconfigure(job, explode=None, raise_on_error=False))
    assert response["status"] is False


# --- interceptors serve both paths --------------------------------------------------------

def test_one_interceptor_serves_both_paths_unchanged(bench):
    """The obligation B11 took on. It is met by running the whole pipeline off the loop,
    interceptors included, rather than by asking them to be written twice."""
    metrics, journal = RequestMetrics(), RequestJournal()
    bench.add_interceptor(metrics)
    bench.add_interceptor(journal)
    job = Job(name="j", size=10)

    bench.inspect(job, crunch=None)
    asyncio.run(bench.ainspect(job, crunch=None))

    assert metrics.snapshot()["inspect"]["calls"] == 2
    assert len(journal) == 2


def test_an_interceptor_can_still_refuse_on_the_async_path(bench):
    def deny(request, call_next):
        return {"status": False, "object": None, "method": None, "result": None,
                "error": "not allowed"}

    bench.add_interceptor(deny)
    job = Job(name="j", size=10)
    response = asyncio.run(bench.ainspect(job, crunch=None, raise_on_error=False))
    assert response["error"] == "not allowed"


# --- the executor -------------------------------------------------------------------------

def test_no_executor_exists_until_something_asynchronous_happens():
    """An application that never goes asynchronous never starts a thread."""
    orchestrator = Bench(base_classes=[Job])
    orchestrator.inspect(Job(name="j", size=10), crunch=None)
    assert orchestrator._executor is None
    orchestrator.close()


def test_close_shuts_the_executor_down(bench):
    asyncio.run(bench.ainspect(Job(name="j", size=10), crunch=None))
    assert bench._executor is not None
    bench.close()
    assert bench._executor is None


def test_close_is_safe_to_call_twice_and_when_nothing_started():
    orchestrator = Bench(base_classes=[Job])
    orchestrator.close()
    orchestrator.close()


def test_the_orchestrator_works_again_after_being_closed(bench):
    job = Job(name="j", size=10)
    asyncio.run(bench.ainspect(job, crunch=None))
    bench.close()
    assert asyncio.run(bench.ainspect(job, crunch=None)) == 285


def test_it_can_be_used_as_a_context_manager():
    job = Job(name="j", size=10)
    with Bench(base_classes=[Job]) as orchestrator:
        assert asyncio.run(orchestrator.ainspect(job, crunch=None)) == 285
        started = orchestrator._executor
    assert started is not None
    assert orchestrator._executor is None


def test_concurrent_requests_do_not_serialize_behind_one_another(bench):
    """Several awaited at once share the executor rather than queueing on the loop."""
    jobs = [Job(name=f"j{index}", size=400_000) for index in range(4)]

    async def scenario():
        started = time.perf_counter()
        await asyncio.gather(*(bench.ainspect(job, crunch=None) for job in jobs))
        return time.perf_counter() - started

    together = asyncio.run(scenario())
    started = time.perf_counter()
    for job in jobs:
        bench.inspect(job, crunch=None)
    sequential = time.perf_counter() - started

    assert together < sequential * 1.5, (
        f"four concurrent requests took {together:.2f}s against {sequential:.2f}s sequentially"
    )
