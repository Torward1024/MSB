"""`inspect` and `configure` without writing a `Super`.

Measured on the project this framework was written for, 20 of its 21 handlers held no domain
logic: they were one call to `_apply_methods`, and six were a redundant type check and one
call. Those two operations served 185 of its 194 facade calls. They follow from the request
model rather than from any domain -- an attribute names a method, and the method reads or
writes -- so the framework supplies them.

The constraint that shaped this is compatibility. Registering an `Inspector` of your own is
how every existing application is written, and it has to keep meaning exactly what it meant.
So a user registration replaces a built-in silently, while two registrations of one name that
are both yours still raise.
"""
import pytest

from msb_arch import BaseContainer, BaseEntity, Manipulator, Super, errors
from msb_arch.super.builtins import Configurator, Inspector


class Widget(BaseEntity):
    diameter: float

    def get_diameter(self) -> float:
        return self.diameter

    def set_diameter(self, value: float) -> bool:
        self.diameter = value
        return True

    def explode(self) -> None:
        raise RuntimeError("boom")

    def get_broken(self) -> float:
        raise RuntimeError("boom")


class Widgets(BaseContainer[Widget]):
    pass


class Observatory(Manipulator):
    pass


@pytest.fixture
def bare():
    """An orchestrator with no operation written by hand. This is the point of the item."""
    return Observatory(base_classes=[Widget, Widgets])


# --- what you get for free ----------------------------------------------------------------

def test_an_orchestrator_reads_and_writes_with_no_super_written(bare):
    dish = Widget(name="DSS14", diameter=70.0)

    assert bare.inspect(dish, get_diameter=None) == 70.0
    bare.configure(dish, set_diameter=64.0)
    assert bare.inspect(dish, get_diameter=None) == 64.0


def test_the_builtins_serve_containers_too(bare):
    """A container answers `get` with an item, where an entity answers with an attribute.
    The built-ins hold no opinion about that: they apply whatever the request names."""
    dishes = Widgets(name="array")
    dishes.add(Widget(name="DSS14", diameter=70.0))

    assert bare.inspect(dishes, has_item="DSS14") is True
    assert bare.inspect(dishes, get="DSS14").diameter == 70.0
    assert list(bare.inspect(dishes, get_all=None)) == ["DSS14"]


def test_reading_reports_every_method_even_when_one_fails(bare):
    """`strict=False` for inspect: a caller reading several things wants the whole picture."""
    dish = Widget(name="d", diameter=1.0)
    results = bare.inspect(dish, get_diameter=None, get_broken=None, raise_on_error=False)

    assert results["result"]["get_diameter"]["status"] is True
    assert results["result"]["get_broken"]["status"] is False


def test_writing_stops_at_the_first_failure(bare):
    """`strict=True` for configure: a half-applied configuration is worse than a rejected one."""
    dish = Widget(name="d", diameter=1.0)
    response = bare.configure(dish, explode=None, set_diameter=99.0, raise_on_error=False)

    assert response["status"] is False
    assert dish.diameter == 1.0


# --- inspect reads, and only reads (3.0.0) ---------------------------------------------------

def test_inspect_refuses_a_method_that_is_not_named_as_a_read(bare):
    """`inspect` and `configure` were one loop with a different strictness, so a request recorded
    as a read could remove, activate or overwrite.

    Found in an application: a source was deactivated through `inspect`. The journal said nothing
    had changed, and when the source was not there the request came back quietly, where the same
    request through `configure` raised.
    """
    dishes = Widgets(name="array")
    dishes.add(Widget(name="DSS14", diameter=70.0))

    with pytest.raises(errors.RequestError, match="'deactivate_item'.*configure"):
        bare.inspect(dishes, deactivate_item="DSS14")
    assert dishes.get("DSS14").isactive is True, "the refused request changed the object"

    bare.configure(dishes, deactivate_item="DSS14")
    assert dishes.get("DSS14").isactive is False


def test_a_refused_request_runs_none_of_it(bare):
    """Refused whole, before anything runs: reading half of it and writing none would still
    report a read of an object the caller meant to change."""
    dish = Widget(name="d", diameter=1.0)

    response = bare.inspect(dish, get_diameter=None, set_diameter=5.0, raise_on_error=False)

    assert response["status"] is False
    assert "set_diameter" in response["error"]
    assert dish.diameter == 1.0


