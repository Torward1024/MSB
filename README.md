# MSB Architecture

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MSB%20Software%20License-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.3.0-brightgreen.svg)](https://github.com/Torward1024/MSB)

Mega-Super-Base (MSB) is an architecture for Python applications built around a single entry
point. You describe your data as typed entities, you describe what may be done to them as
operations, and everything reaches both through one orchestrator — a script, a window, a
command line, a server.

A request is data, not a call:

```text
{"operation": "configure", "obj": part, "attributes": {"set": {"params": {"price": 4.5}}}}
```

That is what lets the same code serve a dialog, a script and a remote caller, and what lets a
session be logged and replayed.

## Features

- **Typed entities.** Attributes validated against their annotations, nested to any depth,
  including `List`, `Dict`, `Tuple`, `Set`, `Union`, `Literal`, `Callable` and `Type[X]`.
- **Constraints on values, not just types.** `price: Annotated[float, Positive()]` is enforced on
  construction, on assignment and on restore, with no `__init__` of your own.
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
- **`Project`** — a named collection of entities with a factory for creating them.
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

MSB is licensed under the [MSB Software License](LICENSE) for non-commercial and research use,
allowing free use, modification, and distribution for non-commercial purposes with attribution.

For commercial use, a separate royalty-bearing license is required. Please contact
[almax1024@gmail.com](mailto:almax1024@gmail.com) for details.

## Contacts

- **Author**: Alexey Rudnitskiy
- **Email**: [almax1024@gmail.com](mailto:almax1024@gmail.com)
- **Repository**: [https://github.com/Torward1024/MSB](https://github.com/Torward1024/MSB)
- **Version**: 1.3.0
