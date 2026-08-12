"""Generating the handler stubs a model implies.

What the generator can know: the handler names dispatch will look for, the signatures, and the
walk into a container. What it cannot: what the handlers do. The tests are about that line.
"""
from typing import List

import pytest

from msb_arch import BaseContainer, BaseEntity, Manipulator, Super


class Bolt(BaseEntity):
    length: float


class Wheel(BaseEntity):
    hub: Bolt
    spokes: List[Bolt]


class Wheels(BaseContainer[Wheel]):
    pass


class Car(BaseEntity):
    wheels: Wheels
    mileage: int


@pytest.fixture
def manipulator():
    return Manipulator(base_classes=[Car])


@pytest.fixture
def source(manipulator):
    return manipulator.scaffold("measure")


def test_one_handler_per_type(source):
    for expected in ("_measure_bolt", "_measure_wheel", "_measure_wheels", "_measure_car"):
        assert f"def {expected}(" in source


def test_the_names_are_the_ones_dispatch_looks_for(manipulator, source):
    """The whole reason to generate them: a handler named anything else is never called."""
    namespace = {}
    exec(compile(source, "generated", "exec"), namespace)

    generated = namespace["MeasureHandlers"](manipulator)
    manipulator.register_operation(generated)

    # It reaches the stub, which raises. Crossing the response boundary makes that a
    # HandlerError, as it does for any exception the framework did not define -- and the
    # message names the handler that still has to be written.
    from msb_arch.errors import HandlerError

    with pytest.raises(HandlerError, match="_measure_bolt"):
        manipulator.measure(Bolt(name="b", length=1.0))


def test_a_container_walks_its_items_and_the_walk_works(manipulator, source):
    namespace = {}
    exec(compile(source, "generated", "exec"), namespace)

    class Measured(namespace["MeasureHandlers"]):
        def _measure_wheel(self, obj, attributes):
            return obj.hub.length

    manipulator.register_operation(Measured(manipulator))
    wheels = Wheels(name="set", items={
        "front": Wheel(name="front", hub=Bolt(name="a", length=2.0), spokes=[]),
        "rear": Wheel(name="rear", hub=Bolt(name="b", length=3.0), spokes=[]),
    })

    assert manipulator.measure(wheels) == {"front": 2.0, "rear": 3.0}


def test_a_stub_raises_rather_than_returning_nothing(source):
    """A handler that silently did nothing would be worse than one that is missing."""
    assert "raise NotImplementedError" in source
    assert source.count("raise NotImplementedError") == 3, "one per entity, none per container"


def test_a_container_is_emitted_after_what_it_holds(source):
    """So the file reads in the order the work happens."""
    assert source.index("_measure_wheel(") < source.index("_measure_wheels(")


def test_what_a_type_holds_is_written_down_where_it_is_needed(source):
    assert "Holds: hub (Bolt), spokes (Bolt)." in source


def test_it_can_be_narrowed_to_the_types_that_matter(manipulator):
    only = manipulator.scaffold("measure", only=["Bolt"])

    assert "_measure_bolt" in only
    assert "_measure_car" not in only


def test_a_model_of_nothing_generates_nothing():
    assert Manipulator(builtins=False).scaffold("measure") == ""


def test_the_generated_source_is_valid_python(source):
    import ast

    ast.parse(source)
