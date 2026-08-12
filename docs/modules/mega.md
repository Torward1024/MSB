# Mega module

The `Manipulator`: the entry point. It holds the registered operations, knows which methods may
be applied to which type, turns requests into responses, and answers questions about itself and
about the model.

Everything in this page runs; the test suite executes it top to bottom.

```python
from msb_arch import BaseContainer, BaseEntity, Manipulator, Super

class Reading(BaseEntity):
    value: float

    def get_value(self) -> float:
        return self.value

    def set_value(self, value: float) -> bool:
        self.value = value
        return True

class Readings(BaseContainer[Reading]):
    pass

class Bench(Manipulator):
    pass

bench = Bench(base_classes=[Reading, Readings])
reading = Reading(name="r1", value=19.0)
```

## The request

A request is data:

```text
{
    "operation": str,          # which registered operation
    "obj": Any,                # what to run it on; None means the managing object
    "method": str,             # optional: a specific handler
    "attributes": {...},       # what the operation is given
}
```

A response is data too:

```text
{
    "status": bool,
    "object": Any,             # the object's name
    "method": str | None,      # the handler that ran
    "result": Any,
    "error": str,              # only when status is False
    "error_type": str,         # only when status is False
}
```

```python
response = bench.process_request({
    "operation": "inspect",
    "obj": reading,
    "attributes": {"get_value": None},
})
assert response["status"] is True
assert response["result"]["get_value"]["result"] == 19.0
```

### Facades

Registering an operation adds a method of the same name, and an `a`-prefixed twin. It is the
same request, written shorter, and it unwraps the common case of one method named.

```python
assert bench.inspect(reading, get_value=None) == 19.0
```

| Argument | Meaning |
| --- | --- |
| `obj` | What to run it on. Omitted or None means the managing object |
| `method` | A specific handler |
| `raise_on_error` | True by default. False returns the whole response instead of raising |
| `**attributes` | The rest of the request |

### The managing object

Set one, and a request may leave `obj` out.

```python
bench.set_managing_object(reading)
assert bench.inspect(get_value=None) == 19.0
bench.set_managing_object(None)
```

### Registering operations

```python
class Statistics(Super):
    OPERATION = "stats"

    def _stats_readings(self, obj, attributes):
        values = [item.value for item in obj.get_items()]
        return {"count": len(values), "mean": sum(values) / len(values) if values else 0.0}

bench.register_operation(Statistics(bench))

series = Readings(name="series")
series.add(reading)
series.add(Reading(name="r2", value=21.0))
assert bench.stats(series)["mean"] == 20.0
```

An operation registered under a name a built-in already uses replaces the built-in silently.
Two registrations of one name that are both yours raise `RegistrationError`, and so does a name
that would shadow a method of the `Manipulator` itself.

### Registering one that is expensive to build

Registering an operation costs whatever its module costs to import. For one reached from a menu
-- a plot, a report -- that is paid on every start whether or not anyone opens the menu.

```python
class Plotting(Super):
    OPERATION = "plot"

    def _plot_reading(self, obj, attributes):
        return f"a chart of {obj.name}"

def make_plotting():
    # The expensive import goes here, so it happens when the operation is first needed.
    return Plotting(bench)

bench.register_deferred("plot", make_plotting)
assert "plot" in bench.get_supported_operations()     # registered from this moment
```

The factory is called once, by whatever needs the operation first: a request, a pipeline step, or
a question about what it offers -- `describe_operations` reads its handlers, and a dialog building
a menu from the catalogue must not be told an operation has none.

```python
assert bench.plot(reading) == "a chart of r1"         # built here
```

`warm()` builds everything still deferred, for an application that would rather pay in the
background than at the first click:

```python
import threading
threading.Thread(target=bench.warm, daemon=True).start()
```

Anything asking meanwhile waits on the same lock rather than building a second instance.

### Teaching it about more types

```python
class Note(BaseEntity):
    text: str

    def get_text(self) -> str:
        return self.text

bench.update_registry(additional_classes=[Note])
assert bench.inspect(Note(name="n", text="hello"), get_text=None) == "hello"
```

`get_methods_for_type(Note)` returns what a request may name for that type.

## Several requests at once

### batch

Independent requests, each answered separately. Give a sequence or a mapping keyed by name.

