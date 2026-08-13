"""The one hook that metrics, auditing, rate limiting and authorisation all turn out to be.

Four things were asked for separately. None of them belongs in a framework with no
dependencies -- a library that picks a metrics backend stops being dependency-free, and one
that picks an authorisation model is wrong about somebody's. What they have in common is the
moment: each wants to see a request before it runs and its response after. So the framework
provides that moment and none of the four, and ships two implementations because they are the
ones everybody writes.
"""
import pytest

from msb_arch import (BaseEntity,
                      Inspector,
                      Manipulator,
                      RequestJournal,
                      RequestMetrics,
                      errors)


class Widget(BaseEntity):
    diameter: float

    def get_diameter(self) -> float:
        return self.diameter

    def set_diameter(self, value: float) -> bool:
        self.diameter = value
        return True

    def explode(self) -> None:
        raise RuntimeError("boom")


class Observatory(Manipulator):
    pass


@pytest.fixture
def bench():
    return Observatory(base_classes=[Widget])


@pytest.fixture
def dish():
    return Widget(name="DSS14", diameter=70.0)


# --- the chain ----------------------------------------------------------------------------

def test_an_interceptor_sees_the_request_and_the_response(bench, dish):
    seen = {}

    def watcher(request, call_next):
        seen["operation"] = request["operation"]
        response = call_next(request)
        seen["status"] = response["status"]
        return response

    bench.add_interceptor(watcher)
    bench.inspect(dish, get_diameter=None)
    assert seen == {"operation": "inspect", "status": True}


def test_an_interceptor_can_refuse_without_running_the_request(bench, dish):
    """What rate limiting and authorisation need: a decision made before anything happens."""
    def deny(request, call_next):
        return {"status": False, "object": None, "method": None, "result": None,
                "error": "not allowed"}

    bench.add_interceptor(deny)
    response = bench.configure(dish, set_diameter=1.0, raise_on_error=False)
    assert response["status"] is False
    assert dish.diameter == 70.0            # the request never ran


def test_an_interceptor_can_rewrite_the_request(bench, dish):
    """The seam a pipeline would later use to substitute one step's result into the next."""
    def double(request, call_next):
        request["attributes"]["set_diameter"] *= 2
        return call_next(request)

    bench.add_interceptor(double)
    bench.configure(dish, set_diameter=30.0)
    assert dish.diameter == 60.0


def test_the_first_added_is_the_outermost(bench, dish):
    order = []

    def outer(request, call_next):
        order.append("outer in")
        response = call_next(request)
        order.append("outer out")
        return response

    def inner(request, call_next):
        order.append("inner in")
        response = call_next(request)
        order.append("inner out")
        return response

    bench.add_interceptor(outer)
    bench.add_interceptor(inner)
    bench.inspect(dish, get_diameter=None)
    assert order == ["outer in", "inner in", "inner out", "outer out"]


def test_each_entry_of_a_batch_is_intercepted_separately(bench, dish):
    """A batch is a container of requests, not a request: ten entries mean ten interceptions."""
    counted = []

    def count(request, call_next):
        counted.append(request["operation"])
        return call_next(request)

    bench.add_interceptor(count)
    bench.batch([
        {"operation": "configure", "obj": dish, "attributes": {"set_diameter": 10.0}},
        {"operation": "inspect", "obj": dish, "attributes": {"get_diameter": None}},
    ])
    assert counted == ["configure", "inspect"]


def test_an_interceptor_can_be_removed(bench, dish):
    def watcher(request, call_next):
        raise AssertionError("should not run once removed")

    bench.add_interceptor(watcher)
    bench.remove_interceptor(watcher)
    assert bench.get_interceptors() == []
    bench.inspect(dish, get_diameter=None)


def test_removing_one_that_was_never_added_says_so(bench):
    with pytest.raises(errors.NotFoundError):
        bench.remove_interceptor(lambda request, call_next: None)


def test_something_that_is_not_callable_is_refused(bench):
    with pytest.raises(errors.RegistrationError, match="callable"):
        bench.add_interceptor("not a function")


