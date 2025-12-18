# tests/performance/test_performance.py
import timeit
import pytest
from typing import Any
from src.msb_arch.base.baseentity import BaseEntity
from src.msb_arch.base.basecontainer import BaseContainer
from src.msb_arch.mega.manipulator import Manipulator
from src.msb_arch.super.super import Super


# Helper classes for testing
class TestEntity(BaseEntity):
    value: int
    data: list
    nested: Any


class TestContainer(BaseContainer[TestEntity]):
    pass


class TestSuper(Super):
    OPERATION = "test_op"

    def _test_op(self, obj, attributes):
        # Simple operation: return sum of values or something
        if hasattr(obj, 'value'):
            return obj.value
        elif hasattr(obj, 'get_items'):
            return sum(item.value for item in obj.get_items())
        return 0


# Performance tests using timeit
def test_baseentity_caching_performance():
    """Test performance of to_dict with and without caching for large structures."""
    # Create a large nested entity
    large_entity = TestEntity(name="large", value=1000, data=list(range(1000)), use_cache=True)
    nested = TestEntity(name="nested", value=500, data=list(range(500)), use_cache=True)
    large_entity.nested = nested

    # Without cache
    large_entity_no_cache = TestEntity(name="large", value=1000, data=list(range(1000)), use_cache=False)
    large_entity_no_cache.nested = TestEntity(name="nested", value=500, data=list(range(500)), use_cache=False)

    # Measure time for to_dict without cache
    time_no_cache = timeit.timeit(lambda: large_entity_no_cache.to_dict(), number=100)

    # Measure time for to_dict with cache (first call builds cache, second uses it)
    large_entity.to_dict()  # Build cache
    time_with_cache = timeit.timeit(lambda: large_entity.to_dict(), number=100)

    print(f"Time without cache: {time_no_cache:.4f}s")
    print(f"Time with cache: {time_with_cache:.4f}s")
    assert time_with_cache < time_no_cache, "Caching should improve performance"


def test_basecontainer_caching_performance():
    """Test performance of to_dict with and without caching for large containers."""
    # Create a large container
    container_cached = TestContainer(name="container", use_cache=True)
    container_no_cache = TestContainer(name="container", use_cache=False)

    for i in range(1000):
        entity = TestEntity(name=f"entity_{i}", value=i, data=list(range(10)))
        container_cached.add(entity)
        container_no_cache.add(entity.clone())

    # Measure without cache
    time_no_cache = timeit.timeit(lambda: container_no_cache.to_dict(), number=10)

    # Measure with cache
    container_cached.to_dict()  # Build cache
    time_with_cache = timeit.timeit(lambda: container_cached.to_dict(), number=10)

    print(f"Container time without cache: {time_no_cache:.4f}s")
    print(f"Container time with cache: {time_with_cache:.4f}s")
    assert time_with_cache < time_no_cache, "Caching should improve performance"


def test_manipulator_registry_performance():
    """Test performance of Manipulator registry with many operations."""
    manip = Manipulator()

    # Register many operations
    for i in range(100):
        super_inst = TestSuper()
        manip.register_operation(super_inst, operation=f"op_{i}")

    # Create a large container
    container = TestContainer(name="test")
    for i in range(1000):
        entity = TestEntity(name=f"entity_{i}", value=i, data=[])
        container.add(entity)

    # Measure time to process requests
    def process_op():
        result = manip.process_request({"operation": "op_50", "obj": container})
        return result

    time_taken = timeit.timeit(process_op, number=100)
    print(f"Manipulator registry time: {time_taken:.4f}s for 100 calls")
    assert time_taken < 10, "Should be reasonably fast"


def test_serialization_large_structures():
    """Test serialization performance for large structures."""
    # Create deeply nested structure
    root = TestContainer(name="root")
    for i in range(100):
        sub_container = TestContainer(name=f"sub_{i}")
        for j in range(10):
            entity = TestEntity(name=f"entity_{i}_{j}", value=i*10 + j, data=list(range(100)))
            sub_container.add(entity)
        root.add(sub_container)

    # Measure to_dict
    time_to_dict = timeit.timeit(lambda: root.to_dict(), number=5)
    print(f"Serialization time: {time_to_dict:.4f}s")

    # Measure from_dict
    data = root.to_dict()
    time_from_dict = timeit.timeit(lambda: TestContainer.from_dict(data), number=5)
    print(f"Deserialization time: {time_from_dict:.4f}s")

    assert time_to_dict < 5, "Serialization should be fast enough"
    assert time_from_dict < 5, "Deserialization should be fast enough"


def test_super_execute_performance():
    """Test performance of Super execute with large attributes."""
    super_inst = TestSuper()
    manip = Manipulator()
    manip.register_operation(super_inst, operation="test_op")

    # Large container
    container = TestContainer(name="large")
    for i in range(1000):
        entity = TestEntity(name=f"entity_{i}", value=i, data=list(range(50)))
        container.add(entity)

    # Measure execute
    def execute_op():
        result = super_inst.execute(container, attributes={})
        return result

    time_taken = timeit.timeit(execute_op, number=100)
    print(f"Super execute time: {time_taken:.4f}s for 100 calls")
    assert time_taken < 10, "Should be reasonably fast"