# MSB documentation

MSB (Mega-Super-Base) is a domain layer for Python with no dependencies: the model, the rules it
must obey and the operations over it, independent of any interface, storage or transport. Every
adapter — a window, a command line, a test, a server — reaches it through one entry point by
sending a request that is data rather than a call.

How that maps onto domain-driven design and ports-and-adapters is set out in
[architecture](architecture.md#in-domain-driven-design-terms).

**New here? Start with the [guide](guide.md).** It builds a working application from nothing,
and every block in it runs.

## The pages

| | |
| --- | --- |
| [Guide](guide.md) | A working application, built from nothing |
| [Base module](modules/base.md) | Entities, containers, type hints, serialization, caching |
| [Super module](modules/super.md) | Writing an operation; the five built-ins; projects |
| [Mega module](modules/mega.md) | Requests, batches, pipelines, interceptors, the async surface |
| [Utils module](modules/utils.md) | Logging and the validation helpers |
| [Examples](examples.md) | Worked examples, longer than the guide's |
| [Architecture](architecture.md) | How the layers fit, and why |
| [Diagrams](diagrams.md) | The same, drawn |
| [API reference](api.md) | Every public class and method |
| [Compatibility](COMPATIBILITY.md) | What will not break, and how anything changes |
| [Roadmap](ROADMAP.md) | What is open, and what was decided against |
| [Changelog](../CHANGELOG.md) | Release history and upgrade notes |

## Installation

```bash
pip install msb-arch
```

Python 3.12 or later. No external dependencies.

## The shortest possible example

```python
from msb_arch import BaseContainer, BaseEntity, Manipulator

class Part(BaseEntity):
    price: float

class Parts(BaseContainer[Part]):
    pass

class Workshop(Manipulator):
    pass

workshop = Workshop(base_classes=[Part, Parts])
box = Parts(name="box")
box.add(Part(name="bolt", price=4.5))

assert workshop.inspect(box, name="bolt", get="price") == 4.5
workshop.configure(box.get("bolt"), set={"params": {"price": 5.0}})
assert box.get("bolt").price == 5.0
```

Nothing was written to make that work: `inspect` and `configure` follow from the request model,
so the framework supplies them, along with `save`, `load` and `catalogue`.

## What the layers are

| Layer | Holds |
| --- | --- |
| **Base** | The data: `Serializable`, `BaseEntity`, `BaseContainer[T]` |
| **Super** | The operations: `Super` and its handlers, the built-ins, `Project` |
| **Mega** | The entry point: `Manipulator` -- registry, requests, batches, pipelines |

Around them: interceptors, the derivation of what is registered and what the model holds, the
error taxonomy, logging and the validation helpers.

## Version

2.0.2

## License

[Apache License 2.0](../LICENSE). Releases up to 1.10.0 went out under the earlier MSB Software License and stay under it.