def test_an_orchestrator_without_interceptors_is_unaffected(bench, dish):
    """The default must cost nothing, so the fast path skips the chain entirely."""
    assert bench.get_interceptors() == []
    assert bench.inspect(dish, get_diameter=None) == 70.0


# --- metrics (P8) -------------------------------------------------------------------------

def test_metrics_count_and_time_each_operation(bench, dish):
    metrics = RequestMetrics()
    bench.add_interceptor(metrics)

    bench.inspect(dish, get_diameter=None)
    bench.inspect(dish, get_diameter=None)
    bench.configure(dish, set_diameter=1.0)

    snapshot = metrics.snapshot()
    assert snapshot["inspect"]["calls"] == 2
    assert snapshot["configure"]["calls"] == 1
    assert snapshot["inspect"]["failures"] == 0
    assert snapshot["inspect"]["mean_seconds"] > 0


def test_metrics_count_a_failure_as_a_call_and_a_failure(bench, dish):
    """How long failures take is usually the interesting part, so they are timed too."""
    metrics = RequestMetrics()
    bench.add_interceptor(metrics)

    bench.configure(dish, explode=None, raise_on_error=False)
    snapshot = metrics.snapshot()
    assert snapshot["configure"]["calls"] == 1
    assert snapshot["configure"]["failures"] == 1
    assert snapshot["configure"]["total_seconds"] > 0


def test_metrics_can_be_reset(bench, dish):
    metrics = RequestMetrics()
    bench.add_interceptor(metrics)
    bench.inspect(dish, get_diameter=None)
    metrics.reset()
    assert metrics.snapshot() == {}


# --- the journal (P12) --------------------------------------------------------------------

def test_the_journal_records_what_ran(bench, dish):
    journal = RequestJournal()
    bench.add_interceptor(journal)

    bench.configure(dish, set_diameter=64.0)
    bench.inspect(dish, get_diameter=None)

    assert len(journal) == 2
    assert journal[0]["operation"] == "configure"
    assert journal[0]["object"] == "DSS14"
    assert journal[0]["attributes"] == {"set_diameter": 64.0}
    assert journal[0]["status"] is True
    assert journal[1]["operation"] == "inspect"


def test_a_result_can_be_traced_back_to_the_object_that_produced_it(bench):
    """Provenance, read backwards: everything that ever touched this object."""
    journal = RequestJournal()
    bench.add_interceptor(journal)

    first = Widget(name="A", diameter=1.0)
    second = Widget(name="B", diameter=2.0)
    bench.configure(first, set_diameter=10.0)
    bench.configure(second, set_diameter=20.0)
    bench.configure(first, set_diameter=30.0)

    history = journal.touching("A")
    assert len(history) == 2
    assert [entry["attributes"]["set_diameter"] for entry in history] == [10.0, 30.0]


def test_a_session_can_be_replayed(bench, dish):
    """Read forwards instead, and the same session happens again."""
    journal = RequestJournal()
    bench.add_interceptor(journal)

    bench.configure(dish, set_diameter=64.0)
    bench.configure(dish, set_diameter=12.0)
    assert dish.diameter == 12.0

    bench.remove_interceptor(journal)       # or the replay records itself
    dish.set_diameter(70.0)
    bench.replay(journal)
    assert dish.diameter == 12.0            # the session ended where it ended


def test_a_failed_request_is_recorded_and_skipped_on_replay(bench, dish):
    journal = RequestJournal()
    bench.add_interceptor(journal)

    bench.configure(dish, explode=None, raise_on_error=False)
    bench.configure(dish, set_diameter=5.0)

    assert len(journal.failures()) == 1
    bench.remove_interceptor(journal)
    assert len(bench.replay(journal)) == 1


def test_a_journal_can_be_bounded(bench, dish):
    """A long-running process should not accumulate a session without end."""
    journal = RequestJournal(limit=3)
    bench.add_interceptor(journal)

    for value in range(10):
        bench.configure(dish, set_diameter=float(value))

    assert len(journal) == 3
    assert [entry["attributes"]["set_diameter"] for entry in journal] == [7.0, 8.0, 9.0]