```python
responses = bench.batch([
    {"operation": "configure", "obj": reading, "attributes": {"set_value": 25.0}},
    {"operation": "inspect", "obj": reading, "attributes": {"get_value": None}},
])
assert responses["1"]["result"]["get_value"]["result"] == 25.0
```

`raise_on_error=True` stops at the first failure; the default reports all of them.

### pipeline

Requests that feed each other. Same convention: one call, taking data.

```python
outcome = bench.pipeline({
    "raised":  {"operation": "configure", "obj": reading, "set_value": 30.0},
    "summary": {"operation": "stats", "obj": series, "after": ["raised"]},
})
assert outcome.output["count"] == 2
```

A step is a request with three additions:

| | |
| --- | --- |
| `"@name"` | What the step called `name` produced. Works anywhere in the step |
| `"after": [...]` | Wait for a step without using its value |
| Any other key | An attribute, so the common case needs no nested `attributes` |

What a pipeline adds over a batch: the order the edges imply, substitution of what a step
produced, and skipping the branch below a failure.

```python
answer = bench.pipeline({
    "measured": {"operation": "inspect", "obj": reading, "get_value": None},
    "copied":   {"operation": "configure", "obj": Reading(name="r3", value=0.0),
                 "set_value": "@measured"},
})
assert answer.failed == []
```

`PipelineRun` is the response of every step, keyed as the plan keyed them, plus `output` (what
the last step produced), `of(name)` and `failed`.

Steps that wait for nothing may run together: `bench.pipeline(plan, concurrent=True)`, or
`await bench.apipeline(plan)` from inside an event loop.

Drafting a plan by calling the operations, when the mapping is a nuisance to type:

```python
draft = bench.pipeline()
draft.inspect(reading, get_value=None)
assert draft.plan()["inspect"]["obj"] is reading
assert draft.run().failed == []
```

The draft produces a plan and hands it to `pipeline`; it runs nothing itself.

## The built-in operations

| Operation | Handler | What it does |
| --- | --- | --- |
| `inspect` | `_inspect` | Applies the methods a request names, reporting every outcome |
| `configure` | `_configure` | The same, stopping at the first failure |
| `catalogue` | `_catalogue`, `_catalogue_order`, `_catalogue_model` | What is registered, and the shape of the model |
| `save` | `_save` | Writes an object to a file as JSON, atomically |
| `load` | `_load` | Reads one back |

`Manipulator(builtins=False)` starts with none of them.

```python
bench.save(series, path="series.json")
restored = bench.load(series, path="series.json")
assert restored == series
```

`save` takes `path`, and optionally `indent` (4) and `overwrite` (True). `load` takes `path`,
and optionally `kind` -- a class or its name -- for reading something no instance exists of.

The write goes to a temporary file beside the target and is renamed, so an interrupted write
leaves the previous file rather than a truncated one. The format is a default: register your own
`save` and it takes over.

### Reaching one member of a collection

A request against a container means one of two things, and only the request says which.

```python
assert sorted(bench.inspect(series, get_all=None)) == ["r1", "r2"]   # the container
assert bench.inspect(series, name="r2", get_value=None) == 21.0      # one member
```

The key is `NESTED_KEY`, `"name"` by default. How to fetch a member is `_nested_getter`, which a
`BaseContainer` answers with `get`; override it for a type that answers differently.

## What the orchestrator knows

Derived from what is registered and from the annotations, so nothing here can go stale.

```python
described = bench.describe_operations("catalogue")
assert sorted(described["catalogue"]) == ["model", "order"]
assert described["catalogue"]["model"]["label"] == "Model"
```

Handlers are found by reading the source of the class, so the operations shown here are the
built-in ones: a class defined inside a documentation example has no source file to read.

`describe_operations()` reports, per operation, each handler with:

| Key | Meaning |
| --- | --- |
| `requires` | Other handlers of the same operation that this one calls. Exact, direct |
| `calls` | Every name it reaches. An upper bound: a shared helper is followed for each caller |
| `touches` | What the `interpret` callback made of those names. Empty without one |
| `label` | A display name, with `acronyms` for words that keep their capitals |

`order_handlers(operation, names)` sorts handlers so each follows what it needs;
`requirements_of(operation, name)` is the transitive walk.

The model graph comes from the annotations:

```python
model = bench.describe_model()
assert model["Readings"]["holds"]["items"] == ["Reading"]
assert model["Reading"]["held_by"] == {"Readings": ["items"]}
assert bench.dependents_of("Reading") == ["Readings"]
```

