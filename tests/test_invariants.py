# test_invariants.py
"""Rules about the whole object, which no rule about one field can express.

`Annotated[float, Positive()]` says a value is allowed. It cannot say `end` comes after `start`,
that weights sum to one, or that an array holds at most eight antennas -- every value is fine on
its own and the object is still wrong. Those rules were written by hand in setters, where nothing
enforced them on construction, on restore, or on a write that came in through a request.

An `@invariant` is checked at the same three points a field constraint is: when the object is
built, when it is restored, and after each write. A refused change leaves the object as it was.
"""
import json

import pytest

from msb_arch import BaseContainer, BaseEntity, Manipulator, invariant
from msb_arch.errors import InvariantError, MSBError


class Window(BaseEntity):
    start: float = 0.0
    end: float = 1.0

    @invariant("end must be after start")
    def _ordered(self) -> bool:
        return self.end > self.start


class Antenna(BaseEntity):
    diameter: float = 1.0


class Array(BaseContainer[Antenna]):
    @invariant("an array holds at most three antennas")
    def _small_enough(self) -> bool:
        return len(self) <= 3


class Bench(Manipulator):
    pass


@pytest.fixture
def bench():
    return Bench(base_classes=[Window, Antenna, Array])


# --- the three points a rule is checked at ------------------------------------------------------

def test_a_broken_object_cannot_be_built():
    with pytest.raises(InvariantError, match="end must be after start"):
        Window(name="w", start=2.0, end=1.0)


def test_a_valid_object_is_built_normally():
    window = Window(name="w", start=1.0, end=2.0)

    assert (window.start, window.end) == (1.0, 2.0)


def test_a_write_that_breaks_a_rule_is_refused_and_undone():
    """A refused write leaves the object exactly as it was, the way a refused type does."""
    window = Window(name="w", start=1.0, end=2.0)

    with pytest.raises(InvariantError):
        window.end = 0.5

    assert window.end == 2.0


def test_data_that_breaks_a_rule_cannot_be_restored():
    with pytest.raises(InvariantError):
        Window.from_dict({"type": "Window", "name": "w", "start": 5.0, "end": 1.0})


def test_a_round_trip_of_a_valid_object_still_works():
    window = Window(name="w", start=1.0, end=2.0)

    restored = Window.from_dict(json.loads(json.dumps(dict(window.to_dict()))))

    assert restored == window


# --- fields that have to move together ----------------------------------------------------------

def test_set_applies_a_group_and_checks_once():
    """`start` and `end` cannot be moved one at a time; `set` is what applies them together."""
    window = Window(name="w", start=1.0, end=2.0)

    window.set({"start": 10.0, "end": 20.0})

    assert (window.start, window.end) == (10.0, 20.0)


def test_a_group_that_breaks_a_rule_puts_every_field_back():
    window = Window(name="w", start=1.0, end=2.0)

    with pytest.raises(InvariantError):
        window.set({"start": 30.0, "end": 25.0})

    assert (window.start, window.end) == (1.0, 2.0)


def test_a_request_writes_a_group_the_same_way(bench):
    """Which is what makes the rule reachable from a dialog, a script or a wire."""
    window = Window(name="w", start=1.0, end=2.0)

    bench.configure(window, set={"params": {"start": 5.0, "end": 9.0}})

    assert (window.start, window.end) == (5.0, 9.0)


def test_a_request_that_breaks_a_rule_comes_back_as_a_failed_response(bench):
    window = Window(name="w", start=1.0, end=2.0)

    answer = bench.configure(window, set={"params": {"start": 9.0, "end": 5.0}},
                             raise_on_error=False)

    assert answer.ok is False
    # A failure inside a method arrives as `HandlerError` carrying its text, which is how every
    # other validation failure crosses the response boundary.
    assert "end must be after start" in answer.error
    assert (window.start, window.end) == (1.0, 2.0)


# --- a rule about what a container holds ---------------------------------------------------------

def test_a_container_rule_is_about_its_contents():
    array = Array(name="a")
    for index in range(3):
        array.add(Antenna(name=f"a{index}"))

    with pytest.raises(InvariantError, match="at most three"):
        array.add(Antenna(name="a4"))

    assert sorted(array.get_all()) == ["a0", "a1", "a2"]


def test_a_bulk_set_that_breaks_a_container_rule_puts_the_items_back():
    array = Array(name="a")
    array.add(Antenna(name="a0"))

    with pytest.raises(InvariantError):
        array.set_items({f"x{index}": Antenna(name=f"x{index}") for index in range(5)})

    assert sorted(array.get_all()) == ["a0"]


def test_removing_from_a_container_with_a_rule_still_works():
    array = Array(name="a")
    array.add(Antenna(name="a0"))
    array.add(Antenna(name="a1"))

    array.remove("a0")

    assert sorted(array.get_all()) == ["a1"]


# --- how rules are declared and inherited ----------------------------------------------------------

def test_the_message_defaults_to_the_docstring():
    class Documented(BaseEntity):
        size: int = 1

        @invariant()
        def _positive_size(self) -> bool:
            """size must be at least one"""
            return self.size >= 1

    with pytest.raises(InvariantError, match="size must be at least one"):
        Documented(name="d", size=0)


def test_a_rule_is_inherited_by_a_subclass():
    class Narrow(Window):
        label: str = ""

    with pytest.raises(InvariantError, match="end must be after start"):
        Narrow(name="n", start=2.0, end=1.0)


def test_a_subclass_overrides_a_rule_by_redefining_it():
    class Reversed(Window):
        @invariant("start must be after end")
        def _ordered(self) -> bool:
            return self.start > self.end

    assert Reversed(name="r", start=2.0, end=1.0).start == 2.0
    with pytest.raises(InvariantError, match="start must be after end"):
        Reversed(name="r", start=1.0, end=2.0)


def test_several_rules_all_hold():
    class Twice(BaseEntity):
        low: float = 0.0
        high: float = 10.0

        @invariant("high must be above low")
        def _ordered(self) -> bool:
            return self.high > self.low

        @invariant("low must not be negative")
        def _not_negative(self) -> bool:
            return self.low >= 0.0

    with pytest.raises(InvariantError, match="must not be negative"):
        Twice(name="t", low=-1.0, high=5.0)
    with pytest.raises(InvariantError, match="must be above low"):
        Twice(name="t", low=5.0, high=1.0)


def test_a_rule_that_cannot_be_evaluated_says_so():
    class Broken(BaseEntity):
        size: int = 1

        @invariant("nonsense")
        def _bad(self) -> bool:
            return self.size / 0 > 1

    with pytest.raises(InvariantError, match="could not be evaluated"):
        Broken(name="b")


def test_check_invariants_can_be_called_by_hand():
    """For code that writes several attributes directly rather than through `set`."""
    window = Window(name="w", start=1.0, end=2.0)
    object.__setattr__(window, "end", 0.5)          # straight past every check

    with pytest.raises(InvariantError):
        window.check_invariants()


def test_a_class_with_no_rules_is_unaffected():
    class Plain(BaseEntity):
        size: int = 1

    plain = Plain(name="p", size=1)
    plain.size = -5

    assert plain.size == -5
    assert Plain._invariant_cache == ()
    plain.check_invariants()


def test_an_invariant_is_still_an_ordinary_method():
    window = Window(name="w", start=1.0, end=2.0)

    assert window._ordered() is True


def test_the_error_is_catchable_as_a_value_error():
    """Every MSB error is also the built-in it replaces."""
    with pytest.raises(ValueError):
        Window(name="w", start=2.0, end=1.0)
    with pytest.raises(MSBError):
        Window(name="w", start=2.0, end=1.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
