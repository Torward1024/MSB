"""A tree of requests: a batch whose steps may feed each other.

The convention comes first -- a plan is data, handed to the manipulator in one call, exactly as
`process_request` and `batch` take theirs. The draft at the bottom of this file is sugar over
that and nothing else, which is itself tested: what it produces is a plan, and it runs one by
handing it back to the manipulator.
"""
import asyncio
import json
import time

import pytest

from msb_arch import BaseEntity, Manipulator, Super
from msb_arch.errors import (AttributeNotFoundError, DispatchError, NotFoundError, RequestError)


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


# --- the convention: a plan is data ---------------------------------------------------------

def test_a_plan_is_requests_keyed_by_name(manipulator, thing):
    outcome = manipulator.pipeline({
        "doubled": {"operation": "compute", "obj": thing, "by": 2},
        "tripled": {"operation": "compute", "obj": thing, "by": 3},
    })

    assert outcome["doubled"]["status"] is True
    assert outcome.of("doubled") == 12 and outcome.of("tripled") == 18


def test_a_plan_can_be_a_sequence_too(manipulator, thing):
    """The two shapes `batch` already accepts, for the same reason."""
    outcome = manipulator.pipeline([
        {"name": "doubled", "operation": "compute", "obj": thing, "by": 2},
        {"operation": "compute", "obj": thing, "by": 3},
    ])

    assert outcome.of("doubled") == 12
    assert outcome["step_2"]["status"] is True


def test_attributes_need_no_nesting_but_may_have_it(manipulator, thing):
    """The common case should not cost a nested mapping; the explicit spelling still works."""
    short = manipulator.pipeline({"a": {"operation": "compute", "obj": thing, "by": 2}})
    spelt = manipulator.pipeline({"a": {"operation": "compute", "obj": thing,
                                        "attributes": {"by": 2}}})

    assert short.output == spelt.output == 12


def test_a_reference_is_an_edge(manipulator, thing):
    outcome = manipulator.pipeline({
        "doubled": {"operation": "compute", "obj": thing, "by": 2},
        "again":   {"operation": "compute", "method": "total", "obj": thing, "of": ["@doubled"]},
    })

    assert outcome.output == 12


def test_a_reference_reaches_wherever_a_request_can_hold_one(manipulator, thing):
    """Inside a list, inside a mapping -- an argument is not a special place."""
    outcome = manipulator.pipeline({
        "doubled": {"operation": "compute", "obj": thing, "by": 2},
        "summed":  {"operation": "compute", "method": "total", "obj": thing,
                    "of": ["@doubled", "@doubled"]},
    })

    assert outcome.output == 24


def test_a_step_with_no_object_follows_the_one_before(manipulator, thing):
    """The chain, written by leaving `obj` out."""
    outcome = manipulator.pipeline({
        "read":    {"operation": "load", "obj": thing, "path": "absent.json"},
        "follows": {"operation": "compute", "by": 2},
    }, raise_on_error=False)

    assert outcome["follows"]["skipped"] is True, "it waited for the step before it"


def test_a_step_given_none_runs_on_the_managing_object(manipulator, thing):
    """"Said nothing" and "said None" have to mean different things, and this is why."""
    outcome = manipulator.pipeline({
        "first":  {"operation": "compute", "obj": thing, "by": 2},
        "second": {"operation": "compute", "obj": None, "by": 3},
    })

    assert outcome.of("second") == 18


def test_a_step_can_wait_without_taking_anything(manipulator, thing, tmp_path):
    """Writing a file and reading it back needs an order and carries nothing across."""
    path = str(tmp_path / "out.json")
    outcome = manipulator.pipeline({
        "written": {"operation": "save", "obj": thing, "path": path},
        "read":    {"operation": "load", "obj": thing, "path": path, "after": ["written"]},
    })

    assert outcome.of("read").value == 6


def test_a_string_that_really_begins_with_an_at_sign(manipulator, thing):
    """Without an escape, a framework convention quietly eats a caller's data."""
    outcome = manipulator.pipeline({
        "named": {"operation": "configure", "obj": thing, "set": {"params": {"name": "@@home"}}},
    })

    assert outcome["named"]["status"] is True
    assert thing.name == "@home"


