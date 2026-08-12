"""Several requests that feed each other.

A pipeline is a tree of requests, so most of what is tested here is about the tree rather than
about running: what an edge is, what order the edges imply, what happens to a branch whose root
failed, and whether the whole thing survives being written down and read back.
"""
import asyncio
import json
import time

import pytest

from msb_arch import BaseEntity, Manipulator, Super
from msb_arch.errors import DispatchError, NotFoundError, RequestError, SerializationError


class Thing(BaseEntity):
    value: int


class Arithmetic(Super):
    """Two handlers that produce values, so steps have something to pass each other."""

    OPERATION = "compute"

    def _compute(self, obj, attributes):
        return obj.get("value") * attributes.get("by", 1)

    def _compute_total(self, obj, attributes):
        return sum(attributes.get("of") or [])


class Slow(Super):
    OPERATION = "slowly"

    def _slowly(self, obj, attributes):
        time.sleep(attributes.get("seconds", 0.2))
        return obj.get("value")


@pytest.fixture
def manipulator():
    thing = Thing(name="t", value=6)
    bench = Manipulator(thing, base_classes=[Thing])
    bench.register_operation(Arithmetic(bench))
    bench.register_operation(Slow(bench))
    return bench


@pytest.fixture
def thing(manipulator):
    return manipulator.get_managing_object()


# --- the sugar, and what it records -------------------------------------------------------

def test_the_operations_are_the_methods(manipulator, thing):
    """A pipeline is written by writing the calls you would have made."""
    pipe = manipulator.pipeline()
    step = pipe.compute(thing, by=2)

    assert step.operation == "compute"
    assert step.attributes == {"by": 2}
    assert len(pipe) == 1


def test_something_that_is_not_an_operation_is_not_a_method(manipulator):
    pipe = manipulator.pipeline()
    with pytest.raises(AttributeError):
        pipe.reticulate(splines=4)


def test_a_step_given_nothing_follows_the_one_before(manipulator, thing):
    pipe = manipulator.pipeline()
    first = pipe.compute(thing, by=2)
    second = pipe.inspect(get="value")

    assert second.obj is first
    assert pipe.requires("inspect") == ["compute"]


def test_a_step_given_none_runs_on_the_managing_object(manipulator, thing):
    """"Given nothing" and "given None" have to mean different things, and this is why."""
    pipe = manipulator.pipeline()
    pipe.compute(thing, by=2)
    second = pipe.compute(None, by=3)

    assert second.obj is None
    assert pipe.requires("compute_2") == []


def test_a_step_passed_as_an_argument_is_an_edge(manipulator, thing):
    pipe = manipulator.pipeline()
    doubled = pipe.compute(thing, by=2)
    tripled = pipe.compute(thing, by=3)
    pipe.compute(thing, method="total", of=[doubled, tripled])

    assert pipe.requires("compute_3") == ["compute", "compute_2"]


def test_a_step_can_wait_without_taking_anything(manipulator, thing):
    """Writing a file and reading it back needs an order and carries nothing across."""
    pipe = manipulator.pipeline()
    written = pipe.save(thing, path="out.json")
    pipe.compute(thing, by=2).once(written)

    assert pipe.requires("compute") == ["save"]


def test_repeats_of_one_operation_get_their_own_names(manipulator, thing):
    pipe = manipulator.pipeline()
    pipe.compute(thing, by=2)
    pipe.compute(thing, by=3)
    pipe.compute(thing, by=4)

    assert [step.name for step in pipe.steps()] == ["compute", "compute_2", "compute_3"]


def test_a_step_can_be_named_where_it_is_written(manipulator, thing):
    pipe = manipulator.pipeline()
    pipe.compute(thing, by=2).named("doubled")

    assert pipe["doubled"].attributes == {"by": 2}


def test_an_unregistered_operation_is_refused_while_building(manipulator):
    """A plan that cannot run should not be buildable."""
    pipe = manipulator.pipeline()
    with pytest.raises(DispatchError):
        pipe.add("teleport")


# --- the order the edges imply --------------------------------------------------------------

def test_a_chain_is_one_step_per_stage(manipulator, thing):
    pipe = manipulator.pipeline()
    pipe.compute(thing, by=2)
    pipe.inspect(get="value")
    pipe.compute(by=3)

    assert pipe.order() == [["compute"], ["inspect"], ["compute_2"]]


def test_independent_steps_share_a_stage(manipulator, thing):
    pipe = manipulator.pipeline()
    left = pipe.compute(thing, by=2)
    right = pipe.compute(thing, by=3)
    pipe.compute(thing, method="total", of=[left, right])

    assert pipe.order() == [["compute", "compute_2"], ["compute_3"]]


