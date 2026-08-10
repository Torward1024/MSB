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


class Telescope(BaseEntity):
    diameter: float

    def get_diameter(self) -> float:
        return self.diameter

    def set_diameter(self, value: float) -> bool:
        self.diameter = value
        return True

    def explode(self) -> None:
        raise RuntimeError("boom")


class Telescopes(BaseContainer[Telescope]):
    pass


class Observatory(Manipulator):
    pass


@pytest.fixture
def bare():
    """An orchestrator with no operation written by hand. This is the point of the item."""
    return Observatory(base_classes=[Telescope, Telescopes])


# --- what you get for free ----------------------------------------------------------------

def test_an_orchestrator_reads_and_writes_with_no_super_written(bare):
    dish = Telescope(name="DSS14", diameter=70.0)

    assert bare.inspect(dish, get_diameter=None) == 70.0
    bare.configure(dish, set_diameter=64.0)
    assert bare.inspect(dish, get_diameter=None) == 64.0


def test_the_builtins_serve_containers_too(bare):
    """A container answers `get` with an item, where an entity answers with an attribute.
    The built-ins hold no opinion about that: they apply whatever the request names."""
    dishes = Telescopes(name="array")
    dishes.add(Telescope(name="DSS14", diameter=70.0))

    assert bare.inspect(dishes, has_item="DSS14") is True
    assert bare.inspect(dishes, get="DSS14").diameter == 70.0
    assert list(bare.inspect(dishes, get_all=None)) == ["DSS14"]


def test_reading_reports_every_method_even_when_one_fails(bare):
    """`strict=False` for inspect: a caller reading several things wants the whole picture."""
    dish = Telescope(name="d", diameter=1.0)
    results = bare.inspect(dish, get_diameter=None, explode=None, raise_on_error=False)

    assert results["result"]["get_diameter"]["status"] is True
    assert results["result"]["explode"]["status"] is False


def test_writing_stops_at_the_first_failure(bare):
    """`strict=True` for configure: a half-applied configuration is worse than a rejected one."""
    dish = Telescope(name="d", diameter=1.0)
    response = bare.configure(dish, explode=None, set_diameter=99.0, raise_on_error=False)

    assert response["status"] is False
    assert dish.diameter == 1.0


# --- what an existing application still gets ----------------------------------------------

def test_registering_your_own_replaces_the_builtin_silently():
    """Every application written before these existed does exactly this, and must not break."""
    class MyInspector(Super):
        OPERATION = "inspect"

        def _inspect(self, obj, attributes):
            return "mine"

    bench = Observatory(base_classes=[Telescope])
    bench.register_operation(MyInspector(bench))

    assert bench.inspect(Telescope(name="d", diameter=1.0), get_diameter=None) == "mine"
    assert "inspect" not in bench._builtin_operations


def test_two_registrations_of_your_own_still_raise():
    """That collision is a mistake, and stays one."""
    class MyOperation(Super):
        OPERATION = "measure"

        def _measure(self, obj, attributes):
            return self._apply_methods(obj, attributes)

    bench = Observatory(base_classes=[Telescope])
    bench.register_operation(MyOperation(bench))
    with pytest.raises(errors.RegistrationError, match="already registered"):
        bench.register_operation(MyOperation(bench))


def test_replacing_a_builtin_twice_raises_the_second_time():
    """The first registration takes the name over; after that it is yours to collide with."""
    class MyInspector(Super):
        OPERATION = "inspect"

        def _inspect(self, obj, attributes):
            return "mine"

    bench = Observatory(base_classes=[Telescope])
    bench.register_operation(MyInspector(bench))
    with pytest.raises(errors.RegistrationError, match="already registered"):
        bench.register_operation(MyInspector(bench))


# --- opting out ---------------------------------------------------------------------------

def test_builtins_can_be_declined():
    bench = Observatory(base_classes=[Telescope], builtins=False)
    assert bench._operations == {}
    assert not hasattr(bench, "inspect")


def test_the_builtins_are_importable_and_registerable_by_hand():
    """Declining them and registering one explicitly is a legitimate middle ground."""
    bench = Observatory(base_classes=[Telescope], builtins=False)
    bench.register_operation(Inspector(bench))

    assert bench.inspect(Telescope(name="d", diameter=5.0), get_diameter=None) == 5.0
    assert Configurator.OPERATION == "configure"


def test_a_builtin_is_thin_enough_to_subclass():
    """One call to `_apply_methods`, so overriding one type keeps the rest working."""
    class Careful(Configurator):
        def _configure_telescope(self, obj, attributes):
            if attributes.get("set_diameter", 0) > 100:
                return self._build_response(obj, False, "set_diameter", None, "too large")
            return self._apply_methods(obj, attributes, strict=True)

    bench = Observatory(base_classes=[Telescope], builtins=False)
    bench.register_operation(Careful(bench))

    dish = Telescope(name="d", diameter=1.0)
    bench.configure(dish, set_diameter=50.0)
    assert dish.diameter == 50.0
    bench.configure(dish, set_diameter=500.0, raise_on_error=False)
    assert dish.diameter == 50.0


# --- descending into a named member -------------------------------------------------------

class Band(BaseEntity):
    frequency: float

    def get_frequency(self) -> float:
        return self.frequency

    def set_frequency(self, value: float) -> bool:
        self.frequency = value
        return True


class Bands(BaseContainer[Band]):
    pass


@pytest.fixture
def bands(bare):
    bare.update_registry(additional_classes=[Band, Bands])
    collection = Bands(name="bands")
    collection.add(Band(name="X", frequency=8400.0))
    collection.add(Band(name="L", frequency=1420.0))
    return collection


def test_a_request_can_ask_the_collection_or_one_member(bare, bands):
    """Only the request can say which is meant, so the presence of the key decides."""
    assert set(bare.inspect(bands, get_all=None)) == {"X", "L"}
    assert bare.inspect(bands, name="X", get_frequency=None) == 8400.0


def test_configuring_reaches_one_member(bare, bands):
    bare.configure(bands, name="L", set_frequency=1600.0)
    assert bands.get("L").frequency == 1600.0
    assert bands.get("X").frequency == 8400.0


def test_naming_a_member_that_is_not_there_says_so(bare, bands):
    with pytest.raises(Exception, match="not found"):
        bare.inspect(bands, name="nope", get_frequency=None)


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

        def count(self) -> int:
            return len(self.entries)

    class RegistryInspector(Inspector):
        NESTED_KEY = "entry"

        def _nested_getter(self, obj):
            return obj.get_entry if isinstance(obj, Registry) else super()._nested_getter(obj)

    bench = Observatory(base_classes=[Registry, Band], builtins=False)
    bench.register_operation(RegistryInspector(bench))
    registry = Registry(name="r", entries={"X": Band(name="X", frequency=8400.0)})

    assert bench.inspect(registry, count=None) == 1
    assert bench.inspect(registry, entry="X", get_frequency=None) == 8400.0


def test_an_operation_with_no_collection_is_unaffected(bare):
    """A plain entity has no members, so the hook returns None and the request is applied to
    the entity exactly as before -- including treating `name` as a method it does not have.

    `Inspector` is `strict=False`, so that one failure is reported beside the successes rather
    than failing the request, which is the behaviour the descent must not have changed.
    """
    dish = Telescope(name="d", diameter=70.0)
    assert bare.inspect(dish, get_diameter=None) == 70.0

    results = bare.inspect(dish, name="anything", get_diameter=None, raise_on_error=False)
    assert results["status"] is True
    assert results["result"]["get_diameter"]["result"] == 70.0
    assert results["result"]["name"]["status"] is False
