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