def test_steps_that_depend_on_each_other_in_a_circle_are_refused(manipulator, thing):
    """Unreachable while building; reachable through a plan edited by hand."""
    pipe = manipulator.pipeline()
    first = pipe.compute(thing, by=2)
    second = pipe.compute(thing, by=3)
    first.after.append(second)
    second.after.append(first)

    with pytest.raises(RequestError, match="circle"):
        pipe.order()


# --- running ---------------------------------------------------------------------------------

def test_what_one_step_produces_reaches_the_next(manipulator, thing):
    pipe = manipulator.pipeline()
    doubled = pipe.compute(thing, by=2)
    tripled = pipe.compute(thing, by=3)
    pipe.compute(thing, method="total", of=[doubled, tripled])

    outcome = pipe.run()
    assert outcome.of("compute") == 12
    assert outcome.output == 12 + 18


def test_a_reference_reaches_wherever_a_request_can_hold_one(manipulator, thing):
    """Inside a list, inside a mapping -- an argument is not a special place."""
    pipe = manipulator.pipeline()
    doubled = pipe.compute(thing, by=2)
    pipe.compute(thing, method="total", of=[doubled, doubled])

    assert pipe.run().output == 24


def test_a_failure_names_the_step_and_keeps_its_kind(manipulator, thing, tmp_path):
    pipe = manipulator.pipeline()
    pipe.load(thing, path=str(tmp_path / "absent.json"))

    with pytest.raises(NotFoundError) as caught:
        pipe.run()
    # `args[0]` rather than `str`, because NotFoundError is a KeyError and those repr their
    # message. The kind is the point of the test: the step failed to find a file, and a
    # caller catching NotFoundError around a pipeline catches it.
    assert "Step 'load'" in caught.value.args[0]


def test_a_failure_can_be_reported_instead(manipulator, thing, tmp_path):
    pipe = manipulator.pipeline()
    pipe.load(thing, path=str(tmp_path / "absent.json"))

    outcome = pipe.run(raise_on_error=False)
    assert outcome.failed == ["load"]


def test_a_branch_below_a_failure_is_skipped_and_the_others_still_run(manipulator, thing,
                                                                     tmp_path):
    """The reason to report rather than raise: a failure should cost its own branch, not all."""
    pipe = manipulator.pipeline()
    doomed = pipe.load(thing, path=str(tmp_path / "absent.json"))
    pipe.inspect(doomed, get_all=None)
    pipe.compute(thing, by=2).named("elsewhere")

    outcome = pipe.run(raise_on_error=False)
    assert outcome["inspect"]["skipped"] is True
    assert outcome["elsewhere"]["status"] is True
    assert outcome.of("elsewhere") == 12


def test_a_step_that_runs_on_nothing_says_so_rather_than_quietly_using_the_managing_object(
        manipulator, thing):
    """An operation that applies methods reports what they returned; it does not hand the
    object on. Without this, the next step silently ran on something else."""
    pipe = manipulator.pipeline()
    configured = pipe.configure(thing, set={"params": {"value": 9}})
    pipe.compute(configured, by=2)

    outcome = pipe.run(raise_on_error=False)
    assert "produced nothing" in outcome["compute"]["error"]


def test_one_method_of_a_step_can_be_named(manipulator, thing):
    """The rule for which of a step's results is its output: one method, its value; several,
    say which."""
    pipe = manipulator.pipeline()
    read = pipe.inspect(thing, get="value", has_attribute="value")
    pipe.compute(thing, method="total", of=[read["get"]])

    assert pipe.run().output == 6


# --- concurrency ------------------------------------------------------------------------------

def test_independent_steps_run_at_the_same_time(manipulator, thing):
    """Two branches of a stage should cost the slower one, not both."""
    pipe = manipulator.pipeline()
    pipe.slowly(thing, seconds=0.3)
    pipe.slowly(thing, seconds=0.3)

    started = time.perf_counter()
    outcome = asyncio.run(pipe.arun())
    elapsed = time.perf_counter() - started

    assert outcome.failed == []
    assert elapsed < 0.5, f"two 0.3s steps took {elapsed:.2f}s, so they ran one after the other"


def test_a_stage_still_waits_for_the_one_before(manipulator, thing):
    pipe = manipulator.pipeline()
    first = pipe.compute(thing, by=2)
    pipe.compute(thing, method="total", of=[first])

    assert asyncio.run(pipe.arun()).output == 12


# --- substitution happens before the interceptors ------------------------------------------

def test_an_interceptor_never_sees_a_placeholder(manipulator, thing):
    """A recorded session has to be replayable, which it is not if a request holds a reference
    to something only the pipeline could resolve."""
    seen = []

    def record(request, call_next):
        seen.append(request)
        return call_next(request)

    manipulator.add_interceptor(record)
    pipe = manipulator.pipeline()
    doubled = pipe.compute(thing, by=2)
    pipe.compute(thing, method="total", of=[doubled])
    pipe.run()

    assert len(seen) == 2
    assert seen[1]["attributes"]["of"] == [12], "the interceptor saw a value, not a reference"
    assert json.dumps(seen[1]["attributes"])          # and one that can be journalled


