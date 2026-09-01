# test_declared_defaults.py
"""A value written after the annotation is what the field starts as.

Until 2.0 it was not. The constructor set every field it was not given to None, so

    class Part(BaseEntity):
        price: float = 4.5

built an object whose `price` was None while the class itself still held 4.5. The syntax meant
nothing, and the object was wrong in a way that only surfaced when something did arithmetic on
it. Everyone coming from a dataclass, from pydantic or from attrs writes this and expects it to
work; the workaround was to pass every value by hand at every construction.
"""
import json
from typing import Dict, List, Optional

import pytest

from msb_arch import BaseContainer, BaseEntity, errors


class Part(BaseEntity):
    price: float = 4.5
    label: str = "blank"
    tags: List[str] = []
    lookup: Dict[str, int] = {}
    unset: float


class Parts(BaseContainer[Part]):
    pass


# --- what a field starts as ----------------------------------------------------------------------

def test_a_declared_value_is_what_the_field_starts_as():
    part = Part(name="p")

    assert part.price == 4.5
    assert part.label == "blank"


def test_a_field_with_no_declared_value_starts_as_none():
    assert Part(name="p").unset is None


def test_a_value_passed_in_wins_over_the_declared_one():
    assert Part(name="p", price=9.0).price == 9.0


def test_passing_none_explicitly_still_means_none():
    """Asking for nothing is different from not asking."""
    assert Part(name="p", price=None).price is None


# --- the mutable trap ------------------------------------------------------------------------------

def test_a_mutable_start_is_per_object_not_shared():
    """One list shared by every object of a class is the oldest mistake in the language."""
    first, second = Part(name="a"), Part(name="b")

    first.tags.append("x")
    first.lookup["k"] = 1

    assert first.tags == ["x"]
    assert second.tags == []
    assert first.lookup == {"k": 1}
    assert second.lookup == {}


def test_the_class_still_holds_the_declaration():
    Part(name="a").tags.append("x")

    assert Part.tags == []


# --- inheritance -------------------------------------------------------------------------------------

def test_a_declared_value_is_inherited():
    class Bolt(Part):
        thread: str = "M6"

    bolt = Bolt(name="b")

    assert bolt.price == 4.5
    assert bolt.thread == "M6"


def test_a_subclass_overrides_the_declared_value():
    class Expensive(Part):
        price: float = 99.0

    assert Expensive(name="e").price == 99.0
    assert Part(name="p").price == 4.5


# --- it goes through everything the field does ---------------------------------------------------------

def test_a_declared_value_is_validated_like_any_other():
    class Wrong(BaseEntity):
        size: int = "not an int"

    with pytest.raises(errors.TypeValidationError):
        Wrong(name="w")


def test_a_declared_value_survives_a_round_trip():
    part = Part(name="p")

    restored = Part.from_dict(json.loads(json.dumps(dict(part.to_dict()))))

    assert restored == part
    assert restored.price == 4.5


def test_data_missing_a_field_restores_it_to_the_declared_value():
    """A file written before the field existed reads as the declaration says, not as None."""
    restored = Part.from_dict({"type": "Part", "name": "p"})

    assert restored.price == 4.5
    assert restored.tags == []


def test_a_constraint_still_applies_to_a_declared_value():
    from typing import Annotated

    from msb_arch import Positive

    class Guarded(BaseEntity):
        price: Annotated[float, Positive()] = -1.0

    with pytest.raises(errors.ConstraintError):
        Guarded(name="g")


def test_an_entity_declared_as_a_value_is_not_shared_by_accident():
    """A model object as a declared value would otherwise be owned by every instance at once."""
    class Holder(BaseEntity):
        part: Optional[Part] = None

    first, second = Holder(name="a"), Holder(name="b")

    assert first.part is None and second.part is None


def test_a_container_field_still_works():
    class Assembly(BaseEntity):
        parts: Optional[Parts] = None

    assembly = Assembly(name="a", parts=Parts(name="parts"))

    assert assembly.parts.name == "parts"


def test_a_property_alongside_a_field_of_another_name_is_untouched():
    class WithProperty(BaseEntity):
        size: float = 1.0

        @property
        def doubled(self) -> float:
            return self.size * 2

    thing = WithProperty(name="w")

    assert thing.size == 1.0
    assert thing.doubled == 2.0


def test_annotating_a_field_and_then_defining_something_else_of_that_name_is_reported():
    """Not silently None: the value is judged like any other, so the class is told what it did."""
    class Confused(BaseEntity):
        size: float

        @property
        def size(self) -> float:                    # noqa: F811 - the point of the test
            return 1.0

    with pytest.raises(errors.TypeValidationError):
        Confused(name="c")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
