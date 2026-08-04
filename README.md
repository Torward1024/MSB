# MSB Architecture

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MSB%20Software%20License-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.5.0-orange.svg)](https://github.com/Torward1024/MSB)

Mega-Super-Base (MSB) is an architecture for Python applications built around a single entry
point. You describe your data as typed entities, you describe what may be done to them as
operations, and everything reaches both through one orchestrator — a user, a GUI, another
API, whatever drives the application.

A request is data, not a call:

```text
{"operation": "configure", "obj": telescope, "attributes": {"set_diameter": 64.0}}
```

which is what lets the same code serve a dialog box, a script and a remote caller, and what
lets a session be logged and replayed.

## Features

- **Typed entities**: attributes validated against their annotations, nested to any depth,
  including `List`, `Dict`, `Tuple`, `Set`, `Union`, `Literal`, `Callable` and `Type[X]`.
- **Constraints on values, not just types**: `price: Annotated[float, Positive()]` is enforced
  on construction, on assignment and on restore, with no `__init__` of your own.
- **Containers for collections**: named, queryable, serializable, with bulk operations.
- **One entry point**: a `Manipulator` registers operations and processes requests; the
  per-operation facades are sugar so you rarely write a request dictionary by hand.
- **Operations that write themselves**: a handler is usually one call to `_apply_methods`,
  which applies everything a request names and reports each outcome.
- **Serialization that round-trips**: `json.loads(json.dumps(obj.to_dict()))` restores an
  equal object, through lists, dicts, sets and tuples, for entities nested to any depth.
  Cycles are detected rather than followed, and serialized data carries the version of the
  class that wrote it, so a model can change shape and still read its old files.
- **Logging that behaves**: a dedicated `msb_arch` logger that stays silent until the
  application configures it.
- **Exceptions you can catch precisely**: everything derives from `MSBError`, and also from
  the built-in it replaces, so `except TypeError` keeps working while `except
  DuplicateNameError` becomes possible.
- **No external dependencies**: Python >= 3.12 and nothing else.

## Installation

```bash
pip install msb_arch
```

## Quick Start

Describe the data, describe the operations, drive both through the orchestrator.

```python
from msb_arch import BaseContainer, BaseEntity, Manipulator, Super

# 1. the data
class Telescope(BaseEntity):
    diameter: float

    def get_diameter(self) -> float:
        return self.diameter

    def set_diameter(self, value: float) -> bool:
        self.diameter = value
        return True

class Telescopes(BaseContainer[Telescope]):
    pass

# 2. the operations
class Inspector(Super):
    OPERATION = "inspect"

    def _inspect(self, obj, attributes):
        return self._apply_methods(obj, attributes)

class Configurator(Super):
    OPERATION = "configure"

    def _configure(self, obj, attributes):
        return self._apply_methods(obj, attributes)

# 3. the entry point
class Observatory(Manipulator):
    pass

manipulator = Observatory(base_classes=[Telescope, Telescopes])
manipulator.register_operation(Inspector(manipulator))
manipulator.register_operation(Configurator(manipulator))

dishes = Telescopes(name="array")
dishes.add(Telescope(name="DSS14", diameter=70.0))
dish = dishes.get("DSS14")

manipulator.inspect(dish, get_diameter=None)      # 70.0
manipulator.configure(dish, set_diameter=64.0)
manipulator.inspect(dish, get_diameter=None)      # 64.0

dishes.to_dict()["items"]["DSS14"]["diameter"]    # 64.0
```

Two handlers of one line each serve every type: the orchestrator dispatches by operation and
by the type of the object, so adding an entity adds no code to the operation layer.

Ask for several things at once and every outcome comes back, whatever the order:

```python
manipulator.inspect(dish, get_diameter=None, get=["name", "isactive"])
# {'get_diameter': {'status': True, 'result': 64.0},
#  'get':          {'status': True, 'result': {'name': 'DSS14', 'isactive': True}}}
```

Run several requests as one batch:

```python
manipulator.batch([
    {"operation": "configure", "obj": dish, "attributes": {"set_diameter": 70.0}},
    {"operation": "inspect", "obj": dish, "attributes": {"get_diameter": None}},
])
```

## Architecture

Four modules, three layers.

| Layer | Module | What lives there |
| --- | --- | --- |
| **Base** — the data | [`serializable.py`](src/msb_arch/base/serializable.py), [`baseentity.py`](src/msb_arch/base/baseentity.py), [`basecontainer.py`](src/msb_arch/base/basecontainer.py) | Validation, serialization, caching, ownership |
| **Super** — the operations | [`super.py`](src/msb_arch/super/super.py), [`project.py`](src/msb_arch/super/project.py) | Handlers, method resolution, projects |
| **Mega** — the entry point | [`manipulator.py`](src/msb_arch/mega/manipulator.py) | Operation registry, request processing, facades, batches |
| Shared | [`results.py`](src/msb_arch/results.py), [`utils/`](src/msb_arch/utils) | Result types, logging, validation helpers |

Main classes:

- **`Serializable`** — what an entity and a container have in common: annotated fields and
  their validation, `name` and `isactive`, `to_dict`, the cache. Use it in `isinstance`
  checks that should accept either.
- **`BaseEntity`** — an object addressed by its attributes.
- **`BaseContainer[T]`** — a named collection addressed by its items. A sibling of
  `BaseEntity`, not a subclass: an entity and a container mean different things by `get`,
  `set` and `clear`.
- **`Super`** — an operation. Subclass it, name the operation, and write handlers as
  `_<operation>_<type>` or `_<operation>` for the fallback.
- **`Project`** — a named collection of entities with a factory for creating them.
- **`Manipulator`** — the entry point. Registers operations, processes requests, generates a
  facade per operation.
- **`MethodResults`** — what an operation reports: every method it ran, mapped to its
  outcome.

## Documentation

- [API reference](docs/api.md) — every public class and method
- [Architecture](docs/architecture.md) and [diagrams](docs/diagrams.md)
- [Base module](docs/modules/base.md) — the data model, the supported type hints, thread safety
- [Super module](docs/modules/super.md) — **writing your own operation**
- [Examples](docs/examples.md)
- [Roadmap](docs/ROADMAP.md) — what is open, what is planned, and what 1.0.0 should mean
- [Changelog](CHANGELOG.md) — release history and upgrade notes

## Testing

Unit, integration, performance and concurrency suites, run with pytest.

The tests import `msb_arch` rather than the source tree, so they exercise whatever is
installed. Install the package first:

```bash
pip install -e .
```

Then run them:

```bash
pytest tests/
```

CI builds the wheel, installs it, checks that `msb_arch` resolves inside `site-packages`,
and runs the same suites against it — so the distribution that ships is the one that was
tested.

## License

MSB is licensed under the [MSB Software License](LICENSE) for non-commercial and research use, allowing free use, modification, and distribution for non-commercial purposes with attribution.

For commercial use, a separate royalty-bearing license is required. Please contact [almax1024@gmail.com](mailto:almax1024@gmail.com) for details.

## Contacts

- **Author**: Alexey Rudnitskiy
- **Email**: [almax1024@gmail.com](mailto:almax1024@gmail.com)
- **Repository**: [https://github.com/Torward1024/MSB](https://github.com/Torward1024/MSB)
- **Version**: 0.5.0
