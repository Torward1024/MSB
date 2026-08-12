# Building an application on MSB

A working application, built from nothing, in the order you would build it. Every block here
runs: the test suite executes this page top to bottom on every commit.

The idea: **you describe your data as typed entities, and everything that drives the application
— a window, a script, a remote caller — reaches it through one orchestrator, by sending a request
that is data rather than a call.** What follows is what that buys.

## 1. Describe the data

An entity is a class with annotations. The annotations are the schema: they are validated,
serialized, restored, and read back by anything that needs to know the shape of your model.

```python
from msb_arch import BaseEntity

class Part(BaseEntity):
    price: float
    material: str

bolt = Part(name="bolt", price=4.5, material="steel")
assert bolt.price == 4.5
assert bolt.isactive is True
```

Every entity has a `name` — containers key their items by it — and an `isactive` flag. A wrong
type is refused at the door:

```python
# raises: TypeValidationError
Part(name="bad", price="cheap", material="steel")
```

## 2. Constrain the values, not only the types

A `float` that must be positive is not a `float`. Say so on the annotation and the model enforces
it: on construction, on assignment, and when restoring from a file.

```python
from typing import Annotated
from msb_arch import ConstraintError, NonEmpty, Positive

class Priced(BaseEntity):
    price: Annotated[float, Positive()]
    material: Annotated[str, NonEmpty()]

try:
    Priced(name="broken", price=-5.0, material="steel")
except ConstraintError as error:
    assert "must be positive" in str(error)
```

The rules that ship: `Positive`, `NonNegative`, `NonZero`, `NonEmpty`, `Range(low, high)` and
`Predicate(test, description)` for anything else.

## 3. Collect them

A container is a named, typed collection. It is not an entity: an entity addresses its
attributes, a container addresses its items.

```python
from msb_arch import BaseContainer

class Parts(BaseContainer[Part]):
    pass

box = Parts(name="box")
box.add(bolt)
box.add(Part(name="nut", price=1.5, material="brass"))

assert len(box) == 2
assert box["bolt"].price == 4.5
assert [part.name for part in box.get_by_value({"material": "brass"})] == ["nut"]
```

## 4. Drive it

Give the model methods and hand the types to an orchestrator. Reading and writing come with the
framework, so there is nothing else to write yet.

```python
from msb_arch import Manipulator

class Widget(BaseEntity):
    price: float

    def get_price(self) -> float:
        return self.price

    def set_price(self, value: float) -> bool:
        self.price = value
        return True

class Widgets(BaseContainer[Widget]):
    pass

class Workshop(Manipulator):
    pass

workshop = Workshop(base_classes=[Widget, Widgets])
widget = Widget(name="hinge", price=7.0)

assert workshop.inspect(widget, get_price=None) == 7.0
workshop.configure(widget, set_price=6.0)
assert widget.price == 6.0
```

`inspect` and `configure` follow from the request model itself — an attribute names a method, and
the method reads or writes — so they serve every type you ever add.

Ask for several things at once and every outcome comes back:

```python
answer = workshop.inspect(widget, get_price=None, get=["name", "isactive"])
assert answer["get_price"]["result"] == 6.0
assert answer["get"]["result"]["name"] == "hinge"
```

## 5. Add an operation of your own

Write a `Super` when an operation carries logic of your own. The handler is usually one line,
because `_apply_methods` owns the loop.

```python
from msb_arch import Super

class Widget(BaseEntity):            # extended with something worth computing
    price: float
    quantity: int

    def get_price(self) -> float:
        return self.price

    def set_price(self, value: float) -> bool:
        self.price = value
        return True

    def line_total(self) -> float:
        return self.price * self.quantity

class Costing(Super):
    OPERATION = "cost"

    def _cost(self, obj, attributes):
        return self._apply_methods(obj, attributes)

workshop = Workshop(base_classes=[Widget])
workshop.register_operation(Costing(workshop))

widget = Widget(name="hinge", price=6.0, quantity=4)
assert workshop.cost(widget, line_total=None) == 24.0
```

Dispatch is by operation *and* by type, so `_cost_widget` would be reached for widgets and
`_cost` for everything else. Adding a new entity adds no code here.

## 6. Send requests as data

A facade is sugar. Underneath, a request is a dictionary, which is why the same code can serve a
window, a script and a remote caller, and why a session can be recorded and replayed.

```python
response = workshop.process_request({
    "operation": "cost",
    "obj": widget,
    "attributes": {"line_total": None},
})
assert response["status"] is True
assert response["result"]["line_total"]["result"] == 24.0
```

Several independent requests at once:

```python
responses = workshop.batch([
    {"operation": "cost", "obj": widget, "attributes": {"line_total": None}},
    {"operation": "cost", "obj": widget, "attributes": {"get_price": None}},
])
assert len(responses) == 2
```

## 7. Chain requests that feed each other

When one request needs what another produced, that is a pipeline: still one call, still data.
`"@name"` means what the step called `name` produced.

