# Building an application on MSB

A working application, built from nothing, in the order you would actually build it. Every
block here runs; the test suite executes this page top to bottom on every commit.

The idea is small enough to state once. **You describe your data as typed entities, and
everything that drives the application — a dialog box, a script, a remote caller — reaches it
through one orchestrator, by sending a request that is data rather than a call.** What follows
is what that buys.

## 1. Describe the data

An entity is a class with annotations. The annotations are the schema: they are validated,
serialized, restored, and later read by anything that wants to know the shape of your model.

```python
from msb_arch import BaseEntity

class Telescope(BaseEntity):
    diameter: float
    band: str

dish = Telescope(name="DSS14", diameter=70.0, band="X")
assert dish.diameter == 70.0
assert dish.isactive is True
```

Every entity has a `name` — containers key their items by it — and an `isactive` flag. A wrong
type is refused at the door:

```python
from msb_arch import TypeValidationError

try:
    Telescope(name="bad", diameter="seventy", band="X")
except TypeValidationError as error:
    print(error)        # Attribute 'diameter' must be of type <class 'float'>, got <class 'str'>
```

## 2. Constrain the values, not only the types

A `float` that must be positive is not a `float`. Say so on the annotation and the model
enforces it — on construction, on assignment, and when restoring from a file:

```python
from typing import Annotated
from msb_arch import ConstraintError, NonEmpty, Positive

class Dish(BaseEntity):
    diameter: Annotated[float, Positive()]
    band: Annotated[str, NonEmpty()]

try:
    Dish(name="broken", diameter=-5.0, band="X")
except ConstraintError as error:
    print(error)        # Attribute 'diameter' must be positive, got -5.0
```

## 3. Collect them

A container is a named, typed collection. It is not an entity and does not pretend to be: an
entity addresses its attributes, a container addresses its items.

```python
from msb_arch import BaseContainer

class Telescopes(BaseContainer[Telescope]):
    pass

array = Telescopes(name="array")
array.add(dish)
array.add(Telescope(name="DSS43", diameter=64.0, band="S"))

assert len(array) == 2
assert array["DSS14"].diameter == 70.0
assert [t.name for t in array.get_by_value({"band": "S"})] == ["DSS43"]
```

## 4. Drive it

Give the model methods, and hand the types to an orchestrator. Reading and writing come with
the framework, so there is nothing else to write yet.

```python
from msb_arch import Manipulator

class Antenna(BaseEntity):
    diameter: float

    def get_diameter(self) -> float:
        return self.diameter

    def set_diameter(self, value: float) -> bool:
        self.diameter = value
        return True

class Antennas(BaseContainer[Antenna]):
    pass

class Observatory(Manipulator):
    pass

observatory = Observatory(base_classes=[Antenna, Antennas])
antenna = Antenna(name="DSS14", diameter=70.0)

assert observatory.inspect(antenna, get_diameter=None) == 70.0
observatory.configure(antenna, set_diameter=64.0)
assert antenna.diameter == 64.0
```

`inspect` and `configure` follow from the request model itself — an attribute names a method,
and the method reads or writes — so they serve every type you ever add.

Ask for several things at once and every outcome comes back:

```python
results = observatory.inspect(antenna, get_diameter=None, get=["name", "isactive"])
assert results["get_diameter"]["result"] == 64.0
assert results["get"]["result"]["name"] == "DSS14"
```

## 5. Add an operation of your own

Write a `Super` when an operation carries domain logic. The handler is usually one line,
because `_apply_methods` owns the loop.

```python
from msb_arch import Super

class Antenna(BaseEntity):           # extended with something worth calculating
    diameter: float

    def get_diameter(self) -> float:
        return self.diameter

    def set_diameter(self, value: float) -> bool:
        self.diameter = value
        return True

    def collecting_area(self) -> float:
        return 3.14159 * (self.diameter / 2) ** 2

class Calculator(Super):
    OPERATION = "calculate"

    def _calculate(self, obj, attributes):
        return self._apply_methods(obj, attributes)

observatory = Observatory(base_classes=[Antenna])
observatory.register_operation(Calculator(observatory))

antenna = Antenna(name="DSS14", diameter=70.0)
assert round(observatory.calculate(antenna, collecting_area=None)) == 3848
```

