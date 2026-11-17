"""Value constraints declared on annotations.

`BaseEntity` checked types and nothing else, so a widget accepted a diameter of -5.0 and a
product an empty name. The helpers to reject both had been in `utils/validation.py` since the
beginning with nothing connecting them to the model, so every project wrote the same
`__init__` to call them by hand.

A constraint now travels with the annotation, which means it is enforced everywhere a value
arrives -- construction, `set`, and restoring from serialized data -- rather than wherever the
author remembered to check.
"""
import json
from types import ModuleType
from typing import Annotated, Any, Dict, List, Literal, Optional

import pytest

from msb_arch import (BaseContainer,
                      BaseEntity,
                      Manipulator,
                      NonEmpty,
                      NonZero,
                      NotNone,
                      Positive,
                      Predicate,
                      Project,
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


class StockRecord(BaseEntity):
    description: str
    sku: Annotated[str, NonEmpty(), NotNone()]
    count: Annotated[int, NotNone()] = 0


@pytest.mark.parametrize("fields", [{}, {"sku": None}, {"sku": "A1", "count": None}])
def test_not_none_checks_the_value_after_defaults(fields):
    field = "count" if "count" in fields else "sku"
    with pytest.raises(errors.ConstraintError, match=field + "'.*None"):
        StockRecord(name="p", **fields)


def test_a_subclass_can_make_an_inherited_required_field_nullable():
    class DraftStock(StockRecord):
        sku: str

    assert DraftStock(name="draft").sku is None
    with pytest.raises(errors.ConstraintError, match="sku"):
        StockRecord(name="final")


def test_not_none_preserves_falsy_values_and_the_underlying_type():
    class Entry(BaseEntity):
        value: Annotated[Any, NotNone()]

    for value in (0, False, "", [], {}):
        assert Entry(name="e", value=value).value is value
    with pytest.raises(errors.TypeValidationError, match="sku"):
        StockRecord(name="p", sku=12)
    with pytest.raises(errors.ConstraintError, match="empty"):
        StockRecord(name="p", sku="  ")
    assert make(label=None).label is None


def test_not_none_rejects_assignment_and_rolls_back_group_writes_and_reset():
    row = StockRecord(name="p", sku="A1", description="original")
    before = row.to_dict()
    with pytest.raises(errors.ConstraintError, match="sku"):
        row.sku = None
    with pytest.raises(errors.ConstraintError, match="sku"):
        row["sku"] = None
    with pytest.raises(errors.ConstraintError, match="sku"):
        row.set({"description": "changed", "sku": None})
    assert row.to_dict() == before
    with pytest.raises(errors.ConstraintError, match="sku"):
        row.reset_attributes()
    assert row.to_dict() == before


def test_not_none_restores_valid_data_and_uses_defaults_for_missing_keys():
    row = StockRecord(name="p", sku="A1")
    payload = json.loads(json.dumps(row.to_dict()))
    assert StockRecord.from_dict(payload) == row
    del payload["count"]
    assert StockRecord.from_dict(payload).count == 0
    payload["sku"] = None
    with pytest.raises(errors.ConstraintError, match="sku"):
        StockRecord.from_dict(payload)
    del payload["sku"]
    with pytest.raises(errors.ConstraintError, match="sku"):
        StockRecord.from_dict(payload)


@pytest.mark.parametrize(("hint", "bad"), [
    (list[Annotated[int, NotNone()]], [None]),
    (tuple[Annotated[int, NotNone()], ...], (None,)),
    (tuple[str, Annotated[int, NotNone()]], ("a", None)),
    (dict[str, Annotated[int, NotNone()]], {"a": None}),
    (dict[Annotated[str, NotNone()], int], {None: 1}),
])
def test_not_none_applies_at_the_annotated_collection_position(hint, bad):
    class Entries(BaseEntity):
        values: hint

    assert Entries(name="e").values is None
    with pytest.raises(errors.ConstraintError, match="values"):
        Entries(name="e", values=bad)


def test_not_none_on_a_collection_leaves_unmarked_items_nullable():
    class Entries(BaseEntity):
        values: Annotated[list[int], NotNone()]
        labels: dict[str, str]
        optional: Optional[Annotated[int, NotNone()]]

    assert Entries(name="e", values=[None], labels={"a": None}).optional is None
    with pytest.raises(errors.ConstraintError, match="values"):
        Entries(name="e")
    with pytest.raises(errors.TypeValidationError, match="Key"):
        Entries(name="e", values=[], labels={None: "invalid"})


def test_required_fields_in_postponed_annotations(monkeypatch):
    import sys
    module = ModuleType("postponed_stock_model")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(
        "from __future__ import annotations\n"
        "from typing import Annotated\n"
        "from msb_arch import BaseEntity, NotNone\n"
        "class Stock(BaseEntity):\n"
        "    count: Annotated[int, NotNone()]\n"
        "    later: 'DefinedByTheApplicationLater'\n",
        module.__dict__,
    )
    stock = module.Stock(name="a", count=0)
    with pytest.raises(errors.ConstraintError, match="count"):
        stock["count"] = None
    with pytest.raises(errors.ConstraintError, match="count"):
        module.Stock.from_dict({"name": "a"})


def test_not_none_applies_to_an_explicitly_marked_activation_flag():
    class Flag(BaseEntity):
        isactive: Annotated[bool, NotNone()]

    with pytest.raises(errors.ConstraintError, match="isactive"):
        Flag(name="a", isactive=None)
    flag = Flag(name="a", isactive=False)
    with pytest.raises(errors.ConstraintError, match="isactive"):
        flag.isactive = None
    assert flag.isactive is False


@pytest.mark.parametrize("deep", [False, True])
def test_cloning_a_container_keeps_required_fields_and_item_copy_policy(deep):
    class StockBin(BaseContainer[StockRecord]):
        label: Annotated[list[str], NotNone()]

    row = StockRecord(name="p", sku="A1")
    box = StockBin(name="bin", items={"p": row}, label=["west"])
    cloned = box.clone(deep=deep)
    assert cloned == box
    assert (cloned.label is box.label) is (not deep)
    assert (cloned.get("p") is row) is (not deep)
    assert StockBin.from_dict(box.to_dict()) == box


def test_annotated_key_and_entity_restore_from_plain_data():
    class CountSheet(BaseEntity):
        counts: dict[Annotated[int, NotNone()], int]
        row: Annotated[StockRecord, NotNone()]

    sheet = CountSheet.from_dict({"name": "s", "counts": {"1": 0},
                                  "row": {"name": "p", "sku": "A1"}})
    assert sheet.counts == {1: 0}
    assert sheet.row.sku == "A1"


def test_a_container_refusing_a_required_field_keeps_its_items():
    class StockBin(BaseContainer[StockRecord]):
        location: Annotated[str, NotNone()]

    row = StockRecord(name="p", sku="A1")
    box = StockBin(name="bin", items={"p": row}, location="west")
    with pytest.raises(errors.ConstraintError, match="location"):
        box.set({"_items": {}, "location": None})
    assert box.get("p") is row
    assert box.location == "west"


def test_a_project_enforces_its_own_required_field_through_requests_and_restore():
    class StockRoom(Project):
        site: Annotated[str, NotNone()]

        def create_item(self, item_code="ITEM", isactive=True):
            self.add_item(StockRecord(name=item_code, sku=item_code, isactive=isactive))

    room = StockRoom(name="room", site="west")
    assert StockRoom.from_dict(room.to_dict()) == room
    response = Manipulator(base_classes=[StockRoom]).configure(
        room, set={"params": {"site": None}}, raise_on_error=False)
    assert not response.ok and "site" in response.error
    assert room.site == "west"
    with pytest.raises(errors.SerializationError, match="site"):
        StockRoom.from_dict({"name": "room", "site": None})


def test_required_keywords_reach_narrow_collection_constructors_on_restore():
    class NamedShelf(BaseContainer[StockRecord]):
        site: Annotated[str, NotNone()]

        def __init__(self, *, name, items, isactive=True, site):
            super().__init__(name=name, items=items, isactive=isactive, site=site)

    class Room(Project):
        site: Annotated[str, NotNone()]

        def __init__(self, *, name, items, site):
            super().__init__(name=name, items=items, site=site)

        def create_item(self, item_code="ITEM", isactive=True):
            self.add_item(StockRecord(name=item_code, sku=item_code, isactive=isactive))

    for model in (NamedShelf, Room):
        original = model(name="store", items={}, site="west")
        assert model.from_dict(original.to_dict()) == original


def test_restoring_unmarked_fields_preserves_narrow_constructor_behaviour():
    class OffsetShelf(BaseContainer[StockRecord]):
        count: int = 0

        def __init__(self, *, name, items=None, isactive=True, count=0):
            super().__init__(name=name, items=items, isactive=isactive, count=count + 1)

    shelf = OffsetShelf(name="s", count=4)
    assert OffsetShelf.from_dict(shelf.to_dict()).count == 5


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


# --- the value every comparison is false about ---------------------------------------------

@pytest.mark.parametrize("constraint", [Positive(), NonZero(), Range(0.0, 1.0)])
def test_nan_is_refused_by_every_numeric_constraint(constraint):
    """`value <= 0` lets NaN through and `not 0 <= value <= 1` rejects it, so the same value
    passed or failed depending on how a rule happened to be spelled. It is refused once, in
    the one place that turns a value into something comparable."""
    with pytest.raises(errors.ConstraintError):
        constraint.check(float("nan"), "size")


def test_a_constrained_field_refuses_nan():
    class Sized(BaseEntity):
        size: Annotated[float, Positive()]

    with pytest.raises(errors.ConstraintError):
        Sized(name="s", size=float("nan"))


def test_infinity_is_still_a_number():
    """It compares, so every rule means what it says about it. Only NaN is the odd one."""
    class Sized(BaseEntity):
        size: Annotated[float, Positive()]

    assert Sized(name="s", size=float("inf")).size == float("inf")


def test_a_bool_is_not_a_number_for_a_constraint():
    """True is 1 to Python, and a rule about a size should not accept it."""
    with pytest.raises(errors.TypeValidationError):
        Positive().check(True, "size")


def test_a_group_one_field_of_which_is_refused_writes_none_of_it():
    """`set` applies a group together and puts the whole of it back when an `@invariant`
    refuses it. A constraint on one field refuses inside the loop instead, so the fields
    written before it stayed written: `set({"label": "new", "price": -1})` renamed a product
    and then refused its price. An application cannot fix that from outside, which is why two
    editors in pAstroCORE restated the model's own rules before writing.
    """
    product = make()
    before = product.to_dict()

    with pytest.raises(errors.ConstraintError):
        product.set({"label": "renamed", "price": -1.0})

    assert product.label == before["label"], "the field written before the refusal stayed"
    assert product.to_dict() == before, "a refused group left part of itself behind"


def test_a_group_one_field_of_which_is_the_wrong_type_writes_none_of_it():
    """The same, for a type rather than a constraint: both raise inside the loop."""
    product = make()
    before = product.to_dict()

    with pytest.raises(errors.TypeValidationError):
        product.set({"label": "renamed", "stock": "many"})

    assert product.to_dict() == before, "a refused group left part of itself behind"


def test_a_group_that_is_accepted_is_written_whole():
    """The guard must not undo a group that nothing refused."""
    product = make()

    product.set({"label": "renamed", "price": 99.0})

    assert (product.label, product.price) == ("renamed", 99.0)
