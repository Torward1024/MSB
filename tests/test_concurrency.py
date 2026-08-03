"""Concurrency tests for the state MSB keeps outside a single object.

Scope: the structures the framework shares between objects -- the class registry, the
resolved type caches, the handler cache, the generated container types. Mutating one
entity from two threads is not covered and is not promised: that is the caller's
responsibility, exactly as for any plain Python object.

Two kinds of test live here, and they are not equally strong:

- `TestProjectContainerTypeUnderThreads` and `TestHandlerCacheUnderThreads` reproduce real
  defects: run against the unguarded code they fail on every attempt. Sixteen threads
  building the first project of a type generate up to fifteen competing container classes
  instead of one, which silently reintroduces the bug where two projects hold containers
  that compare unequal; and the handler cache loses entries or exceeds its size when a
  lookup interleaves with an eviction.
- The rest exercise shared structures concurrently and assert their invariants. They do not
  fail on unguarded code today, because under CPython the individual dictionary operations
  they guard are effectively atomic. They exist to catch a future change that opens a wider
  window, and to record what is expected to hold.

The fixture below shortens the interpreter's thread switch interval for the duration of a
test. Without it none of these fail even on unguarded code -- which is worth remembering:
a concurrency test that passes proves nothing until it has been seen to fail.
"""
import sys
import threading

import pytest

from msb_arch import BaseContainer, BaseEntity, Manipulator, Project, Super
from msb_arch.base.serializable import EntityMeta


THREADS = 16
ROUNDS = 60


@pytest.fixture(autouse=True)
def eager_thread_switching():
    """Make the interpreter switch threads aggressively for the duration of a test."""
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-9)
    yield
    sys.setswitchinterval(previous)