```python
outcome = workshop.pipeline({
    "cheaper": {"operation": "configure", "obj": widget, "set_price": 5.0},
    "total":   {"operation": "cost", "obj": widget, "line_total": None,
                "after": ["cheaper"]},
})
assert outcome.output == 20.0
assert outcome.failed == []
```

`after` waits for a step without using its value. Steps that wait for nothing may run at the same
time: `workshop.pipeline(plan, concurrent=True)`, or `await workshop.apipeline(plan)` from inside
an event loop.

If typing the mapping is a nuisance, draft it by calling the operations. The draft only produces
a plan; the manipulator still runs it.

```python
draft = workshop.pipeline()
priced = draft.cost(widget, line_total=None)
draft.inspect(widget, get="price")

assert draft.plan()["cost"]["operation"] == "cost"
assert draft.run().failed == []
```

## 8. Save and load

`save` and `load` are registered for you: JSON over `to_dict`, written atomically. The format is
a default — register your own `save` to replace it.

```python
class Kit(BaseContainer[Widget]):
    pass

kit = Kit(name="kit")
kit.add(widget)

workshop.update_registry(additional_classes=[Kit])
workshop.save(kit, path="kit.json")
restored = workshop.load(kit, path="kit.json")

assert restored.get("hinge").price == 5.0
assert restored == kit
```

Underneath, `to_dict` produces plain data — entities nested to any depth, sets and tuples
included — and `from_dict` restores the declared types from the annotations.

```python
import json

text = json.dumps(kit.to_dict())
assert Kit.from_dict(json.loads(text)) == kit
```

When a model changes shape, say how to read the old one:

```python
class Tool(BaseEntity):
    SCHEMA_VERSION = 2
    price: float                 # this was 'cost' in version 1

    @classmethod
    def migrate(cls, data, from_version):
        if from_version == 1:
            data["price"] = data.pop("cost")
        return data

old = {"name": "t", "isactive": True, "type": "Tool", "schema_version": 1, "cost": 25.0}
assert Tool.from_dict(old).price == 25.0
```

## 9. Watch what happens

One hook sees every request before it runs and its response after. Metrics, auditing, rate
limiting and authorisation are all this hook, which is why MSB provides it and none of them.

```python
from msb_arch import RequestJournal, RequestMetrics

workshop.add_interceptor(RequestMetrics())
workshop.add_interceptor(RequestJournal())

workshop.inspect(widget, get_price=None)
workshop.inspect(widget, get="name")

assert workshop.metrics()["inspect"]["calls"] == 2
assert len(workshop.history("hinge")) == 2
```

The journal reads both ways: backwards it says what happened to an object, forwards it replays
the session.

```python
journal = workshop.journal()
workshop.remove_interceptor(journal)          # or the replay records itself
assert len(workshop.replay(journal)) == 2
```

Two cheaper questions about change, when a whole journal is more than you need:

```python
before = widget.revision, widget.fingerprint()
widget.price = 5.0                             # the same value it already held

assert widget.revision != before[0]            # it was written to
assert widget.fingerprint() == before[1]       # but the content did not change
```

## 10. Ask what the application can do

The orchestrator answers from what is registered, so a menu, a form or a diagram built from these
cannot go out of date.

```python
described = workshop.describe_operations("cost")
assert "cost" in described

model = workshop.describe_model()
assert model["Kit"]["holds"]["items"] == ["Widget"]
assert workshop.dependents_of("Widget") == ["Kit"]
```

And it can write the handlers a new operation would need over that model:

```python
source = workshop.scaffold("measure")
assert "def _measure_widget(" in source
```

## 11. Keep the interface responsive

Long work belongs off the event loop. Every facade has an `a`-prefixed twin, and the synchronous
ones are unchanged.

```python
import asyncio

async def main():
    return await workshop.acost(widget, line_total=None)

assert asyncio.run(main()) == 20.0
workshop.close()                               # shuts the executor down
```

The hop onto the executor costs about 170 µs, so it pays for work that takes longer than that,
not for a single attribute read.

## 12. Handle what goes wrong

Every exception derives from `MSBError`, and also from the built-in it replaces, so you can be as
broad or as narrow as you like.

```python
from msb_arch import MSBError, ValidationError

try:
    Priced(name="bad", price=-1.0, material="steel")
except ValidationError:
    pass                # anything the caller got wrong
except MSBError:
    pass                # anything from the framework
```

A facade raises the kind of failure that happened — `NotFoundError` for a missing file,
`SerializationError` for a corrupt one. Ask for the response instead when you would rather read
it than catch it:

```python
response = workshop.cost(widget, no_such_method=None, raise_on_error=False)
assert response["status"] is False
```

## Where to go next

| | |
| --- | --- |
| The data model, type hints, caching, serialization | [Base module](modules/base.md) |
| Writing your own operation | [Super module](modules/super.md) |
| Requests, pipelines, interceptors, the async surface | [Mega module](modules/mega.md) |
| Every class and method | [API reference](api.md) |
| What will not break, and how anything changes | [Compatibility](COMPATIBILITY.md) |
| What is planned | [Roadmap](ROADMAP.md) |