# --- as data ----------------------------------------------------------------------------------

def test_a_plan_survives_being_written_down_and_read_back(manipulator, thing):
    pipe = manipulator.pipeline(name="arithmetic")
    doubled = pipe.compute(thing, by=2)
    pipe.compute(thing, method="total", of=[doubled])

    plan = json.loads(json.dumps(pipe.to_dict()))
    assert manipulator.pipeline(plan=plan).output == 12


def test_an_object_travels_as_its_own_data(manipulator, thing):
    plan = manipulator.pipeline().compute(thing, by=2)
    pipe = manipulator.pipeline()
    pipe.compute(thing, by=2)

    stored = pipe.to_dict()
    assert stored["steps"][0]["obj"] == {"$type": "Thing", "$data": thing.to_dict()}


def test_the_edges_survive_too(manipulator, thing):
    pipe = manipulator.pipeline()
    written = pipe.compute(thing, by=2)
    pipe.compute(thing, by=3).once(written)

    stored = pipe.to_dict()
    assert stored["steps"][1]["after"] == ["compute"]
    assert manipulator.pipeline(plan=stored).failed == []


def test_a_plan_that_cannot_be_written_down_says_so_when_it_is_written(manipulator, thing):
    """Better than finding out when it is read."""
    pipe = manipulator.pipeline()
    pipe.compute(thing, by=object())

    with pytest.raises(SerializationError):
        pipe.to_dict()


def test_a_plan_referring_to_a_step_that_is_not_there_is_refused(manipulator):
    with pytest.raises(RequestError, match="not in the plan"):
        manipulator.pipeline(plan={"steps": [
            {"name": "second", "operation": "compute", "obj": {"$step": "first"},
             "attributes": {}}]})


def test_a_plan_naming_a_type_that_is_not_here_is_refused(manipulator):
    with pytest.raises(RequestError, match="not imported"):
        manipulator.pipeline(plan={"steps": [
            {"name": "one", "operation": "compute",
             "obj": {"$type": "Sasquatch", "$data": {}}, "attributes": {}}]})


def test_something_that_is_not_a_plan_is_refused(manipulator):
    with pytest.raises(RequestError):
        manipulator.pipeline(plan={"nothing": "useful"})


# --- one way in ------------------------------------------------------------------------------

def test_a_pipeline_is_only_reachable_through_a_manipulator():
    """The class is not part of the package surface: there is one door, and it is the
    orchestrator."""
    import msb_arch

    assert "Pipeline" not in msb_arch.__all__
    assert not hasattr(msb_arch, "Pipeline")


def test_a_pipeline_has_no_operations_of_its_own(manipulator, thing):
    """Its methods are the manipulator's registry, read at the moment of the call. Registering
    an operation makes it appear; nothing is copied, so nothing can drift."""
    pipe = manipulator.pipeline()
    assert not hasattr(pipe, "polish")

    class Polish(Super):
        OPERATION = "polish"

        def _polish(self, obj, attributes):
            return "shiny"

    manipulator.register_operation(Polish(manipulator))
    assert pipe.polish(thing).operation == "polish"
    assert pipe.run().output == "shiny"


def test_every_step_is_run_by_the_manipulator(manipulator, thing):
    """A pipeline runs nothing itself. Each step goes through process_request, which is what
    puts every step through the interceptors, the journal and the metrics like any other
    request."""
    went_through = []
    original = manipulator.process_request

    def counting(request):
        went_through.append(request["operation"])
        return original(request)

    manipulator.process_request = counting
    pipe = manipulator.pipeline()
    doubled = pipe.compute(thing, by=2)
    pipe.compute(thing, method="total", of=[doubled])
    pipe.run()

    assert went_through == ["compute", "compute"]


def test_the_pipeline_never_reaches_past_the_manipulator():
    """A ratchet. The module may ask the orchestrator and nothing else: calling a Super's
    execute, or reading _operations, would be the hierarchy quietly going flat."""
    import pathlib
    import re

    source = (pathlib.Path(__file__).resolve().parent.parent
              / "src" / "msb_arch" / "pipeline.py").read_text(encoding="utf-8")
    for forbidden in (r"\.execute\(", r"\._operations\b", r"\._registry\b", r"\._interceptors\b"):
        assert not re.search(forbidden, source), (
            f"pipeline.py reaches past the manipulator: {forbidden}. Asking it -- "
            "get_supported_operations, process_request -- is the whole of what it may do.")