@pytest.mark.parametrize("name,reads", [
    ("get", True), ("get_all", True), ("has_item", True), ("is_active", True),
    ("getter", False), ("set", False), ("remove", False), ("deactivate_item", False),
    ("clone", False), ("to_dict", False), ("history", False),
])
def test_a_read_is_known_by_its_name(name, reads):
    """By the name alone, so a caller -- a session filter, a permission check -- knows the answer
    without the object."""
    assert Inspector.reads(name) is reads


def test_a_member_is_read_by_the_same_rule(bare, bands):
    """Descending into a member is not a way round it."""
    with pytest.raises(Exception, match="set_rating"):
        bare.inspect(bands, name="X", set_rating=1.0)
    assert bands.get("X").rating == 8400.0


def test_a_model_with_a_reading_verb_of_its_own_widens_the_rule():
    """Rather than naming a read as something else."""
    class Lock(BaseEntity):
        engaged: bool

        def can_open(self) -> bool:
            return not self.engaged

    class LockInspector(Inspector):
        READING_PREFIXES = Inspector.READING_PREFIXES + ("can_",)

    bench = Observatory(base_classes=[Lock], builtins=False)
    bench.register_operation(LockInspector(bench))

    assert bench.inspect(Lock(name="front", engaged=False), can_open=None) is True


def test_configure_takes_reads_as_well_as_changes(bare):
    """Changing a model is more than `set`, and a request that reads along the way is not wrong.
    Only `inspect` is narrowed."""
    dish = Widget(name="d", diameter=1.0)

    answer = bare.configure(dish, set_diameter=2.0, get_diameter=None)

    assert answer["get_diameter"]["result"] == 2.0


def test_a_failed_request_is_logged_without_holding_what_it_named(bare, caplog):
    """A log record keeps its arguments, and an exception keeps the frames that raised it -- and
    those hold the request. Logged as the exception, a refused request stayed alive in any handler
    that keeps records."""
    import gc
    import logging
    import weakref

    dish = Widget(name="d", diameter=1.0)
    held = Widget(name="held", diameter=2.0)
    watch = weakref.ref(held)

    with caplog.at_level(logging.ERROR):
        bare.inspect(dish, remove=held, raise_on_error=False)
    assert caplog.records, "nothing was logged, so this checks nothing"

    del held
    gc.collect()
    assert watch() is None, "a log record is keeping the request's objects alive"


# --- what an existing application still gets ----------------------------------------------

def test_registering_your_own_replaces_the_builtin_silently():
    """Every application written before these existed does exactly this, and must not break."""
    class MyInspector(Super):
        OPERATION = "inspect"

        def _inspect(self, obj, attributes):
            return "mine"

    bench = Observatory(base_classes=[Widget])
    bench.register_operation(MyInspector(bench))

    assert bench.inspect(Widget(name="d", diameter=1.0), get_diameter=None) == "mine"
    assert "inspect" not in bench._builtin_operations


def test_two_registrations_of_your_own_still_raise():
    """That collision is a mistake, and stays one."""
    class MyOperation(Super):
        OPERATION = "measure"

        def _measure(self, obj, attributes):
            return self._apply_methods(obj, attributes)

    bench = Observatory(base_classes=[Widget])
    bench.register_operation(MyOperation(bench))
    with pytest.raises(errors.RegistrationError, match="already registered"):
        bench.register_operation(MyOperation(bench))


def test_replacing_a_builtin_twice_raises_the_second_time():
    """The first registration takes the name over; after that it is yours to collide with."""
    class MyInspector(Super):
        OPERATION = "inspect"

        def _inspect(self, obj, attributes):
            return "mine"

    bench = Observatory(base_classes=[Widget])
    bench.register_operation(MyInspector(bench))
    with pytest.raises(errors.RegistrationError, match="already registered"):
        bench.register_operation(MyInspector(bench))


# --- opting out ---------------------------------------------------------------------------

def test_builtins_can_be_declined():
    bench = Observatory(base_classes=[Widget], builtins=False)
    assert bench._operations == {}
    assert not hasattr(bench, "inspect")