def test_one_method_of_a_step_can_be_named(manipulator, thing):
    """The rule for which of a step's results is its output: one method, its value; several,
    say which."""
    outcome = manipulator.pipeline({
        "read":   {"operation": "inspect", "obj": thing, "get": "value",
                   "has_attribute": "value"},
        "summed": {"operation": "compute", "method": "total", "obj": thing, "of": ["@read.get"]},
    })

    assert outcome.output == 6


# --- what the edges imply ---------------------------------------------------------------------

def test_a_chain_runs_in_order_whatever_order_it_was_written_in(manipulator, thing):
    outcome = manipulator.pipeline({
        "last":  {"operation": "compute", "method": "total", "obj": thing, "of": ["@first"]},
        "first": {"operation": "compute", "obj": thing, "by": 2},
    })

    assert outcome.of("last") == 12


def test_a_plan_that_refers_to_nothing_is_refused_before_anything_runs(manipulator, thing,
                                                                      tmp_path):
    """A typo in the last step should not surface after the first has written a file."""
    path = tmp_path / "out.json"
    with pytest.raises(RequestError, match="not in the plan"):
        manipulator.pipeline({
            "written": {"operation": "save", "obj": thing, "path": str(path)},
            "broken":  {"operation": "compute", "obj": "@writen"},
        })
    assert not path.exists()


def test_steps_that_depend_on_each_other_in_a_circle_are_refused(manipulator, thing):
    with pytest.raises(RequestError, match="circle"):
        manipulator.pipeline({
            "a": {"operation": "compute", "obj": thing, "after": ["b"]},
            "b": {"operation": "compute", "obj": thing, "after": ["a"]},
        })


def test_an_unregistered_operation_is_refused(manipulator, thing):
    with pytest.raises(DispatchError):
        manipulator.pipeline({"a": {"operation": "teleport", "obj": thing}})


def test_a_step_without_an_operation_is_refused(manipulator, thing):
    with pytest.raises(RequestError, match="names no operation"):
        manipulator.pipeline({"a": {"obj": thing}})


def test_something_that_is_not_a_plan_is_refused(manipulator):
    with pytest.raises(RequestError):
        manipulator.pipeline("not a plan")


def test_an_empty_plan_is_refused(manipulator):
    with pytest.raises(RequestError):
        manipulator.pipeline({})


# --- failure ------------------------------------------------------------------------------------

def test_a_failure_names_the_step_and_keeps_its_kind(manipulator, thing, tmp_path):
    with pytest.raises(NotFoundError) as caught:
        manipulator.pipeline({"read": {"operation": "load", "obj": thing,
                                       "path": str(tmp_path / "absent.json")}})
    # `args[0]` rather than `str`: NotFoundError is a KeyError, and those repr their message.
    assert "Step 'read'" in caught.value.args[0]


def test_a_branch_below_a_failure_is_skipped_and_the_others_still_run(manipulator, thing,
                                                                      tmp_path):
    """The reason to report rather than raise: a failure should cost its own branch, not all."""
    outcome = manipulator.pipeline({
        "doomed":    {"operation": "load", "obj": thing, "path": str(tmp_path / "absent.json")},
        "below":     {"operation": "inspect", "obj": "@doomed", "get": "value"},
        "elsewhere": {"operation": "compute", "obj": thing, "by": 2},
    }, raise_on_error=False)

    assert outcome.failed == ["doomed", "below"]
    assert outcome["below"]["skipped"] is True
    assert outcome.of("elsewhere") == 12


def test_a_step_that_runs_on_nothing_says_so_rather_than_quietly_using_the_managing_object(
        manipulator, thing):
    """An operation that applies methods reports what they returned; it does not hand the object
    on. Without this, the next step silently ran on something else."""
    outcome = manipulator.pipeline({
        "changed": {"operation": "configure", "obj": thing, "set": {"params": {"value": 9}}},
        "after":   {"operation": "compute", "obj": "@changed", "by": 2},
    }, raise_on_error=False)

    assert "produced nothing" in outcome["after"]["error"]


# --- concurrency ---------------------------------------------------------------------------------

