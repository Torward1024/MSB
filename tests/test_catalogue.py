"""Working out what a Super offers from the code that does it."""
from typing import Any, Dict

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


def test_the_edges_are_direct_rather_than_transitive():
    """A scheduler wants the edges that were written. The closure follows from them; going the
    other way loses which is which, and credits a handler with needing something it never
    mentions."""
    found = derive(Chain(None))

    assert found["middle"]["requires"] == ["root"]
    assert found["leaf"]["requires"] == ["middle", "root"], (
        "leaf names both, so both are direct edges")

    # What middle reaches through root is still reported, but as reach rather than as an edge.
    assert "get_items" in found["middle"]["calls"]


def test_everything_a_handler_needs_is_available_on_demand():
    """Direct edges are stored because they are the more informative of the two: the full set
    follows from them by walking, and recovering which edges were written from a closure does
    not. So both answers are available and only one is kept."""
    from msb_arch.catalogue import requirements_of

    found = derive(Chain(None))

    assert found["middle"]["requires"] == ["root"], "stored: what it names"
    assert requirements_of(found, "middle") == ["root"]
    assert requirements_of(found, "leaf") == ["middle", "root"], "walked: everything below it"
    assert requirements_of(found, "root") == []


def test_a_cycle_does_not_hang_the_walk():
    from msb_arch.catalogue import requirements_of

    cyclic = {"a": {"requires": ["b"]}, "b": {"requires": ["a"]}}
    assert requirements_of(cyclic, "a") == ["a", "b"] or requirements_of(cyclic, "a") == ["b"]


class Extended(Chain):
    """A Super that inherits handlers and adds one, as an application's subclass does."""

    def _compute_extra(self, obj, attributes):
        return self._compute_leaf(obj, attributes)


def test_inherited_handlers_are_found():
    """A subclass that adds a handler still has the ones it inherited, and a catalogue that
    reports only the subclass's own body would tell an application half of what it offers."""
    found = derive(Extended(None))

    assert "extra" in found, "the handler it defines"
    assert {"root", "middle", "leaf"} <= set(found), "and the ones it inherited"
    assert found["extra"]["requires"] == ["leaf"]


# --- what a handler accepts -----------------------------------------------------------------

class Filtered(Super):
    """A Super whose handlers read attributes the way real ones do.

    Between them these are every shape found in a real application: read in the handler's own
    body, read by a helper the mapping was handed to, read by a closure that names it something
    else, and read under a name only known at run time.
    """

    OPERATION = "draw"

    def _draw_plain(self, obj, attributes):
        return attributes.get("colour"), attributes["width"]

    def _draw_delegating(self, obj, attributes):
        return self._render(obj, attributes)

    def _draw_by_keyword(self, obj, attributes):
        return self._render(obj, options=attributes)

    def _draw_in_a_closure(self, obj, attributes):
        def build(item, attrs: Dict[str, Any]):
            return attrs.get("in_the_closure")

        return self._apply(obj, attributes, build)

    def _draw_computed(self, obj, attributes):
        wanted = obj.name
        return attributes.get(wanted)

    def _render(self, obj, options):
        return options.get("dpi"), options.get("output_file")

    def _apply(self, obj, attributes, build):
        return build(obj, attributes)


def test_what_a_handler_accepts_is_derived_rather_than_declared():
    """The third thing already in the code and written down again elsewhere: a menu builds a
    control per filter, a command line builds a flag, a server validates a request -- each from
    its own copy of a list the handler already states by reading it."""
    found = derive(Filtered(None))
    assert found["plain"]["accepts"] == ["colour", "width"], "both shapes of read"


def test_a_helper_contributes_what_it_was_handed():
    """`calls` is an upper bound because a shared helper is followed for every caller. This
    is not: the helper is followed at the parameter the mapping actually landed on."""
    found = derive(Filtered(None))
    assert found["delegating"]["accepts"] == ["dpi", "output_file"]
    assert found["by_keyword"]["accepts"] == ["dpi", "output_file"], "by name as well"


def test_a_closure_that_renames_the_mapping_is_followed():
    """A handler that builds its result in an inner function hands the mapping on, and the
    closure calls it whatever it likes."""
    found = derive(Filtered(None))
    assert found["in_a_closure"]["accepts"] == ["in_the_closure"]


def test_a_key_named_at_run_time_is_invisible_and_says_so():
    """The one shape this cannot see, asserted so it is known rather than discovered. A caller
    using `accepts` to reject unknown attributes would refuse a valid request."""
    found = derive(Filtered(None))
    assert found["computed"]["accepts"] == []


def test_what_a_handler_accepts_reaches_the_manipulator():
    from msb_arch.base.baseentity import BaseEntity

    class Thing(BaseEntity):
        value: int

    thing = Thing(name="t", value=1)
    manipulator = Manipulator(thing, operations={"draw": Filtered(None)})

    described = manipulator.describe_operations(operation="draw")
    assert described["draw"]["plain"]["accepts"] == ["colour", "width"]

    response = manipulator.catalogue(thing, operation="draw", raise_on_error=False)
    result = response["result"] if isinstance(response, dict) and "status" in response else response
    assert result["draw"]["delegating"]["accepts"] == ["dpi", "output_file"]