def test_the_builtins_are_importable_and_registerable_by_hand():
    """Declining them and registering one explicitly is a legitimate middle ground."""
    bench = Observatory(base_classes=[Widget], builtins=False)
    bench.register_operation(Inspector(bench))

    assert bench.inspect(Widget(name="d", diameter=5.0), get_diameter=None) == 5.0
    assert Configurator.OPERATION == "configure"


def test_a_builtin_is_thin_enough_to_subclass():
    """One call to `_apply_methods`, so overriding one type keeps the rest working."""
    class Careful(Configurator):
        def _configure_widget(self, obj, attributes):
            if attributes.get("set_diameter", 0) > 100:
                return self._build_response(obj, False, "set_diameter", None, "too large")
            return self._apply_methods(obj, attributes, strict=True)

    bench = Observatory(base_classes=[Widget], builtins=False)
    bench.register_operation(Careful(bench))

    dish = Widget(name="d", diameter=1.0)
    bench.configure(dish, set_diameter=50.0)
    assert dish.diameter == 50.0
    bench.configure(dish, set_diameter=500.0, raise_on_error=False)
    assert dish.diameter == 50.0


# --- descending into a named member -------------------------------------------------------

class Band(BaseEntity):
    rating: float

    def get_rating(self) -> float:
        return self.rating

    def set_rating(self, value: float) -> bool:
        self.rating = value
        return True


class Bands(BaseContainer[Band]):
    pass


@pytest.fixture
def bands(bare):
    bare.update_registry(additional_classes=[Band, Bands])
    collection = Bands(name="bands")
    collection.add(Band(name="X", rating=8400.0))
    collection.add(Band(name="L", rating=1420.0))
    return collection


def test_a_request_can_ask_the_collection_or_one_member(bare, bands):
    """Only the request can say which is meant, so the presence of the key decides."""
    assert set(bare.inspect(bands, get_all=None)) == {"X", "L"}
    assert bare.inspect(bands, name="X", get_rating=None) == 8400.0


def test_configuring_reaches_one_member(bare, bands):
    bare.configure(bands, name="L", set_rating=1600.0)
    assert bands.get("L").rating == 1600.0
    assert bands.get("X").rating == 8400.0


def test_naming_a_member_that_is_not_there_says_so(bare, bands):
    with pytest.raises(Exception, match="not found"):
        bare.inspect(bands, name="nope", get_rating=None)


def test_the_getter_is_a_hook_because_the_descent_is_not_uniform():
    """A container answers `get(name)`; something else answers differently.

    This is the whole reason the descent is a hook rather than a convention, and it was
    predicted before it was needed: a `Project` exposes `get_observation(name)`, so a built-in
    that assumed `get` would silently fail to reach anything inside one.
    """
    class Registry(BaseEntity):
        """Holds its members under a name of its own choosing."""
        entries: dict

        def get_entry(self, name):
            return self.entries.get(name)

        def get_count(self) -> int:
            return len(self.entries)

    class RegistryInspector(Inspector):
        NESTED_KEY = "entry"

        def _nested_getter(self, obj):
            return obj.get_entry if isinstance(obj, Registry) else super()._nested_getter(obj)

    bench = Observatory(base_classes=[Registry, Band], builtins=False)
    bench.register_operation(RegistryInspector(bench))
    registry = Registry(name="r", entries={"X": Band(name="X", rating=8400.0)})

    assert bench.inspect(registry, get_count=None) == 1
    assert bench.inspect(registry, entry="X", get_rating=None) == 8400.0


def test_an_operation_with_no_collection_is_unaffected(bare):
    """A plain entity has no members, so the hook returns None and the request is applied to
    the entity exactly as before -- including treating `name` as a method it does not have.

    `Inspector` is `strict=False`, so that one failure is reported beside the successes rather
    than failing the request, which is the behaviour the descent must not have changed.
    """
    dish = Widget(name="d", diameter=70.0)
    assert bare.inspect(dish, get_diameter=None) == 70.0

    results = bare.inspect(dish, name="anything", get_diameter=None, raise_on_error=False)
    assert results["status"] is True
    assert results["result"]["get_diameter"]["result"] == 70.0
    assert results["result"]["name"]["status"] is False