Dispatch is by operation *and* by type, so `_calculate_antenna` would be reached for antennas
and `_calculate` for everything else. Adding a new entity adds no code here at all.

## 6. Send requests as data

A facade is sugar. Underneath, a request is a dictionary, which is why the same code can serve
a dialog box, a script and a remote caller — and why a session can be recorded and replayed.

```python
response = observatory.process_request({
    "operation": "calculate",
    "obj": antenna,
    "attributes": {"collecting_area": None},
})
assert response["status"] is True
```

Several at once:

```python
responses = observatory.batch([
    {"operation": "calculate", "obj": antenna, "attributes": {"collecting_area": None}},
    {"operation": "calculate", "obj": antenna, "attributes": {"get_diameter": None}},
])
assert len(responses) == 2
```

## 7. Save and load

`to_dict` produces plain data — entities nested to any depth, sets and tuples included — and
`from_dict` restores the declared types from the annotations.

```python
import json

class Array(BaseContainer[Antenna]):
    pass

array = Array(name="array")
array.add(antenna)

text = json.dumps(array.to_dict())
restored = Array.from_dict(json.loads(text))
assert restored.get("DSS14").diameter == 70.0
assert restored == array
```

When a model changes shape, say how to read the old one:

```python
class Instrument(BaseEntity):
    SCHEMA_VERSION = 2
    diameter: float              # this was 'size' in version 1

    @classmethod
    def migrate(cls, data, from_version):
        if from_version == 1:
            data["diameter"] = data.pop("size")
        return data

old = {"name": "i", "isactive": True, "type": "Instrument", "schema_version": 1, "size": 25.0}
assert Instrument.from_dict(old).diameter == 25.0
```

## 8. Watch what happens

One hook sees every request before it runs and its response after. Metrics, auditing, rate
limiting and authorisation are all this hook, which is why MSB provides it and none of them.

```python
from msb_arch import RequestJournal, RequestMetrics

metrics = RequestMetrics()
journal = RequestJournal()
observatory.add_interceptor(metrics)
observatory.add_interceptor(journal)

observatory.calculate(antenna, collecting_area=None)
observatory.calculate(antenna, get_diameter=None)

assert metrics.snapshot()["calculate"]["calls"] == 2
assert len(journal.touching("DSS14")) == 2
```

The journal reads both ways: backwards it says what produced a result, forwards it replays the
session.

```python
observatory.remove_interceptor(journal)     # or the replay records itself
assert len(journal.replay(observatory)) == 2
```

## 9. Keep the interface responsive

Long work belongs off the event loop. Every facade has an `a`-prefixed twin, and the
synchronous ones are unchanged.

```python
import asyncio

async def main():
    return await observatory.acalculate(antenna, collecting_area=None)

assert round(asyncio.run(main())) == 3848
observatory.close()                          # shuts the executor down
```

## 10. Handle what goes wrong

Every exception derives from `MSBError`, and also from the built-in it replaces, so you can be
as broad or as narrow as you like.

```python
from msb_arch import MSBError, ValidationError

try:
    Dish(name="bad", diameter=-1.0, band="X")
except ValidationError:
    pass                # anything the caller got wrong
except MSBError:
    pass                # anything from the framework
```

By default a facade raises on failure. Ask for the response instead when you would rather
inspect it:

```python
response = observatory.calculate(antenna, no_such_method=None, raise_on_error=False)
assert response["status"] is False
```

## Where to go next

| | |
| --- | --- |
| The data model, type hints, caching, serialization | [Base module](modules/base.md) |
| Writing your own operation | [Super module](modules/super.md) |
| Interceptors, built-ins, the asynchronous surface | [Mega module](modules/mega.md) |
| Every class and method | [API reference](api.md) |
| What will not break, and how anything changes | [Compatibility](COMPATIBILITY.md) |
| What is planned | [Roadmap](ROADMAP.md) |
