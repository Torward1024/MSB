"""Type variables in entity annotations.

A generic entity resolves its type variables from whatever its subclass was parameterized
with. Three things were wrong with that, and each is pinned here: the position of a parameter
was ignored, a constrained variable accepted only its first constraint, and one that nothing
determined raised instead of standing aside.

The tests name what a caller sees -- a value accepted or rejected -- rather than what
`_resolve_type` returns, so they survive a change of mechanism.
"""
from typing import Generic, TypeVar

import pytest

from msb_arch import BaseEntity, errors

T = TypeVar('T')
U = TypeVar('U')
Constrained = TypeVar('Constrained', int, str)
Bounded = TypeVar('Bounded', bound='Animal')
Free = TypeVar('Free')


class Animal(BaseEntity):
    legs: int


class Dog(Animal):
    pass


class Pair(BaseEntity, Generic[T, U]):
    first: T
    second: U


class IntStr(Pair[int, str]):
    pass


class Middle(Pair[int, str]):
    pass


class Leaf(Middle):
    """Parameterized by a grandparent: the arguments are reached through inheritance."""


class Holder(BaseEntity, Generic[Constrained]):
    value: Constrained


class Keeper(BaseEntity, Generic[Bounded]):
    pet: Bounded


class Loose(BaseEntity, Generic[Free]):
    """Never parameterized, so nothing determines what `item` may hold."""
    item: Free


# --- position ---------------------------------------------------------------------------

def test_each_parameter_resolves_to_its_own_argument():
    """Both fields used to get the first argument, so `second` was typed `int`."""
    pair = IntStr(name="p", first=1, second="two")
    assert pair.first == 1
    assert pair.second == "two"


def test_the_first_parameter_still_rejects_the_second_type():
    with pytest.raises(errors.TypeValidationError):
        IntStr(name="p", first="one", second="two")


def test_the_second_parameter_rejects_the_first_type():
    """This is the failure the old resolution allowed: `second` accepted an int."""
    with pytest.raises(errors.TypeValidationError):
        IntStr(name="p", first=1, second=2)


def test_arguments_are_found_through_an_inheritance_chain():
    leaf = Leaf(name="l", first=1, second="two")
    assert (leaf.first, leaf.second) == (1, "two")
    with pytest.raises(errors.TypeValidationError):
        Leaf(name="l", first=1, second=2)


# --- constraints ------------------------------------------------------------------------

@pytest.mark.parametrize("value", [7, "seven"])
def test_a_constrained_variable_accepts_every_constraint(value):
    """Only the first constraint was accepted before, so a `str` was rejected."""
    class Constrainted(Holder[Constrained]):
        pass

    assert Constrainted(name="h", value=value).value == value


def test_a_constrained_variable_rejects_a_type_outside_its_constraints():
    class Constrainted(Holder[Constrained]):
        pass

    with pytest.raises(errors.TypeValidationError):
        Constrainted(name="h", value=1.5)


# --- bounds -----------------------------------------------------------------------------

def test_a_bounded_variable_accepts_a_subclass_of_its_bound():
    class Kennel(Keeper[Bounded]):
        pass

    dog = Dog(name="rex", legs=4)
    assert Kennel(name="k", pet=dog).pet is dog


def test_a_bounded_variable_rejects_something_outside_the_bound():
    class Kennel(Keeper[Bounded]):
        pass

    with pytest.raises(errors.TypeValidationError):
        Kennel(name="k", pet="not an animal")


# --- unparameterized --------------------------------------------------------------------

def test_an_unparameterized_variable_stands_aside_instead_of_raising():
    """It used to raise at construction, so a generic entity could not be used directly.

    Accepting anything matches what `_check_type` already does with any hint it cannot
    reduce to a class: an unresolvable annotation does not block a valid assignment.
    """
    for value in (1, "one", [1], None):
        assert Loose(name="l", item=value).item == value


# --- serialization ----------------------------------------------------------------------

def test_a_parameterized_entity_round_trips():
    original = IntStr(name="p", first=1, second="two")
    restored = IntStr.from_dict(original.to_dict())
    assert (restored.first, restored.second) == (1, "two")
    assert restored == original


def test_a_wrong_type_in_serialized_data_is_still_rejected():
    payload = IntStr(name="p", first=1, second="two").to_dict()
    payload["second"] = 99
    with pytest.raises(errors.TypeValidationError):
        IntStr.from_dict(payload)