def test_metrics_and_the_journal_compose(bench, dish):
    """They are ordinary interceptors, so nothing special happens when both are present."""
    metrics, journal = RequestMetrics(), RequestJournal()
    bench.add_interceptor(metrics)
    bench.add_interceptor(journal)

    bench.inspect(dish, get_diameter=None)
    assert metrics.snapshot()["inspect"]["calls"] == 1
    assert len(journal) == 1


# --- a journal is a record, not a retainer ----------------------------------------------------

def recorded():
    """A manipulator with a journal on it. Not a fixture: `bench` is taken in this file."""
    thing = Widget(name="held", diameter=70.0)
    manipulator = Observatory(base_classes=[Widget])
    journal = RequestJournal()
    manipulator.add_interceptor(journal)
    return thing, manipulator, journal


def test_a_journal_holds_nothing_alive():
    """An audit trail that pins what it audited is a leak.

    Found downstream: an application whose whole storage design is about *not* keeping results
    in memory -- 407 MB to 71 MB -- found its journal holding a reference to every result frame
    it had ever computed, so evicting one freed nothing.
    """
    import gc
    import weakref

    thing, manipulator, journal = recorded()
    manipulator.inspect(thing, get="diameter", raise_on_error=False)
    watch = weakref.ref(thing)

    assert len(journal) == 1, "the request was not recorded at all"
    del thing, manipulator
    gc.collect()

    assert watch() is None, "the journal is keeping the object it recorded alive"


def test_an_entry_is_the_request_and_whether_it_worked():
    """A record of what was asked and how it went. Not the request as it ran, and not what it
    produced -- a response holds whatever was computed, which for a calculation is the result."""
    thing, manipulator, journal = recorded()
    manipulator.inspect(thing, get="diameter", raise_on_error=False)
    entry = journal.entries[0]

    assert entry["operation"] == "inspect"
    assert entry["object"] == "held"
    assert entry["attributes"] == {"get": "diameter"}
    assert entry["status"] is True
    assert entry["error"] is None
    assert entry["seconds"] >= 0.0
    assert "request" not in entry and "response" not in entry, (
        "the live request and its response are retained")


def test_a_failure_records_what_went_wrong():
    thing, manipulator, journal = recorded()
    manipulator.configure(thing, explode=None, raise_on_error=False)
    entry = journal.entries[-1]

    assert entry["status"] is False
    assert entry["error"], "a failure that records no reason is not worth recording"


def test_an_entry_is_plain_data():
    """Which is what lets an application write a session to a file."""
    import json

    thing, manipulator, journal = recorded()
    manipulator.inspect(thing, get="diameter", raise_on_error=False)

    json.dumps(journal.entries)


def test_an_object_in_the_attributes_is_named_rather_than_held():
    """A batch carries requests in its attributes, and a request names an object. Holding those
    is the same leak one level down."""
    import gc
    import weakref

    thing, manipulator, journal = recorded()
    other = Widget(name="other", diameter=12.0)
    manipulator.inspect(thing, get="diameter", targets=[other], raise_on_error=False)

    entry = journal.entries[-1]
    assert entry["attributes"]["targets"] == ["other"], (
        f"the object is still in there: {entry['attributes']!r}")

    watch = weakref.ref(other)
    del other
    gc.collect()
    assert watch() is None, "an object in the attributes is kept alive by the journal"


def test_the_session_replays_by_naming_what_it_ran_on():
    """A plan of names rather than of objects: the same session runs against whatever project
    it is replayed on, which is what makes it a reproduction rather than a souvenir."""
    thing, manipulator, journal = recorded()
    manipulator.inspect(thing, get="diameter", raise_on_error=False)

    assert journal.entries[0]["object"] == "held", "the record names it"

    # While the object is alive the plan reaches it, so replaying in the process that recorded
    # the session is exactly what it was.
    plan = journal.as_plan()
    assert next(iter(plan.values()))["obj"] is thing

    # Once it is gone the plan carries the name, and whoever replays resolves it against the
    # model in hand. That is what makes a session portable rather than a souvenir.
    import gc

    del thing, plan               # the plan reaches it too, which is the point of the first half
    gc.collect()
    plan = journal.as_plan()
    assert next(iter(plan.values()))["obj"] == "held"
