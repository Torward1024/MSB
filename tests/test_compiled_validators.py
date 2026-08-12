"""The compiled checks and the structural walk must agree, on everything.

`_check_type` is where the rules live. For speed, the shapes a model is mostly made of are
compiled into a single predicate, and a compiled predicate is a second implementation of those
rules unless something holds it to them. This does: it runs both over a matrix of values and
fails on any disagreement.
"""
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple, Union

import pytest

from msb_arch import BaseEntity, errors


class Probe(BaseEntity):
    """Somewhere to hang the classmethods; no fields of its own are needed."""


#: Every hint worth compiling, and the ones that must decline to.
HINTS = [
    int, str, float, bool, Any,
    Optional[int], Optional[str], Optional[List[int]],
    List[int], List[str], List[List[int]], List[Optional[int]], list,
    Set[int], FrozenSet[str], set,
    Dict[str, int], Dict[str, List[int]], Dict[int, str], dict,
    Tuple[int, str], Tuple[int, ...],
    Union[int, str], Union[int, str, None],
]

#: Values chosen to sit on both sides of every rule above.
VALUES = [
    1, 0, -1, True, 1.5, "a", "", None,
    [], [1], [1, 2], ["a"], [1, "a"], [None], [[1]], [["a"]], [[1], "x"],
    {1, 2}, set(), frozenset({"a"}), frozenset({1}),
    {}, {"a": 1}, {"a": "b"}, {1: "a"}, {"a": [1]}, {"a": [1, "b"]},
    (1, "a"), (1, 2), ("a",), (),
    object(),
]


def walks(hint, value):
    """What the structural walk says: True if it accepts the value."""
    try:
        Probe._check_type("field", value, hint, "Attribute 'field'")
        return True
    except (TypeError, ValueError):
        return False


@pytest.mark.parametrize("hint", HINTS, ids=lambda h: str(h))
def test_a_compiled_check_agrees_with_the_walk(hint):
    compiled = Probe._compiled_validator(hint)
    if compiled is None:
        pytest.skip("nothing compiled for this hint, so the walk is what runs")

    for value in VALUES:
        if value is None:
            continue                       # None is decided before either is consulted
        assert compiled(value) == walks(hint, value), (
            f"{hint} and the walk disagree about {value!r}: "
            f"compiled says {compiled(value)}, the walk says {walks(hint, value)}")


def test_the_shapes_a_model_is_made_of_do_compile():
    """If these stopped compiling the tests above would pass by skipping, and the speed they
    exist for would be gone with nothing to say so."""
    for hint in (int, str, Optional[int], List[int], Set[int], Dict[str, int],
                 List[List[int]], Dict[str, List[int]], Optional[List[int]]):
        assert Probe._compiled_validator(hint) is not None, f"{hint} no longer compiles"


def test_a_real_union_is_left_to_the_walk():
    """Trying members in order, and what each failure means, is the walk's business."""
    assert Probe._compiled_validator(Union[int, str]) is None


def test_a_refusal_still_names_the_element_that_failed():
    """The compiled form answers yes or no. The message has to keep saying which item was
    wrong, or the speed was bought with the thing a reader needs."""
    class Tagged(BaseEntity):
        tags: List[int]

    with pytest.raises(errors.TypeValidationError, match="Item in list 'tags'"):
        Tagged(name="t", tags=["a"])


def test_a_nested_refusal_too():
    class Nested(BaseEntity):
        rows: Dict[str, List[int]]

    with pytest.raises(errors.TypeValidationError):
        Nested(name="n", rows={"a": ["x"]})
