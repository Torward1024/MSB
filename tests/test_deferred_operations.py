"""An operation whose `Super` is built the first time it is needed.

Registering an operation costs whatever its module costs to import. For an operation reached
from a menu -- a plot, a report -- that is paid on every start whether or not anyone opens the
menu. Deferring it moves the cost to the first use, and `warm()` moves it to wherever the
application would rather have it.

What must stay true: a deferred operation is registered from the moment it is declared. It
appears in the catalogue, it has a facade, a pipeline may name it. Only the building waits.
"""
import threading
import time

import pytest

from msb_arch import BaseEntity, Manipulator, Super, errors


class Thing(BaseEntity):
    value: int


class Slow(Super):
    """Stands in for a Super whose module costs a second to import."""

    OPERATION = "slowly"
    built = 0

    def __init__(self, manipulator=None):
        super().__init__(manipulator)
        Slow.built += 1

    def _slowly(self, obj, attributes):
        return obj.get("value")


class Bench(Manipulator):
    pass


@pytest.fixture(autouse=True)
def counted():
    Slow.built = 0


@pytest.fixture
def bench():
    return Bench(base_classes=[Thing])


@pytest.fixture
def thing():
    return Thing(name="t", value=7)


# --- registered now, built later ------------------------------------------------------

def test_declaring_one_builds_nothing(bench):
    bench.register_deferred("slowly", lambda: Slow(bench))
    assert Slow.built == 0


def test_it_counts_as_registered_straight_away(bench):
    bench.register_deferred("slowly", lambda: Slow(bench))

    assert "slowly" in bench.get_supported_operations()
    assert hasattr(bench, "slowly") and hasattr(bench, "aslowly")
    assert Slow.built == 0


def test_the_first_request_builds_it(bench, thing):
    bench.register_deferred("slowly", lambda: Slow(bench))

    assert bench.slowly(thing) == 7
    assert Slow.built == 1


def test_and_only_the_first(bench, thing):
    bench.register_deferred("slowly", lambda: Slow(bench))

    bench.slowly(thing)
    bench.slowly(thing)
    bench.process_request({"operation": "slowly", "obj": thing})

    assert Slow.built == 1


def test_a_pipeline_may_name_one(bench, thing):
    """A plan is checked against the registry before it runs, so a deferred operation has to
    be in it -- otherwise a plan naming one would be refused for a typo it does not have."""
    bench.register_deferred("slowly", lambda: Slow(bench))

    outcome = bench.pipeline({"step": {"operation": "slowly", "obj": thing}})

    assert outcome.output == 7
    assert Slow.built == 1


def test_warm_builds_everything(bench):
    bench.register_deferred("slowly", lambda: Slow(bench))

    assert bench.warm() == ["slowly"]
    assert Slow.built == 1
    assert bench.warm() == [], "nothing left to build"


def test_warm_can_be_narrowed(bench):
    bench.register_deferred("slowly", lambda: Slow(bench))
    bench.register_deferred("other", lambda: Slow(bench))

    assert bench.warm(["slowly"]) == ["slowly"]
    assert Slow.built == 1


def test_two_threads_asking_at_once_build_one(bench, thing):
    """The point of the lock: the cost being deferred is expensive, so paying it twice is
    worse than waiting."""
    def slow_factory():
        time.sleep(0.05)
        return Slow(bench)

    bench.register_deferred("slowly", slow_factory)
    results = []

    def ask():
        results.append(bench.slowly(thing))

    threads = [threading.Thread(target=ask) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [7] * 6
    assert Slow.built == 1


def test_warming_in_the_background_while_something_asks(bench, thing):
    def slow_factory():
        time.sleep(0.05)
        return Slow(bench)

    bench.register_deferred("slowly", slow_factory)
    warming = threading.Thread(target=bench.warm)
    warming.start()
    answer = bench.slowly(thing)
    warming.join()

    assert answer == 7
    assert Slow.built == 1


# --- the ordinary rules still apply ----------------------------------------------------

def test_a_name_already_taken_is_refused(bench):
    bench.register_deferred("slowly", lambda: Slow(bench))
    with pytest.raises(errors.RegistrationError):
        bench.register_deferred("slowly", lambda: Slow(bench))


def test_a_deferred_name_may_still_replace_a_builtin(bench, thing):
    class MyInspector(Super):
        OPERATION = "inspect"

        def _inspect(self, obj, attributes):
            return "mine"

    bench.register_deferred("inspect", lambda: MyInspector(bench))
    assert bench.inspect(thing) == "mine"


def test_a_name_that_would_shadow_a_method_is_refused(bench):
    with pytest.raises(errors.RegistrationError):
        bench.register_deferred("batch", lambda: Slow(bench))


def test_something_that_is_not_a_factory_is_refused(bench):
    with pytest.raises(errors.RegistrationError):
        bench.register_deferred("slowly", Slow(bench))


def test_a_factory_that_produces_the_wrong_thing_says_so(bench, thing):
    bench.register_deferred("slowly", lambda: object())

    with pytest.raises(errors.RegistrationError, match="no execute"):
        bench.slowly(thing)


def test_registering_over_a_deferred_one_wins(bench, thing):
    """An application that decides to build it eagerly after all should not have to unregister
    anything first."""
    class Eager(Super):
        OPERATION = "slowly"

        def _slowly(self, obj, attributes):
            return "eager"

    bench.register_deferred("slowly", lambda: Slow(bench))
    bench.register_operation(Eager(bench), operation="slowly")

    assert bench.slowly(thing) == "eager"
    assert Slow.built == 0


def test_the_methods_of_a_built_super_are_registered(bench, thing):
    """A request may name a method of the Super itself, and that only works if the registry
    learned about it when it was built."""
    bench.register_deferred("slowly", lambda: Slow(bench))
    bench.slowly(thing)

    assert Slow in bench._registry


# --- asking what it offers builds it ---------------------------------------------------

def test_describing_a_deferred_operation_builds_it(bench):
    """A dialog that builds its menu from the catalogue must not be told the operation has no
    handlers because nobody has used it yet."""
    bench.register_deferred("slowly", lambda: Slow(bench))

    described = bench.describe_operations("slowly")

    assert Slow.built == 1
    assert "slowly" in described


def test_describing_everything_builds_everything(bench):
    bench.register_deferred("slowly", lambda: Slow(bench))

    assert "slowly" in bench.describe_operations()
    assert Slow.built == 1


def test_ordering_and_requirements_build_it_too(bench):
    bench.register_deferred("slowly", lambda: Slow(bench))
    assert bench.order_handlers("slowly", []) == []
    assert Slow.built == 1