def run_in_threads(worker, threads=THREADS):
    """Run `worker(index)` on several threads, starting together, and re-raise failures."""
    failures = []
    barrier = threading.Barrier(threads)

    def target(index):
        try:
            barrier.wait()
            worker(index)
        except Exception as exc:                      # noqa: BLE001 - reported below
            failures.append(exc)

    workers = [threading.Thread(target=target, args=(i,)) for i in range(threads)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()
    if failures:
        raise failures[0]


class ConcurrentEntity(BaseEntity):
    value: int
    label: str


class ConcurrentBox(BaseContainer[ConcurrentEntity]):
    pass


class TestProjectContainerTypeUnderThreads:
    """Reproduces a real race: competing generated classes for one item type."""

    def test_one_container_class_per_item_type(self):
        class SharedProject(Project):
            _item_type = ConcurrentEntity

            def create_item(self, item_code="ITEM", isactive=True):
                self.add_item(ConcurrentEntity(name=item_code, value=1, label="x"))

        generated = set()
        for attempt in range(10):
            # Drop the cached class so every attempt races on creating the first one.
            Project._container_types.pop(ConcurrentEntity, None)
            seen = []
            guard = threading.Lock()

            def worker(index):
                project = SharedProject(name=f"p{index}")
                with guard:
                    seen.append(type(project._items))

            run_in_threads(worker)
            assert len(set(seen)) == 1, (
                f"attempt {attempt}: {len(set(seen))} competing container classes"
            )
            generated.update(seen)

        assert len(generated) == 10, "each attempt should produce exactly one class"

    def test_projects_built_concurrently_hold_comparable_containers(self):
        class ComparableProject(Project):
            _item_type = ConcurrentEntity

            def create_item(self, item_code="ITEM", isactive=True):
                self.add_item(ConcurrentEntity(name=item_code, value=1, label="x"))

        Project._container_types.pop(ConcurrentEntity, None)
        projects = []
        guard = threading.Lock()

        def worker(index):
            project = ComparableProject(name="SameName")
            project.create_item("item1")
            with guard:
                projects.append(project)

        run_in_threads(worker)
        first = projects[0]._items
        assert all(other._items == first for other in projects[1:])


class TestClassRegistryUnderThreads:
    def test_declaring_classes_while_reading_the_registry(self):
        def worker(index):
            for round_ in range(ROUNDS):
                if index % 2:
                    type(f"Declared{index}_{round_}", (BaseEntity,),
                         {"__annotations__": {"v": int}})
                else:
                    EntityMeta.registered_classes("ConcurrentEntity")

        run_in_threads(worker)
        assert ConcurrentEntity in EntityMeta.registered_classes("ConcurrentEntity")

    def test_resolving_a_name_while_classes_appear(self):
        def worker(index):
            for round_ in range(ROUNDS):
                type(f"Noise{index}_{round_}", (BaseEntity,), {"__annotations__": {"v": int}})
                assert ConcurrentEntity._resolve_entity_type("ConcurrentEntity") is ConcurrentEntity

        run_in_threads(worker)


class TestTypeCacheUnderThreads:
    def test_resolving_types_concurrently(self):
        def worker(index):
            for _ in range(ROUNDS):
                assert ConcurrentEntity._resolve_type(int) is int
                assert ConcurrentEntity._resolve_type(str) is str

        run_in_threads(worker)

    def test_constructing_and_validating_concurrently(self):
        def worker(index):
            for round_ in range(ROUNDS):
                entity = ConcurrentEntity(name=f"e{index}_{round_}", value=round_, label="x")
                assert entity.to_dict()["value"] == round_

        run_in_threads(worker)


class TestSerializationUnderThreads:
    def test_traversal_state_is_per_thread(self):
        # The seen-set lives in a context variable; two serializations running at once must
        # not see each other's marks and mistake a live object for a cyclic reference.
        boxes = []
        for index in range(THREADS):
            box = ConcurrentBox(name=f"box{index}")
            for item in range(10):
                box.add(ConcurrentEntity(name=f"item{item}", value=item, label="x"))
            boxes.append(box)

        def worker(index):
            for _ in range(ROUNDS):
                data = boxes[index].to_dict()
                assert len(data["items"]) == 10
                assert all(isinstance(value, dict) for value in data["items"].values()), \
                    "a live object was marked as a cyclic reference"

        run_in_threads(worker)


class TestHandlerCacheUnderThreads:
    def test_dispatch_from_several_threads(self):
        class Counting(Super):
            OPERATION = "count"

            def _count(self, obj, attributes):
                return "default"

            def _count_str(self, obj, attributes):
                return "for str"

            def _count_list(self, obj, attributes):
                return "for list"

        handler = Counting(cache_size=4)
        targets = ["text", [1], {"a": 1}, 3, (1,), 3.5, set(), b"bytes"]

        def worker(index):
            for round_ in range(ROUNDS):
                target = targets[(index + round_) % len(targets)]
                assert handler.execute(target, {})["status"] is True

        run_in_threads(worker)
        assert len(handler._method_cache) <= 4

    def test_eviction_does_not_race_with_lookup(self):
        class Tiny(Super):
            OPERATION = "tiny"

            def _tiny(self, obj, attributes):
                return True

        handler = Tiny(cache_size=2)

        def worker(index):
            for round_ in range(ROUNDS):
                assert handler.execute("obj", {}, method=f"name{index}_{round_}")["status"] is True

        run_in_threads(worker)
        assert len(handler._method_cache) <= 2


class TestManipulatorUnderThreads:
    def test_processing_requests_concurrently(self):
        class Reader(Super):
            OPERATION = "read"

            def _read(self, obj, attributes):
                return obj.name

        class Manip(Manipulator):
            pass

        manipulator = Manip()
        manipulator.register_operation(Reader(), operation="read")
        entity = ConcurrentEntity(name="shared", value=1, label="x")

        def worker(index):
            for _ in range(ROUNDS):
                out = manipulator.process_request({"operation": "read", "obj": entity})
                assert out["status"] is True
                assert out["result"] == "shared"

        run_in_threads(worker)
