# Mega Module

The Mega module provides the `Manipulator` class, which serves as the central orchestration component of the MSB Framework. It manages operations, processes requests, and coordinates interactions between objects and Super classes.

## Abstract Manipulator Class

`Manipulator` is an abstract class for managing and processing operations on objects. It acts as a registry for operations and provides a unified interface for executing complex workflows.

### Key Features

- **Operation Registry**: Register and manage multiple operation handlers
- **Request Processing**: Handle single and batch requests with detailed error handling
- **Method Discovery**: Automatic method registry generation for base classes
- **Facade Methods**: Dynamic facade method creation for simplified operation calls
- **Caching**: LRU caching for method resolution and serialization
- **Type Safety**: Optional strict type checking for objects

### Basic Usage

```python
from msb_arch.mega import Manipulator
from msb_arch.super import Super

class MathOperations(Super):
    OPERATION = "math"

    def _math_add(self, obj, attributes):
        return attributes.get("a", 0) + attributes.get("b", 0)

    def _math_multiply(self, obj, attributes):
        return attributes.get("a", 1) * attributes.get("b", 1)

# Create manipulator
manipulator = Manipulator()

# Register operation
manipulator.register_operation(MathOperations())

# Process requests
result = manipulator.process_request({
    "operation": "math",
    "obj": int,
    "attributes": {"method": "add", "a": 5, "b": 3}
})

print(result)
# {"status": True, "object": None, "method": "_math_add", "result": 8}

# Use facade method (created automatically)
result = manipulator.math(int, a=10, b=4, method="multiply")
print(result)  # 40
```

### Advanced Features

#### Managing Objects

```python
# Set a central managing object
from msb_arch.base import BaseContainer, BaseEntity

class Item(BaseEntity):
    name: str
    value: int

class ItemsContainer(BaseContainer[Item]):
    pass

container = ItemsContainer(name="items")
manipulator.set_managing_object(container)

# Now operations can work on the managing object implicitly
result = manipulator.process_request({
    "operation": "math",
    "attributes": {"method": "add", "a": 1, "b": 2}
})
```

#### Batch Processing

```python
# Process multiple requests
requests = {
    "req1": {
        "operation": "math",
        "attributes": {"method": "add", "a": 1, "b": 2}
    },
    "req2": {
        "operation": "math",
        "attributes": {"method": "multiply", "a": 3, "b": 4}
    }
}

results = manipulator.process_request(requests)
print(results["req1"]["result"])  # 3
print(results["req2"]["result"])  # 12
```

#### Base Class Registration

```python
# Register base classes for method discovery
manipulator = Manipulator(base_classes=[list, dict, str])

# Now methods from these classes are available
result = manipulator.process_request({
    "obj": [1, 2, 3],
    "operation": "custom_operation",  # Assuming operation that uses list methods
    "attributes": {"method": "append", "value": 4}
})
```

### Operation Registration

#### Automatic Registration

```python
class DataProcessor(Super):
    OPERATION = "process"  # Auto-register with this name

processor = DataProcessor()
manipulator.register_operation(processor)  # Uses "process" as operation name
```

#### Manual Registration

```python
manipulator.register_operation(processor, operation="data_process")
```

#### Multiple Operations

```python
from msb_arch import BaseEntity, Manipulator, Super

class Reading(BaseEntity):
    value: float

class Calculator(Super):
    OPERATION = "calculate"

    def _calculate_reading(self, obj, attributes):
        return obj.value * attributes.get("factor", 1.0)

class Formatter(Super):
    OPERATION = "format"

    def _format_reading(self, obj, attributes):
        return f"{obj.name}: {obj.value:.2f}"

class Pipeline(Manipulator):
    pass

manipulator = Pipeline(base_classes=[Reading])
manipulator.register_operation(Calculator(manipulator))
manipulator.register_operation(Formatter(manipulator))

reading = Reading(name="sensor-1", value=21.5)
manipulator.calculate(reading, factor=2.0)   # 43.0
manipulator.format(reading)                  # 'sensor-1: 21.50'
```