def test_independent_steps_run_at_the_same_time(manipulator, thing):
    """Two branches of a stage should cost the slower one, not both."""
    plan = {"left":  {"operation": "slowly", "obj": thing, "seconds": 0.3},
            "right": {"operation": "slowly", "obj": thing, "seconds": 0.3}}

    started = time.perf_counter()
    outcome = manipulator.pipeline(plan, concurrent=True)
    elapsed = time.perf_counter() - started

    assert outcome.failed == []
    assert elapsed < 0.5, f"two 0.3s steps took {elapsed:.2f}s, so they ran one after the other"


def test_a_stage_still_waits_for_the_one_before(manipulator, thing):
    outcome = manipulator.pipeline({
        "first":  {"operation": "compute", "obj": thing, "by": 2},
        "second": {"operation": "compute", "method": "total", "obj": thing, "of": ["@first"]},
    }, concurrent=True)

    assert outcome.output == 12


# --- substitution happens before the interceptors ---------------------------------------------

def test_an_interceptor_never_sees_a_reference(manipulator, thing):
    """A recorded session has to be replayable, which it is not if a request holds a reference
    only the pipeline could resolve."""
    seen = []

    def record(request, call_next):
        seen.append(request)
        return call_next(request)

    manipulator.add_interceptor(record)
    manipulator.pipeline({
        "doubled": {"operation": "compute", "obj": thing, "by": 2},
        "summed":  {"operation": "compute", "method": "total", "obj": thing, "of": ["@doubled"]},
    })

    assert len(seen) == 2
    assert seen[1]["attributes"]["of"] == [12], "the interceptor saw a value, not a reference"


def test_a_plan_is_data_all_the_way_through(manipulator):
    """Written by hand, stored, sent: it is JSON, and running it needs nothing else."""
    plan = json.loads(json.dumps({
        "built":   {"operation": "load", "obj": None, "path": "thing.json", "kind": None},
    }))
    assert isinstance(plan["built"], dict)          # nothing here is an object or a callable


# --- every step goes through the manipulator ----------------------------------------------------

def test_every_step_is_one_process_request(manipulator, thing):
    """A pipeline runs nothing itself, which is what puts every step through the interceptors,
    the journal and the metrics like any other request."""
    went_through = []
    original = manipulator.process_request

    def counting(request):
        went_through.append(request["operation"])
        return original(request)

    manipulator.process_request = counting
    manipulator.pipeline({
        "one": {"operation": "compute", "obj": thing, "by": 2},
        "two": {"operation": "compute", "method": "total", "obj": thing, "of": ["@one"]},
    })

    assert went_through == ["compute", "compute"]


def test_the_module_never_reaches_past_the_manipulator():
    """A ratchet. Calling a Super's execute, or reading _operations, would be the hierarchy
    quietly going flat."""
    import pathlib
    import re

    source = (pathlib.Path(__file__).resolve().parent.parent
              / "src" / "msb_arch" / "pipeline.py").read_text(encoding="utf-8")
    for forbidden in (r"\.execute\(", r"\._operations\b", r"\._registry\b", r"\._interceptors\b"):
        assert not re.search(forbidden, source), (
            f"pipeline.py reaches past the manipulator: {forbidden}. Asking it -- "
            "get_supported_operations, process_request -- is the whole of what it may do.")


def test_nothing_of_the_pipeline_is_exported():
    """One door: `manipulator.pipeline`."""
    import msb_arch

    assert not hasattr(msb_arch, "Pipeline")
    assert not [name for name in msb_arch.__all__ if "ipeline" in name]


# --- the draft, which is sugar and is tested as sugar -------------------------------------------

def test_a_draft_produces_a_plan_and_nothing_else(manipulator, thing):
    """The whole claim about the draft: what it makes is what could have been typed."""
    draft = manipulator.pipeline()
    loaded = draft.load(thing, path="in.json")
    draft.compute(loaded, by=2)

    assert draft.plan() == {
        "load":    {"operation": "load", "obj": thing, "path": "in.json"},
        "compute": {"operation": "compute", "obj": "@load", "by": 2},
    }


