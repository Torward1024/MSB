"""Benchmarks that fail a build when performance regresses.

Wall-clock thresholds do not work for this. A CI runner is between two and ten times slower
than a developer machine and varies run to run, so a threshold loose enough not to be flaky
is loose enough to hide a tenfold regression -- which is what the older assertions in
`test_performance.py` do.

Three kinds of assertion here, in decreasing order of how much they can be trusted:

- **Counts.** How many times a hot path is entered is not a measurement at all, it is
  arithmetic. It cannot flake, and it is exactly what the cost of entity construction turned
  out to be about. Where a property can be expressed as a count, it is expressed as a count.
- **Scaling.** Cost at 2n against cost at n catches an accidental quadratic, which is the
  regression that has actually happened here before (R3, adding 4000 items took 1.4 s). The
  ratio between two sizes is far more stable than either measurement.
- **Ratios against a baseline.** A ratio cancels how fast the machine is. It does **not**
  cancel how much the machine varies, which is a separate thing and was learned the hard way:
  a budget set from a single sample of 17x failed CI at 32.9x, on the same commit that had
  passed minutes earlier. Sampling both sides in one pass and taking the median of the
  per-pass ratios brought the observed spread from 19x down to 6x; the remaining budget
  carries honest headroom over that, so it catches a gross regression and nothing finer.

Budgets say what they defend and what was measured when they were set. Where a number here
looks loose, it is because a tighter one would fail on noise, and the exact count beside it is
the assertion doing the real work.
"""
import statistics
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


def paired_ratio(first, second, count=3000, repeats=9):
    """How much dearer `first` is than `second`, as the median of per-pass ratios.

    Both sides are timed inside one pass, so a slow moment on the machine lands on both and
    largely cancels. Timing each side separately and dividing the two minima does the
    opposite: it pairs the unluckiest run of one with the luckiest of the other, which is what
    produced a spread of 19x where this produces 6x.
    """
    ratios = []
    for _ in range(repeats):
        start = time.perf_counter()
        first(count)
        elapsed_first = time.perf_counter() - start

        start = time.perf_counter()
        second(count)
        ratios.append(elapsed_first / (time.perf_counter() - start))
    return statistics.median(ratios)


def test_an_entity_costs_no_more_than_forty_five_plain_objects():
    """Defends the construction path against a gross regression.

    Compared against a plain class rather than a dict literal, because both then allocate an
    object and assign the same four attributes, so the ratio is what validation costs.
    Measured at 44x before P5. After it, this machine reports between 22x and 29x depending on
    the pass, and a CI runner reported 33x, so the budget sits above all of them.

    It is deliberately loose. What actually defends P5 is
    `test_construction_introspects_a_bounded_number_of_times_per_object`, which counts rather
    than times and therefore cannot flake; this catches the slowdown that a count would miss.
    """
    def entities(count):
        for _ in range(count):
            Reading(name="r", value=1.0, label="x")

    def plain(count):
        for _ in range(count):
            PlainReading("r", 1.0, "x")

    ratio = paired_ratio(entities, plain)
    assert ratio < 45, f"entity construction is {ratio:.1f}x a plain object, budget 45x"


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
    """Defends P5. It was ten per object -- five `get_origin` and five `get_args` for an
    entity declaring two fields -- and is now none: a validator is compiled once per class,
    so resolution happens per annotation rather than per instance.

    A count is exact, so this catches a regression a timing assertion would miss entirely --
    an extra `get_args` per field costs little on one object and everything on a million. The
    budget of 2 leaves room for the first instance of a class to compile its table.
    """
    for index in range(500):
        Reading(name=f"r{index}", value=1.0, label="x")

    total = sum(counted_introspection.values())
    per_object = total / 500
    assert per_object <= 2, f"{per_object:.1f} introspection calls per object, budget 2"


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
    """Defends P6.

    Invalidation climbs the ownership graph on every write, and with nothing caching that
    walk reached nothing: 413 us at 500 owners against 3.3 with none. It now stops before
    climbing, leaving only a pass over the direct owners to drop dead ones, and costs 39 us
    at 500. The budget is set from that with headroom, and would fail if the walk returned.
    """
    item = Reading(name="shared", value=1.0, label="x")
    owners = [Readings(name=f"box{index}") for index in range(200)]
    for owner in owners:
        owner.add(item, copy_items=False)

    lonely = Reading(name="lonely", value=1.0, label="x")
    shared = owners[0].get("shared")

    ratio = paired_ratio(
        lambda n: [setattr(shared, "value", 2.0) for _ in range(n)],
        lambda n: [setattr(lonely, "value", 2.0) for _ in range(n)],
        count=2000,
    )
    assert ratio < 25, (
        f"a write with 200 owners costs {ratio:.1f}x one with none, budget 25x"
    )