### Request Processing

#### Single Request Format

```text
request = {
    "operation": "operation_name",    # Required
    "obj": object_to_process,         # Optional (uses managing object if None)
    "method": "specific_method",      # Optional
    "attributes": {                   # Optional
        "param1": "value1",
        "param2": "value2"
    }
}

result = manipulator.process_request(request)
```

#### Batch Request Format

```text
requests = {
    "request_id_1": { /* single request */ },
    "request_id_2": { /* single request */ }
}

results = manipulator.process_request(requests)
# Returns: {"request_id_1": result1, "request_id_2": result2}
```

### Facade Methods

When you register an operation, Manipulator automatically creates a facade method with the same name:

```python
manipulator.register_operation(MathOperations(), operation="math")

# This creates manipulator.math() method
result = manipulator.math(int, a=1, b=2, method="add")
# Equivalent to:
result = manipulator.process_request({
    "operation": "math",
    "obj": int,
    "attributes": {"a": 1, "b": 2, "method": "add"}
})
```

Facade methods support these parameters:
- `obj`: Object to operate on (optional)
- `method`: Specific method to call (optional)
- `raise_on_error`: If True, raises exceptions; if False, returns dict (default: True)
- Any other keyword arguments become attributes

### Method Registry

Manipulator maintains a registry of available methods for different object types:

```python
# the methods registered for a type the manipulator knows about
methods = manipulator.get_methods_for_type(Reading)
sorted(methods)[:3]                 # ['activate', 'clear', 'clone']

# teach it about further types
manipulator.update_registry(additional_classes=[list])
sorted(manipulator.get_methods_for_type(list))[:3]   # ['append', 'clear', 'copy']
```

### Configuration Options

#### Strict Type Checking

```python
manipulator = Manipulator(strict_type_check=True)
# Will raise errors for unsupported object types
```

#### Cache Size

```python
# In Super classes
super_instance = MathOperations(cache_size=500)  # Default is 2048
```

### Error Handling

Manipulator provides comprehensive error handling:

```python
class Inspector(Super):
    OPERATION = "inspect"

    def _inspect(self, obj, attributes):
        return self._apply_methods(obj, attributes)

manipulator.register_operation(Inspector(manipulator))

# raise_on_error is True by default: a failure is raised
try:
    manipulator.inspect(reading, no_such_method=None)
except Exception as e:
    print(f"raised: {e}")            # Method 'no_such_method' not found

# with raise_on_error=False the whole response comes back instead
response = manipulator.inspect(reading, no_such_method=None, raise_on_error=False)
if not response["status"]:
    print(response["error"])         # Method 'no_such_method' not found
```

Common error scenarios:
- **Operation not registered**: `ValueError`
- **Invalid request format**: `TypeError`
- **Method not found**: `ValueError`
- **Type validation errors**: `TypeError`

### Performance Optimization

#### Caching

- Method resolution results are cached using `lru_cache`
- Super instances can have configurable cache sizes
- Registry updates clear relevant caches

#### Best Practices

1. **Batch Operations**: Use batch requests for multiple operations to reduce overhead.

2. **Facade Methods**: Use facade methods for simple operations instead of full request dictionaries.

3. **Managing Object**: Set a managing object when most operations work on the same object.

4. **Operation Naming**: Use consistent, descriptive operation names.

5. **Error Handling**: Use `raise_on_error=False` for programmatic error handling.

## Built-in operations

A `Manipulator` answers `inspect` and `configure` without being told. They follow from the
request model rather than from any domain -- an attribute names a method, and the method reads
or writes -- so an application that only reads and writes its model needs no `Super` at all.

