"""Benchmarks that fail a build when performance regresses.

Wall-clock thresholds do not work for this. A CI runner is between two and ten times slower
than a developer machine and varies run to run, so a threshold loose enough not to be flaky
is loose enough to hide a tenfold regression -- which is what the older assertions in
`test_performance.py` do.

Three kinds of assertion here are stable across machines:

- **Ratios.** Both sides are measured in the same run on the same machine, so the hardware
  cancels out. "An entity costs no more than N times a plain dict" survives a slow runner.
- **Counts.** How many times a hot path is entered is not a measurement at all, it is
  arithmetic, and it is exactly what the cost of entity construction turned out to be about.
- **Scaling.** Cost at 2n against cost at n catches an accidental quadratic, which is the
  regression that has actually happened here before (R3, adding 4000 items took 1.4 s).

Budgets carry headroom over what was measured, so they fail on a real regression rather than
on noise. Each says what it is defending and what the number was when it was set.
"""
import time
from typing import Dict, List

import pytest

from msb_arch import BaseContainer, BaseEntity
from msb_arch.base import serializable


class Reading(BaseEntity):
    value: float
    label: str


class Readings(BaseContainer[Reading]):
    pass


class Nested(BaseEntity):
    reading: Reading
    table: Dict[str, List[float]]


def per_operation(action, count, repeats=5):
    """Seconds per operation, best of `repeats`.

    The best run is used rather than the mean: timing noise is one-sided, since nothing makes
    a run faster than the machine can go, so the minimum is the most stable estimate.
    """
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        action(count)
        best = min(best, (time.perf_counter() - start) / count)
    return best


@pytest.fixture
def counted_introspection(monkeypatch):
    """Count calls to the type-hint introspection that dominates entity construction."""
    counts = {"get_origin": 0, "get_args": 0}
    for name in counts:
        original = getattr(serializable, name)

        def counting(hint, _name=name, _original=original):
            counts[_name] += 1
            return _original(hint)

        monkeypatch.setattr(serializable, name, counting)
    return counts


# --- ratios ------------------------------------------------------------------------------

class PlainReading:
    """The same four attributes, assigned by hand. The baseline MSB's validation is paid over."""
    __slots__ = ("name", "isactive", "value", "label")

    def __init__(self, name, value, label, isactive=True):
        self.name, self.value, self.label, self.isactive = name, value, label, isactive


def test_an_entity_costs_no_more_than_sixty_five_plain_objects():
    """Defends the construction path.

    Compared against a plain class rather than a dict literal, because both then allocate an
    object and set the same four attributes, and the ratio is exactly what validation costs.
    Measured at 44x on 2026-08-04: 13.1 us against 0.30. The budget carries about half again
    in headroom, so it fails on a real regression rather than on a slow runner. **Tighten it
    when P5 lands**, which is the item that should move this number.
    """
    def entities(count):
        for _ in range(count):
            Reading(name="r", value=1.0, label="x")

    def plain(count):
        for _ in range(count):
            PlainReading("r", 1.0, "x")

    ratio = per_operation(entities, 3000) / per_operation(plain, 3000)
    assert ratio < 65, f"entity construction is {ratio:.1f}x a plain object, budget 65x"


def test_a_cached_to_dict_is_much_cheaper_than_an_uncached_one():
    """Defends the cache. Without it the cache could stop working and nothing would notice."""
    cached = Readings(name="cached", use_cache=True)
    plain = Readings(name="plain")
    for index in range(200):
        for box in (cached, plain):
            box.add(Reading(name=f"r{index}", value=float(index), label="x"))

    cached.to_dict()                                  # warm it, so we measure hits
    hit = per_operation(lambda n: [cached.to_dict() for _ in range(n)], 200)
    miss = per_operation(lambda n: [plain.to_dict() for _ in range(n)], 200)
    assert hit < miss / 5, f"a cache hit is only {miss / hit:.1f}x cheaper than a miss"


# --- counts ------------------------------------------------------------------------------

def test_construction_introspects_a_bounded_number_of_times_per_object(counted_introspection):
    """Defends what P5 targets. Measured at 10 per object on 2026-08-04: five `get_origin`
    and five `get_args`, for an entity declaring two fields beyond `name` and `isactive`.

    A count is exact, so this catches a regression a timing assertion would miss entirely --
    an extra `get_args` per field costs little on one object and everything on a million.
    **P5 should drive this to nearly zero**, since a compiled per-class validator introspects
    once per class rather than once per instance.
    """
    for index in range(500):
        Reading(name=f"r{index}", value=1.0, label="x")

    total = sum(counted_introspection.values())
    per_object = total / 500
    assert per_object <= 12, f"{per_object:.1f} introspection calls per object, budget 12"


def test_resolving_a_field_type_is_cached_per_class(counted_introspection):
    """The second instance of a class must not re-derive what the first already resolved."""
    Nested(name="first", reading=Reading(name="r", value=1.0, label="x"), table={})
    after_first = sum(counted_introspection.values())

    for index in range(100):
        Nested(name=f"n{index}", reading=Reading(name="r", value=1.0, label="x"), table={})
    added = sum(counted_introspection.values()) - after_first

    assert added / 100 <= after_first, "resolution is being repeated per instance"


# --- scaling -----------------------------------------------------------------------------

def test_adding_items_to_a_container_stays_linear():
    """Defends against R3 returning: invalidation once walked every item, making add quadratic."""
    def adding(count):
        box = Readings(name="box")
        for index in range(count):
            box.add(Reading(name=f"r{index}", value=1.0, label="x"), copy_items=False)

    small = per_operation(adding, 500, repeats=3)
    large = per_operation(adding, 2000, repeats=3)
    assert large < small * 3, (
        f"per-item cost grew {large / small:.1f}x when the container grew 4x; "
        "adding is no longer linear"
    )


def test_serializing_a_container_stays_linear():
    def serializing(count):
        box = Readings(name="box")
        for index in range(count):
            box.add(Reading(name=f"r{index}", value=1.0, label="x"), copy_items=False)
        box.to_dict()

    small = per_operation(serializing, 500, repeats=3)
    large = per_operation(serializing, 2000, repeats=3)
    assert large < small * 3, f"per-item serialization grew {large / small:.1f}x"


def test_invalidation_does_not_grow_with_owners_that_do_not_cache():
    """Defends P6 once it lands, and records the cost until then.

    Invalidation climbs the ownership graph on every write. With 500 non-caching owners that
    walk reached nothing and still cost 277 us of 413 on 2026-08-04. The budget is loose
    because the skip is not built yet; tighten it with P6.
    """
    item = Reading(name="shared", value=1.0, label="x")
    owners = [Readings(name=f"box{index}") for index in range(200)]
    for owner in owners:
        owner.add(item, copy_items=False)

    lonely = Reading(name="lonely", value=1.0, label="x")
    shared = owners[0].get("shared")

    alone = per_operation(lambda n: [setattr(lonely, "value", 2.0) for _ in range(n)], 2000)
    crowded = per_operation(lambda n: [setattr(shared, "value", 2.0) for _ in range(n)], 2000)
    assert crowded < alone * 400, (
        f"a write with 200 owners costs {crowded / alone:.0f}x one with none"
    )
