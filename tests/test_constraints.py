"""Value constraints declared on annotations.

`BaseEntity` checked types and nothing else, so a telescope accepted a diameter of -5.0 and a
product an empty name. The helpers to reject both had been in `utils/validation.py` since the
beginning with nothing connecting them to the model, so every project wrote the same
`__init__` to call them by hand.

A constraint now travels with the annotation, which means it is enforced everywhere a value
arrives -- construction, `set`, and restoring from serialized data -- rather than wherever the
author remembered to check.
"""
import json
from typing import Annotated, Any, Dict, List, Literal, Optional

import pytest

from msb_arch import (BaseContainer,
                      BaseEntity,
                      NonEmpty,
                      NonZero,
                      Positive,
                      Predicate,
                      Range,
                      errors)


class Product(BaseEntity):
    price: Annotated[float, Positive()]
    stock: Annotated[int, Range(0, 100)]
    label: Annotated[str, NonEmpty()]
    ratio: Annotated[float, NonZero()]
    width: Annotated[int, Predicate(lambda value: value % 2 == 0, "must be even")]


def make(**overrides):
    fields = dict(price=10.0, stock=5, label="widget", ratio=2.0, width=4)
    fields.update(overrides)
    return Product(name="p", **fields)


def test_a_valid_object_is_built():
    product = make()
    assert (product.price, product.stock, product.label) == (10.0, 5, "widget")


@pytest.mark.parametrize("field, bad, message", [
    ("price", -1.0, "must be positive"),
    ("stock", 200, "must be between"),
    ("label", "   ", "must not be empty"),
    ("ratio", 0.0, "must be non-zero"),
    ("width", 3, "must be even"),
])
def test_a_violation_is_rejected_with_a_message_naming_the_rule(field, bad, message):
    with pytest.raises(errors.ConstraintError, match=message):
        make(**{field: bad})


def test_a_violation_is_a_validationerror_and_a_valueerror():
    """It belongs with the other ways the caller got the data wrong."""
    with pytest.raises(errors.ValidationError):
        make(price=-1.0)
    with pytest.raises(ValueError):
        make(price=-1.0)


def test_the_type_is_checked_before_the_constraint():
    """A rule should never see a value it was not written for."""
    with pytest.raises(errors.TypeValidationError):
        make(price="free")


def test_a_constraint_holds_on_assignment_too():
    """Enforcing only at construction would leave the object able to become invalid."""
    product = make()
    with pytest.raises(errors.ConstraintError):
        product.set({"price": -5.0})
    assert product.price == 10.0


def test_a_constraint_holds_when_restoring_from_data():
    """Serialized data is an entry point like any other, and is often the least trusted."""
    payload = make().to_dict()
    payload["price"] = -1.0
    with pytest.raises(errors.ConstraintError):
        Product.from_dict(payload)


def test_a_constrained_field_still_round_trips():
    restored = Product.from_dict(json.loads(json.dumps(make().to_dict())))
    assert restored == make()


def test_none_is_still_allowed_where_the_annotation_permits_it():
    """Unset annotated attributes are initialized to None, so a constraint must not fire."""
    class Optionalish(BaseEntity):
        margin: Optional[Annotated[float, Positive()]]

    assert Optionalish(name="o").margin is None


def test_constraints_reach_inside_a_container_item():
    class Products(BaseContainer[Product]):
        pass

    box = Products(name="box")
    box.add(make())
    with pytest.raises(errors.ConstraintError):
        box.add(make(price=-1.0))


def test_several_constraints_on_one_field_all_apply():
    class Narrow(BaseEntity):
        value: Annotated[int, Range(0, 100), Predicate(lambda v: v % 5 == 0, "must divide by 5")]

    assert Narrow(name="n", value=25).value == 25
    with pytest.raises(errors.ConstraintError, match="must divide by 5"):
        Narrow(name="n", value=26)
    with pytest.raises(errors.ConstraintError, match="must be between"):
        Narrow(name="n", value=200)


def test_a_custom_constraint_needs_only_a_check_method():
    from msb_arch import Constraint

    class EndsWith(Constraint):
        def __init__(self, suffix):
            self.suffix = suffix

        def check(self, value, name):
            if not value.endswith(self.suffix):
                raise errors.ConstraintError(f"{name} must end with {self.suffix!r}")

    class Code(BaseEntity):
        tag: Annotated[str, EndsWith("-01")]

    assert Code(name="c", tag="unit-01").tag == "unit-01"
    with pytest.raises(errors.ConstraintError, match="must end with"):
        Code(name="c", tag="unit-02x")


def test_an_unconstrained_annotation_is_untouched():
    """The common case must not pay for the feature."""
    class Plain(BaseEntity):
        values: List[int]
        table: Dict[str, int]

    plain = Plain(name="p", values=[1, 2], table={"a": 1})
    assert plain.values == [1, 2]
    with pytest.raises(errors.TypeValidationError):
        Plain(name="p", values=["x"], table={})


# --- the compiled validator (P5) ----------------------------------------------------------

class Differential(BaseEntity):
    """One field per shape the compiler might get wrong."""
    plain: int
    text: str
    entity: Product
    anything: Any
    listed: List[int]
    mapped: Dict[str, int]
    either: Optional[int]
    picked: Literal["a", "b"]
    constrained: Annotated[int, Positive()]


CORPUS = [
    ("plain", 1, True), ("plain", "x", False), ("plain", True, True),
    ("text", "x", True), ("text", 1, False),
    ("anything", object(), True), ("anything", [1], True),
    ("listed", [1, 2], True), ("listed", ["x"], False), ("listed", "no", False),
    ("mapped", {"a": 1}, True), ("mapped", {"a": "x"}, False),
    ("either", 5, True), ("either", "x", False),
    ("picked", "a", True), ("picked", "z", False),
    ("constrained", 5, True), ("constrained", -5, False),
]


@pytest.mark.parametrize("field, value, acceptable", CORPUS)
def test_the_compiled_path_agrees_with_the_structural_walk(field, value, acceptable):
    """Two implementations of one rule is how they drift apart, so they are compared here.

    `_validate_type` takes a compiled one-call check where it can and the structural walk
    otherwise. Whichever it takes, the answer has to be the same.
    """
    entity = Differential(name="d")

    def structural():
        Differential._check_type(field, value, Differential._fields[field], f"Attribute '{field}'")

    def compiled():
        entity._validate_type(field, value, Differential._fields[field])

    structural_ok = True
    try:
        structural()
    except (errors.TypeValidationError, errors.ConstraintError):
        structural_ok = False

    compiled_ok = True
    try:
        compiled()
    except (errors.TypeValidationError, errors.ConstraintError):
        compiled_ok = False

    assert compiled_ok == structural_ok == acceptable, (
        f"{field}={value!r}: compiled said {compiled_ok}, structural said {structural_ok}"
    )


def test_the_validator_table_belongs_to_the_class_that_built_it():
    """A subclass reading its parent's table would validate against the parent's fields."""
    class Parent(BaseEntity):
        value: int

    class Child(Parent):
        value: str

    Parent(name="p", value=1)
    assert Child(name="c", value="text").value == "text"
    with pytest.raises(errors.TypeValidationError):
        Child(name="c", value=1)