```python
from msb_arch import BaseEntity, Manipulator

class Telescope(BaseEntity):
    diameter: float

    def get_diameter(self) -> float:
        return self.diameter

    def set_diameter(self, value: float) -> bool:
        self.diameter = value
        return True

class Observatory(Manipulator):
    pass

manipulator = Observatory(base_classes=[Telescope])
dish = Telescope(name="DSS14", diameter=70.0)

manipulator.configure(dish, set_diameter=64.0)
assert manipulator.inspect(dish, get_diameter=None) == 64.0
```

They differ in one thing. `Inspector` applies every method a request names and reports each
outcome; `Configurator` stops at the first failure. A caller reading several things wants the
whole picture, while a half-applied configuration is worse than a rejected one.

### Reaching one member of a collection

A request against a collection means one of two things, and only the request can say which:

```python
class Telescopes(BaseContainer[Telescope]):
    pass

array = Telescopes(name="array")
array.add(Telescope(name="DSS14", diameter=70.0))
manipulator.update_registry(additional_classes=[Telescopes])

assert list(manipulator.inspect(array, get_all=None)) == ["DSS14"]      # ask the collection
assert manipulator.inspect(array, name="DSS14", get_diameter=None) == 70.0   # ask one member
```

The key is removed before descending, so the member sees only the methods meant for it.

**The descent is not uniform**, which is why it is a hook rather than a convention: a
`BaseContainer` answers `get(name)`, a `Project` answers `get_observation(name)`, and a model
of your own answers however it likes. Two things say how:

```python
from msb_arch import Inspector

class RegistryInspector(Inspector):
    NESTED_KEY = "entry"                    # what a request calls the member

    def _nested_getter(self, obj):          # how to fetch it
        getter = getattr(obj, "get_entry", None)
        return getter or super()._nested_getter(obj)

assert RegistryInspector.NESTED_KEY == "entry"
```

Anything holding no members is unaffected: the hook returns `None` and the request is applied
to the object itself.

**Registering your own replaces a built-in silently.** That is how every application written
before they existed is already spelled, and it has to keep meaning the same thing. Two
registrations of one name that are both yours still raise. Pass `builtins=False` to start with
nothing registered.

## The asynchronous surface

Every facade has an `a`-prefixed twin, and so do `process_request` and `batch`. The synchronous
API is untouched.

```python
import asyncio

async def main():
    await manipulator.aconfigure(dish, set_diameter=64.0)
    return await manipulator.ainspect(dish, get_diameter=None)

assert asyncio.run(main()) == 64.0
```

**Why it is not simply `async def` on the entry point.** Awaiting does not create concurrency;
it marks a point where control *may* be yielded, and a synchronous handler has none. Measured
against a heartbeat task during one 0.5-second operation:

| | the loop ran |
| --- | --- |
| a plain synchronous call | **0 times** |
| an `async def` entry point over a synchronous handler | **0 times** |
| the work moved onto an executor | **19 times** |

So the work moves off the loop. The whole synchronous pipeline runs on an executor the
framework owns — interceptors included, which is what lets one interceptor serve both paths
unchanged. The consequence is that an interceptor runs on a worker thread here and cannot await
inside it.

Threads rather than processes: the numerical libraries this was written for release the GIL, so
a thread is real parallelism there, and a process would have to pickle the model to reach the
work.

### Methods that are themselves coroutines

An entity may declare one, and the asynchronous surface awaits it back on the loop:

```python
class Dish(BaseEntity):
    async def fetch_status(self) -> str:
        await asyncio.sleep(0)
        return "online"

remote = Observatory(base_classes=[Dish])
assert asyncio.run(remote.ainspect(Dish(name="d"), fetch_status=None)) == "online"
remote.close()
```

### The executor

Created on first asynchronous use and never before, so an application that stays synchronous
never starts a thread. Size it with `Manipulator(max_workers=...)`.

It is the one resource MSB owns, so it is the one thing to shut down:

