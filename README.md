# MSB — Mega-Super-Base

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-3.0.0-brightgreen.svg)](https://github.com/Torward1024/MSB)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](pyproject.toml)

**A domain layer for Python, with no dependencies.** The model, the rules it must obey and the
operations over it live in MSB, independent of any interface, storage or transport. Everything
reaches them through one entry point, by sending a request that is data:

```text
{"operation": "configure", "obj": part, "attributes": {"set": {"params": {"price": 4.5}}}}
```

A window, a command line, a test and an HTTP handler are then adapters that send the same
dictionary. Nothing in the domain knows which one did.

What that buys:

- **One domain, several faces.** The same rules and operations serve a GUI, a script and a remote
  caller, with no second copy of the logic in any of them.
- **Rules enforced where the data is.** Types, constraints on values, and invariants across fields
  and across a whole collection are checked when an object is built, when it is restored and after
  every write. A refused change is undone, not half-applied.
- **A session you can record and replay.** The journal keeps each request as data, with the
  object's address in the model rather than a reference to it, so the same session runs again
  against another project or in another process and lands on the objects it meant.
- **Answers derived from the code.** Which operations exist, what each handler needs and accepts,
  which type holds which, and what a change reaches are read back from the classes, so a menu, a
  command line or a diagram built on them cannot go stale.
- **Cross-cutting concerns kept out.** Metrics, auditing, authorisation and rate limiting hang on
  one hook that sees every request; the domain knows nothing about them.

In use behind [pAstroCORE](https://github.com/Torward1024/pAstroCORE), which plans radio astronomy
observations through a desktop interface and a command line over one model.

## Where MSB sits

In domain-driven design and ports-and-adapters terms:

| Concept | In MSB |
| --- | --- |
| Entities | `BaseEntity` — typed, validated fields; named within its owner, and addressable in the model |
| Rules on values | `Annotated[float, Positive()]`, `Range`, `Predicate` — enforced on build, write and restore |
| Aggregates and their consistency | `BaseContainer`, `Project` — an `@invariant` on the whole, checked after every change to what it holds, the change undone when refused |
| Domain services | `Super` — an operation with a handler per type, resolved through inheritance |
| The port | `Manipulator` — the single entry point every adapter talks to |
| Commands and queries | Requests as data. The built-in `configure` writes and stops at the first failure; `inspect` only reads -- `get`, `get_*`, `has_*`, `is_*` -- and reports every outcome |
| Adapters | Whatever sends a request — a GUI, a CLI, a test, an HTTP handler. None of them live in MSB |
| Cross-cutting concerns | Interceptors |
| Persistence | `save` and `load` — a replaceable JSON default, with schema versions and migrations |
| Command log | `RequestJournal` — every request as data, replayable against another model |

**Not provided, on purpose:** domain events, repositories and a unit of work, immutable value
objects, and event sourcing. The journal records requests, not domain events. Those belong to the
application, or to a library built for them. The reasoning is in [architecture](docs/architecture.md#in-domain-driven-design-terms).

## Plug it into anything

The domain never imports an adapter, so adapters are small and interchangeable:

| Put MSB behind | How |
| --- | --- |
| **HTTP** — FastAPI, Flask, Django | A view turns JSON into a request; objects travel as addresses and come back through `locate` |
| **A command line** | Flags built from the catalogue: a handler's parameters are derived from its code, so no list to keep in sync |
| **A GUI** | The same requests; forms and menus derived the same way |
| **SQL, a document store, an API** | Register your own `save` and `load`; the built-in JSON ones are defaults, not a law |

```text
@app.post("/request")
def handle(body: dict):
    target = service.locate(body["path"]) if body.get("path") else None
    return dict(service.process_request({"operation": body["operation"], "obj": target,
                                         "attributes": body.get("attributes", {})}))
```

That is a complete CRUD endpoint: create, read, update and delete are requests like any other, and
the invariants guard every one of them. Moving from JSON files to a database, or from a desktop tool
to a web service, replaces an adapter and leaves the domain and its tests untouched. Worked through
in [examples](docs/examples.md#one-domain-any-adapter).

## Features

- **Typed entities.** Attributes validated against their annotations, nested to any depth,
  including `List`, `Dict`, `Tuple`, `Set`, `Union`, `Literal`, `Callable` and `Type[X]`. A value
  written after the annotation is what the field starts as, and a declared list or dict belongs
  to the object rather than to the class.
- **Constraints on values, not just types.** `price: Annotated[float, Positive()]` is enforced on
  construction, on assignment and on restore, with no `__init__` of your own.
- **Rules about the whole object.** `@invariant("end must be after start")` guards what no
  per-field rule can — the relation between several. Checked at the same three points, and a
  refused change is undone rather than half-applied.
- **Containers for collections.** Named, queryable, serializable, with bulk operations.
- **One entry point.** A `Manipulator` registers operations and processes requests; a facade per
  operation means you rarely write a request dictionary by hand.
- **Reading and writing come free.** `inspect`, `configure`, `save`, `load` and `catalogue` are
  registered for you, so an application that only reads and writes its model needs no operation
  layer at all.
- **Operations that write themselves.** A handler is usually one call to `_apply_methods`, which
  applies everything a request names and reports each outcome.
- **Pipelines.** Several requests that feed each other, given as data in one call. The order,
  what may run at once, and what to skip when a step fails all follow from the edges.
- **Serialization that round-trips.** `json.loads(json.dumps(obj.to_dict()))` restores an equal
  object, through lists, dicts, sets and tuples, nested to any depth. Cycles are detected rather
  than followed, and data carries the schema version of the class that wrote it.
- **Derived answers instead of hand-written ones.** What operations exist, what handlers they
  have, which handler needs which, which type holds which, and what a change reaches — all read
  back from the code, so a menu or a diagram cannot go stale.
- **One place to hang metrics, auditing, rate limiting and authorisation.** An interceptor sees a
  request before it runs and its response after, and may refuse or rewrite it. Request metrics
  and a replayable journal ship using nothing more than that hook.
- **A session that replays somewhere else.** The journal records each request as plain data, with
  the object's address in the model rather than a reference to it, so `json.dumps(journal.entries)`
  on one side and `manipulator.replay(json.loads(...))` on the other run the same session against
  another project, in another process -- landing on the objects it meant. `address` and `locate`
  are the same addressing on its own, for a request that has to cross a wire.
- **Asynchronous when you need it.** `await manipulator.ainspect(...)` moves the work off the
  event loop, and every synchronous signature is untouched.
- **Exceptions you can catch precisely.** Everything derives from `MSBError`, and also from the
  built-in it replaces, so `except TypeError` keeps working while `except DuplicateNameError`
  becomes possible.
- **No external dependencies.** Python >= 3.12 and nothing else.

## Installation

```bash
pip install msb_arch
```

## Quick start

Describe the data, describe the operations, drive both through the orchestrator.

```python
from msb_arch import BaseContainer, BaseEntity, Manipulator

# 1. the data
class Part(BaseEntity):
    price: float

    def get_price(self) -> float:
        return self.price

    def set_price(self, value: float) -> bool:
        self.price = value
        return True

class Parts(BaseContainer[Part]):
    pass

# 2. the entry point
class Workshop(Manipulator):
    pass

manipulator = Workshop(base_classes=[Part, Parts])

box = Parts(name="box")
box.add(Part(name="bolt", price=4.5))
bolt = box.get("bolt")

assert manipulator.inspect(bolt, get_price=None) == 4.5
manipulator.configure(bolt, set_price=5.0)
assert manipulator.inspect(bolt, get_price=None) == 5.0

assert box.to_dict()["items"]["bolt"]["price"] == 5.0
```

There is no operation layer to write: `inspect` and `configure` follow from the request model
itself. You write a `Super` when an operation carries logic of your own:

```python
from msb_arch import Super

class Pricing(Super):
    OPERATION = "price"

    def _price_parts(self, obj, attributes):
        return sum(part.price for part in obj.get_items())

manipulator.register_operation(Pricing(manipulator))
assert manipulator.price(box) == 5.0
```

A handler is short because `_apply_methods` owns the loop, and the orchestrator dispatches by
operation and by the type of the object, so adding an entity adds no code at all.

Ask for several things at once and every outcome comes back:

```python
answer = manipulator.inspect(bolt, get_price=None, get=["name", "isactive"])
assert answer["get_price"]["result"] == 5.0
assert answer["get"]["result"] == {"name": "bolt", "isactive": True}
```

Run several requests as one batch:

```python
manipulator.batch([
    {"operation": "configure", "obj": bolt, "attributes": {"set_price": 6.0}},
    {"operation": "inspect", "obj": bolt, "attributes": {"get_price": None}},
])
assert bolt.price == 6.0
```

Or as a pipeline, when the steps feed each other:

```python
outcome = manipulator.pipeline({
    "written": {"operation": "save", "obj": box, "path": "box.json"},
    "read":    {"operation": "load", "obj": box, "path": "box.json", "after": ["written"]},
    "total":   {"operation": "price", "obj": "@read"},
})
assert outcome.output == 6.0
```

## Architecture

Three layers, plus what they share.

| Layer | Module | What lives there |
| --- | --- | --- |
| **Base** — the data | [`serializable.py`](src/msb_arch/base/serializable.py), [`baseentity.py`](src/msb_arch/base/baseentity.py), [`basecontainer.py`](src/msb_arch/base/basecontainer.py) | Validation, serialization, caching, ownership |
| **Super** — the operations | [`super.py`](src/msb_arch/super/super.py), [`builtins.py`](src/msb_arch/super/builtins.py), [`project.py`](src/msb_arch/super/project.py) | Handlers, method resolution, the built-in operations |
| **Mega** — the entry point | [`manipulator.py`](src/msb_arch/mega/manipulator.py) | Operation registry, request processing, facades, batches, pipelines |
| Derivation | [`catalogue.py`](src/msb_arch/catalogue.py), [`model.py`](src/msb_arch/model.py), [`scaffold.py`](src/msb_arch/scaffold.py) | What is registered, what holds what, generated stubs |
| Shared | [`interceptors.py`](src/msb_arch/interceptors.py), [`results.py`](src/msb_arch/results.py), [`utils/`](src/msb_arch/utils) | Metrics and journal, result types, logging, validation |

Main classes:

- **`Serializable`** — what an entity and a container have in common: annotated fields and their
  validation, `name` and `isactive`, `to_dict`, the cache, `revision` and `fingerprint`.
- **`BaseEntity`** — an object addressed by its attributes.
- **`BaseContainer[T]`** — a named collection addressed by its items. A sibling of `BaseEntity`,
  not a subclass: the two mean different things by `get`, `set` and `clear`.
- **`Super`** — an operation. Subclass it, name the operation, and write handlers as
  `_<operation>_<type>`, or `_<operation>` for the fallback.
- **`Project`** — a named collection of entities with a factory for creating them: the thing an
  application saves as a whole. A `Serializable` like the other two, addressed by its items.
- **`Manipulator`** — the entry point. Registers operations, processes requests and pipelines,
  and answers what it knows about itself and the model.
- **`MethodResults`** — what an operation reports: every method it ran, mapped to its outcome.

## Documentation

- [**Guide**](docs/guide.md) — **start here**: a working application, built from nothing
- [API reference](docs/api.md) — every public class and method
- [Compatibility](docs/COMPATIBILITY.md) — what will not break, and how anything changes
- [Architecture](docs/architecture.md) and [diagrams](docs/diagrams.md)
- [Base module](docs/modules/base.md) — the data model, type hints, serialization, caching
- [Super module](docs/modules/super.md) — writing your own operation
- [Mega module](docs/modules/mega.md) — requests, pipelines, interceptors, the async surface
- [Examples](docs/examples.md)
- [Roadmap](docs/ROADMAP.md) — what is open, and what was decided against
- [Changelog](CHANGELOG.md) — release history and upgrade notes

## Testing

Unit, integration, performance and concurrency suites, run with pytest.

The tests import `msb_arch` rather than the source tree, so they exercise whatever is installed.
Install the package first:

```bash
pip install -e .
```

Then run them:

```bash
pytest tests/
```

CI builds the wheel, installs it, checks that `msb_arch` resolves inside `site-packages`, and
runs the same suites against it, so the distribution that ships is the one that was tested.

## Projects using MSB

- [pAstroCORE](https://github.com/Torward1024/pAstroCORE) — radio astronomy observation planning.

## License

[Apache License 2.0](LICENSE). Use it for anything, including commercially, in open or closed
source: keep the licence and the [NOTICE](NOTICE) with the code, state what you changed, and the
patent grant protects you as long as you do not sue over it.

Releases up to and including 1.10.0 went out under the earlier MSB Software License and stay under
it; 2.0.0 and later are Apache-2.0.

Available for collaboration, contract work and support — [almax1024@gmail.com](mailto:almax1024@gmail.com).

## Contacts

- **Author**: Alexey Rudnitskiy
- **Email**: [almax1024@gmail.com](mailto:almax1024@gmail.com)
- **Repository**: [https://github.com/Torward1024/MSB](https://github.com/Torward1024/MSB)
- **Version**: 3.0.0
