"""Working out what a Super offers from the code that does it."""
import pytest

from msb_arch.catalogue import derive, label_for, order
from msb_arch.mega.manipulator import Manipulator
from msb_arch.super.super import Super


class Chain(Super):
    """A Super whose handlers call one another, as a real one does."""

    OPERATION = "compute"

    def _compute_root(self, obj, attributes):
        return obj.get_items()

    def _compute_middle(self, obj, attributes):
        base = self._compute_root(obj, attributes)
        return base

    def _compute_leaf(self, obj, attributes):
        return self._compute_middle(obj, attributes), self._compute_root(obj, attributes)


def test_the_handlers_are_found_without_being_listed():
    """A Super's handlers name themselves, so the catalogue costs no declaration."""
    found = derive(Chain(None))
    assert set(found) == {"root", "middle", "leaf"}


def test_the_edges_between_handlers_are_exact():
    """Handlers call each other by name, and a call is a call. This is the edge set a
    scheduler needs: what may run at once, and what a change invalidates."""
    found = derive(Chain(None))

    assert found["root"]["requires"] == []
    assert found["middle"]["requires"] == ["root"]
    assert found["leaf"]["requires"] == ["middle", "root"]


def test_what_a_handler_touches_is_for_the_caller_to_interpret():
    """Nothing in the framework knows what an application is about. Names are reported as
    written, and only the caller can say what they mean."""
    plain = derive(Chain(None))
    assert plain["root"]["touches"] == [], "without an interpreter, nothing is claimed"
    assert "get_items" in plain["root"]["calls"], "the raw name is still reported"

    read = derive(Chain(None), interpret=lambda name: "items" if name == "get_items" else None)
    assert read["root"]["touches"] == ["items"]


def test_a_helper_is_followed_whatever_it_is_called():
    """Following anything the class defines, rather than names with an agreed prefix, keeps
    this free of an application's conventions -- and is more complete."""
    found = derive(Chain(None))
    assert "get_items" in found["leaf"]["calls"], "reached two calls deep, through no prefix"


def test_ordering_puts_each_after_what_it_needs():
    found = derive(Chain(None))
    assert order(found, ["leaf", "root", "middle"]) == ["root", "middle", "leaf"]


def test_a_prerequisite_nobody_asked_for_is_not_invented():
    """The caller asked for two things; it gets two things back."""
    found = derive(Chain(None))
    assert order(found, ["leaf", "middle"]) == ["middle", "leaf"]


def test_a_cycle_is_reported_rather_than_raised(caplog):
    """A cycle is a defect in the handlers, not a reason to refuse to run them."""
    cyclic = {"a": {"requires": ["b"]}, "b": {"requires": ["a"]}}
    assert sorted(order(cyclic, ["a", "b"])) == ["a", "b"]


def test_a_label_follows_from_the_name():
    assert label_for("uv_coverage") == "Uv Coverage"
    assert label_for("uv_coverage", {"uv": "UV"}) == "UV Coverage"
    assert label_for("beam_pattern") == "Beam Pattern"


def test_the_registry_is_reached_by_asking_the_manipulator():
    """Not by a caller reaching into it. The registry is the manipulator's own state, and the
    built-in `Catalogue` is how anybody else asks about it -- a dialog, a command line and a
    server all send the same request."""
    from msb_arch.base.baseentity import BaseEntity

    class Thing(BaseEntity):
        value: int

    thing = Thing(name="t", value=1)
    manipulator = Manipulator(thing, operations={"compute": Chain(None)})

    response = manipulator.catalogue(thing, operation="compute", raise_on_error=False)
    result = response["result"] if isinstance(response, dict) and "status" in response else response

    assert set(result["compute"]) == {"root", "middle", "leaf"}
    assert result["compute"]["leaf"]["requires"] == ["middle", "root"]
    assert result["compute"]["leaf"]["label"] == "Leaf"


def test_ordering_is_reached_the_same_way():
    from msb_arch.base.baseentity import BaseEntity

    class Thing(BaseEntity):
        value: int

    thing = Thing(name="t", value=1)
    manipulator = Manipulator(thing, operations={"compute": Chain(None)})

    response = manipulator.catalogue(thing, method="order", operation="compute",
                                     names=["leaf", "root", "middle"], raise_on_error=False)
    result = response["result"] if isinstance(response, dict) and "status" in response else response
    assert result == ["root", "middle", "leaf"]


def test_an_operation_registered_later_is_included():
    """The whole point of deriving: register a Super and the answer covers it, with nobody
    adding it to a table."""
    from msb_arch.base.baseentity import BaseEntity

    class Thing(BaseEntity):
        value: int

    thing = Thing(name="t", value=1)
    manipulator = Manipulator(thing)
    before = manipulator.describe_operations()
    manipulator.register_operation(Chain(None), operation="compute")
    after = manipulator.describe_operations()

    assert "compute" not in before
    assert set(after["compute"]) == {"root", "middle", "leaf"}


def test_nothing_in_the_framework_interprets_a_name():
    """`touches` stays empty until the application says what a name means to it."""
    from msb_arch.base.baseentity import BaseEntity

    class Thing(BaseEntity):
        value: int

    thing = Thing(name="t", value=1)
    manipulator = Manipulator(thing, operations={"compute": Chain(None)})

    plain = manipulator.describe_operations(operation="compute")
    assert plain["compute"]["root"]["touches"] == []

    read = manipulator.describe_operations(
        operation="compute", interpret=lambda name: "items" if name == "get_items" else None)
    assert read["compute"]["root"]["touches"] == ["items"]


def test_a_super_whose_source_cannot_be_read_answers_empty():
    """Introspection that cannot see the code says so by returning nothing, rather than by
    raising in the middle of building somebody's menu."""
    assert derive(object(), "compute") == {}