```python
manipulator.close()

# or let a context manager do it
with Observatory(base_classes=[Telescope]) as orchestrator:
    assert asyncio.run(orchestrator.ainspect(dish, get_diameter=None)) == 64.0
```

`close()` is safe when nothing was started and safe to call twice, and the orchestrator stays
usable afterwards: the next asynchronous call starts a new executor.

## Interceptors

Something that sees a request before it runs and its response after. Metrics, auditing, rate
limiting and authorisation are four uses of this one hook, which is why MSB supplies the hook
and none of the four: a library that chose a metrics backend would stop being dependency-free,
and one that chose an authorisation model would be wrong about somebody's.

```python
import time

def timing(request, call_next):
    started = time.perf_counter()
    response = call_next(request)
    print(request["operation"], time.perf_counter() - started)
    return response

manipulator.add_interceptor(timing)
```

An interceptor may pass the request on, do something either side of that, **refuse** by
returning a response without calling `call_next` -- which is what rate limiting and
authorisation need -- or **rewrite** the request before passing it on. The first added is the
outermost. Each entry of a batch is intercepted separately, because a batch is a container of
requests rather than a request.

With none registered, a request pays one check.

### What ships

Both are ordinary interceptors with no privileged access, and neither is registered by default.

```python
from msb_arch import RequestJournal, RequestMetrics

metrics = RequestMetrics()
journal = RequestJournal()
manipulator.add_interceptor(metrics)
manipulator.add_interceptor(journal)

manipulator.configure(dish, set_diameter=12.0)

metrics.snapshot()["configure"]["calls"]      # 1
journal.touching("DSS14")                     # everything that touched this object
```

`RequestMetrics` counts, times and records failures per operation. `snapshot()` gives a plain
mapping to export wherever you like -- Prometheus, statsd, a log line, a status page.

`RequestJournal` records what ran. Read backwards it answers *what produced this*; read
forwards, `replay(manipulator)` runs the session again. It is nearly free here only because a
request is data rather than a call, and a response already reports every method that ran.

Two limits worth knowing. Entries hold the live object the request named, which is what makes
replay exact and what stops a journal from being written to a file as it stands. And replay
assumes handlers are deterministic: one that reads the clock, a file or a random seed cannot be
reconstructed from its request alone.

For the size of the serialization cache, `cache_statistics()` reports it on demand. Counters
for how often invalidation runs, or how long serialization takes, are deliberately not
maintained: both would put an unconditional increment into paths measured in microseconds, to
answer a question most applications never ask.

## Integration Patterns

### With Base Classes

```python
from msb_arch import BaseContainer

class Readings(BaseContainer[Reading]):
    pass

class Recorder(Super):
    OPERATION = "record"

    def _record_readings(self, obj, attributes):
        obj.add(Reading(name=attributes["name"], value=attributes["value"]))
        return len(obj)

recorder = Pipeline(base_classes=[Reading, Readings])
recorder.register_operation(Recorder(recorder))

series = Readings(name="series")
recorder.record(series, name="sensor-2", value=19.0)   # 1
```

### With Projects

```python
from msb_arch import Project

class ReadingProject(Project):
    _item_type = Reading

    def create_item(self, item_code="R", isactive=True):
        self.add_item(Reading(name=item_code, value=0.0, isactive=isactive))

managed = Pipeline(base_classes=[Reading])
managed.register_operation(Inspector(managed), operation="inspect")

project = ReadingProject(name="observations")
project.create_item("R1")

# with a managing object set, obj may be omitted from a request
managed.set_managing_object(project)
managed.inspect(get_name=None)      # 'observations'
```

## Response Format

All Manipulator operations return standardized responses:

```text
{
    "status": bool,        # Operation success status
    "object": Any,         # Object identifier/name
    "method": str,         # Executed method name
    "result": Any,         # Operation result (if status=True)
    "error": str           # Error message (if status=False)
}
```

For batch operations, returns a dictionary mapping request IDs to response objects.