def test_a_draft_runs_by_handing_its_plan_to_the_manipulator(manipulator, thing):
    """There is one execution path and the draft is not it."""
    handed = []
    original = manipulator.pipeline

    def watching(plan=None, **kwargs):
        if plan is not None:
            handed.append(plan)
        return original(plan, **kwargs)

    draft = original()
    draft.compute(thing, by=2)
    manipulator.pipeline = watching
    outcome = draft.run()

    assert handed == [draft.plan()]
    assert outcome.output == 12


def test_a_draft_leaves_out_what_it_was_not_told(manipulator, thing):
    """A step written with no object leaves `obj` out of the plan, which is how the plan spells
    'the step before'."""
    draft = manipulator.pipeline()
    draft.compute(thing, by=2)
    draft.inspect(get="value")

    assert "obj" not in draft.plan()["inspect"]


def test_a_draft_numbers_repeats_and_takes_a_name(manipulator, thing):
    draft = manipulator.pipeline()
    draft.compute(thing, by=2)
    draft.compute(thing, by=3)
    draft.compute(thing, by=4, step="quadrupled")

    assert list(draft.plan()) == ["compute", "compute_2", "quadrupled"]


def test_a_draft_offers_only_what_is_registered(manipulator, thing):
    """Its methods are the manipulator's registry, read at the moment of the call, so nothing is
    copied and nothing can drift."""
    draft = manipulator.pipeline()
    with pytest.raises(AttributeNotFoundError):
        draft.polish(thing)

    class Polish(Super):
        OPERATION = "polish"

        def _polish(self, obj, attributes):
            return "shiny"

    manipulator.register_operation(Polish(manipulator))
    draft.polish(thing)

    assert draft.run().output == "shiny"


def test_a_draft_refuses_an_unregistered_operation_through_add(manipulator):
    draft = manipulator.pipeline()
    with pytest.raises(DispatchError):
        draft.add("teleport")


def test_a_drafted_plan_is_the_same_plan_written_by_hand(manipulator, thing):
    """The two paths meet: same steps, same answer."""
    draft = manipulator.pipeline()
    doubled = draft.compute(thing, by=2)
    draft.compute(thing, method="total", of=[doubled], step="summed")

    by_hand = {
        "compute": {"operation": "compute", "obj": thing, "by": 2},
        "summed":  {"operation": "compute", "obj": thing, "method": "total", "of": ["@compute"]},
    }

    assert draft.plan() == by_hand
    assert draft.run().output == manipulator.pipeline(by_hand).output == 12


# --- edges found by probing them ---------------------------------------------------------------

def test_after_given_one_name_rather_than_a_list(manipulator, thing):
    """A string is a sequence of letters, and iterating it would wait for steps called w, r, i."""
    outcome = manipulator.pipeline({
        "written": {"operation": "compute", "obj": thing, "by": 2},
        "second":  {"operation": "compute", "obj": thing, "by": 3, "after": "written"},
    })

    assert outcome.failed == []
    assert list(outcome) == ["written", "second"]


def test_a_step_whose_name_contains_a_dot(manipulator, thing):
    """`@totals.by_month` has to mean the step called that, not the by_month result of a step
    called totals -- and the wrong reading is the plausible one."""
    outcome = manipulator.pipeline({
        "totals.by_month": {"operation": "compute", "obj": thing, "by": 2},
        "used":            {"operation": "compute", "method": "total", "obj": thing,
                            "of": ["@totals.by_month"]},
    })

    assert outcome.of("used") == 12


def test_naming_a_method_still_works_where_no_step_is_called_that(manipulator, thing):
    outcome = manipulator.pipeline({
        "read": {"operation": "inspect", "obj": thing, "get": "value", "has_attribute": "value"},
        "used": {"operation": "compute", "method": "total", "obj": thing, "of": ["@read.get"]},
    })

    assert outcome.of("used") == 6


def test_concurrency_inside_a_running_loop_says_what_to_use(manipulator, thing):
    """A server or a window is already in a loop, and asyncio.run inside one raises something
    that says nothing about pipelines."""
    plan = {"a": {"operation": "compute", "obj": thing, "by": 2}}

    async def inside():
        with pytest.raises(RequestError, match="apipeline"):
            manipulator.pipeline(plan, concurrent=True)
        return await manipulator.apipeline(plan)

    assert asyncio.run(inside()).output == 12