And the handlers a new operation over that model would need:

```python
source = bench.scaffold("audit")
assert "def _audit_reading(" in source
assert "def _audit_readings(" in source
```

Containers get a working walk over their items; entities get a stub that raises.

## The asynchronous surface

Every facade has an `a`-prefixed twin that runs the work on an executor the framework owns, so
an event loop stays responsive.

```python
import asyncio

async def main():
    await bench.aconfigure(reading, set_value=12.0)
    return await bench.ainspect(reading, get_value=None)

assert asyncio.run(main()) == 12.0
```

`aprocess_request`, `abatch` and `apipeline` are the same for the other three entry points. The
whole synchronous pipeline runs on the executor, interceptors included, so one interceptor
serves both paths -- and cannot await inside.

The hop onto the executor costs about 170 µs. It pays for work longer than that.

A handler that is itself a coroutine is awaited rather than run on the executor:

```python
class Probe(BaseEntity):
    async def fetch_status(self) -> str:
        await asyncio.sleep(0)
        return "ready"

remote = Bench(base_classes=[Probe])
assert asyncio.run(remote.ainspect(Probe(name="p"), fetch_status=None)) == "ready"
```

The executor is created on first asynchronous use and never before. `close()` shuts it down, or
use the manipulator as a context manager:

```python
with Bench(base_classes=[Reading]) as orchestrator:
    assert asyncio.run(orchestrator.ainspect(reading, get_value=None)) == 12.0
```

## Interceptors

Something that sees a request before it runs and its response after. Metrics, auditing, rate
limiting and authorisation are four uses of this one hook, which is why MSB supplies the hook and
none of the four.

```python
import time

def timing(request, call_next):
    started = time.perf_counter()
    response = call_next(request)
    del started
    return response

bench.add_interceptor(timing)
```

An interceptor may pass the request on, do something either side of that, **refuse** by returning
a response without calling `call_next`, or **rewrite** the request before passing it on. The
first added is the outermost. Each entry of a batch is intercepted separately. With none
registered, a request pays one check.

### What ships

```python
from msb_arch import RequestJournal, RequestMetrics

bench.remove_interceptor(timing)
bench.add_interceptor(RequestMetrics())
bench.add_interceptor(RequestJournal(fingerprints=True))

bench.configure(reading, set_value=15.0)
bench.inspect(reading, get_value=None)

assert bench.metrics()["configure"]["calls"] == 1
assert len(bench.history("r1")) == 2
assert [entry["operation"] for entry in bench.history(changed_only=True)] == ["configure"]
```

`RequestMetrics` counts, times and records failures per operation. `snapshot()` gives a plain
mapping to export wherever you like; `manipulator.metrics()` returns the same thing.

`RequestJournal` records what ran. `manipulator.history(name, changed_only)` reads it,
`manipulator.replay(journal)` runs the session again by turning it into a plan and passing it to
`pipeline`.

```python
journal = bench.journal()
bench.remove_interceptor(journal)          # or the replay records itself
assert bench.replay(journal).failed == []
```

With `fingerprints=True` the journal hashes the object either side of each request, so it can
report which requests actually changed something. It costs a serialisation each way.

Two limits: entries hold the live object the request named, which is what makes replay exact and
what stops a journal from being written to a file as it stands; and replay assumes deterministic
handlers.

## Errors

A facade raises the kind of failure that happened, with the operation's own error types
preserved across the response boundary.

```python
from msb_arch import errors

try:
    bench.load(reading, path="absent.json")
except errors.NotFoundError:
    pass
```

The traceback does not survive, because a response carries no exception object. Ask for the
response instead of the exception when you would rather read it:

```python
response = bench.configure(reading, no_such_method=None, raise_on_error=False)
assert response["status"] is False
assert response["error_type"] == "HandlerError"
```

`inspect` would report `status: True` here with the failure recorded against that one method:
reading is where a caller usually wants every outcome, writing is where a half-applied change is
worse than a refused one.

## With a Project

```python
from msb_arch import Project

class ReadingProject(Project):
    _item_type = Reading

    def create_item(self, item_code="R", isactive=True):
        self.add_item(Reading(name=item_code, value=0.0, isactive=isactive))

managed = Bench(base_classes=[Reading])
project = ReadingProject(name="series")
project.create_item("R1")

managed.set_managing_object(project)
assert managed.inspect(get_name=None) == "series"
```
