# Examples

Worked examples, longer than the [guide](guide.md)'s. Every block runs: the test suite executes
this page top to bottom.

## An inventory

The model: parts, boxes of parts, and a warehouse of boxes.

```python
from typing import Annotated, List, Optional, Tuple
from msb_arch import BaseContainer, BaseEntity, Manipulator, NonEmpty, Positive, Super

class Part(BaseEntity):
    price: Annotated[float, Positive()]
    material: Annotated[str, NonEmpty()]
    quantity: int
    tags: List[str]

    def get_price(self) -> float:
        return self.price

    def set_price(self, value: float) -> bool:
        self.price = value
        return True

    def line_total(self) -> float:
        return self.price * self.quantity

class Box(BaseContainer[Part]):
    pass

class Warehouse(BaseContainer[Box]):
    pass
```

Annotations are the schema. A constraint travels with one, so it is enforced on construction, on
assignment and on restore.

```python
bolt = Part(name="bolt", price=4.5, material="steel", quantity=100, tags=["fastener"])
nut = Part(name="nut", price=1.5, material="brass", quantity=250, tags=["fastener"])

crate = Box(name="crate")
crate.add(bolt, copy_items=False)
crate.add(nut, copy_items=False)

store = Warehouse(name="store")
store.add(crate, copy_items=False)

assert store["crate"]["bolt"] is bolt
assert len(crate) == 2
```

`add` stores a **copy** by default, so `add(bolt)` would leave you holding a different object
from the one in the container -- and `store.add(crate)` would copy the crate and everything in
it. `copy_items=False` stores the object itself, which is what you want when the variable and the
container should stay the same thing:

```python
scratch = Box(name="scratch")
scratch.add(bolt)                              # a copy this time

bolt.price = 9.0
assert scratch.get("bolt").price == 4.5        # unaffected
bolt.price = 4.5
```

### Querying

```python
assert [part.name for part in crate.get_by_value({"material": "brass"})] == ["nut"]
assert sorted(crate.get_all()) == ["bolt", "nut"]
assert crate.get("bolt").tags == ["fastener"]
```

### An operation of your own

```python
class Costing(Super):
    OPERATION = "cost"

    def _cost_part(self, obj, attributes):
        return obj.line_total()

    def _cost_box(self, obj, attributes):
        return sum(self._cost_part(part, attributes) for part in obj.get_items())

    def _cost_warehouse(self, obj, attributes):
        return sum(self._cost_box(box, attributes) for box in obj.get_items())

class Depot(Manipulator):
    pass

depot = Depot(base_classes=[Part, Box, Warehouse])
depot.register_operation(Costing(depot))

assert depot.cost(bolt) == 450.0              # 4.5 x 100
assert depot.cost(crate) == 825.0              # and 1.5 x 250 for the nuts
assert depot.cost(store) == 825.0
```

One handler per type, each named so dispatch finds it. Adding a fourth type means adding a fourth
handler and changing nothing else.

## Reading and writing without writing code

`inspect`, `configure`, `save` and `load` are registered for you.

```python
assert depot.inspect(bolt, get_price=None) == 4.5
depot.configure(bolt, set_price=5.0)
assert bolt.price == 5.0

depot.save(store, path="store.json")
restored = depot.load(store, path="store.json")
assert restored == store
assert depot.cost(restored) == 875.0           # 5.0 x 100 + 1.5 x 250
```

Reaching one member of a collection, rather than the collection:

```python
assert depot.inspect(crate, name="nut", get_price=None) == 1.5
```

## A pipeline

Steps that feed each other, given as data.

```python
outcome = depot.pipeline({
    "written": {"operation": "save", "obj": store, "path": "snapshot.json"},
    "read":    {"operation": "load", "obj": store, "path": "snapshot.json",
                "after": ["written"]},
    "total":   {"operation": "cost", "obj": "@read"},
})

assert outcome.output == 875.0
assert outcome.failed == []
assert list(outcome) == ["written", "read", "total"]
```

`after` is for order without a value: the file has to exist before it is read.

### When a step fails

```python
outcome = depot.pipeline({
    "missing": {"operation": "load", "obj": store, "path": "absent.json"},
    "below":   {"operation": "cost", "obj": "@missing"},
    "elsewhere": {"operation": "cost", "obj": crate},
}, raise_on_error=False)

assert outcome.failed == ["missing", "below"]
assert outcome["below"]["skipped"] is True
assert outcome.of("elsewhere") == 875.0
```

The branch below the failure is skipped; the independent one still runs.

### Two branches at once

```python
plan = {
    "left":  {"operation": "cost", "obj": crate},
    "right": {"operation": "cost", "obj": store},
}
assert depot.pipeline(plan, concurrent=True).failed == []
```

Both wait for nothing, so they share a stage.

## A project

A named set of entities with a factory.

```python
from msb_arch import Project

class PartsProject(Project):
    _item_type = Part

    def create_item(self, item_code="P", isactive=True):
        self.add_item(Part(name=item_code, price=1.0, material="steel",
                           quantity=1, tags=[], isactive=isactive))

project = PartsProject(name="restock")
project.create_item("washer")
project.create_item("screw")

assert len(project.get_items()) == 2
assert project.get_item("washer").material == "steel"
```

With a managing object set, a request may leave `obj` out:

```python
depot.set_managing_object(project)
assert depot.inspect(get_name=None) == "restock"
depot.set_managing_object(None)
```

## Watching a session

```python
from msb_arch import RequestJournal, RequestMetrics

depot.add_interceptor(RequestMetrics())
depot.add_interceptor(RequestJournal(fingerprints=True))

depot.inspect(bolt, get_price=None)
depot.configure(bolt, set_price=6.0)
depot.configure(bolt, set_price=6.0)           # the same value again

assert depot.metrics()["configure"]["calls"] == 2
assert len(depot.history("bolt")) == 3
assert len(depot.history(changed_only=True)) == 1
```

Only one of the three requests changed anything: reading does not, and writing the value an
object already holds does not either.

### Replaying it

```python
journal = depot.journal()
depot.remove_interceptor(journal)              # or the replay records itself

bolt.price = 4.5
assert depot.replay(journal).failed == []
assert bolt.price == 6.0
```

### Refusing a request

An interceptor may answer without calling the next one.

```python
def read_only(request, call_next):
    if request["operation"] == "configure":
        return {"status": False, "object": None, "method": None, "result": None,
                "error": "read-only mode", "error_type": "RequestError"}
    return call_next(request)

depot.add_interceptor(read_only)
response = depot.configure(bolt, set_price=99.0, raise_on_error=False)

assert response["status"] is False
assert bolt.price == 6.0
depot.remove_interceptor(read_only)
```

## Asking what the application can do

Everything here is derived, so a menu built from it cannot go stale.

```python
model = depot.describe_model()
assert model["Box"]["holds"]["items"] == ["Part"]
assert model["Warehouse"]["container"] is True
assert depot.dependents_of("Part") == ["Box", "Warehouse"]
```

The handlers a new operation over that model would need:

```python
source = depot.scaffold("audit")
assert "def _audit_part(" in source
assert "def _audit_box(" in source
```

## Versioning a model

```python
class Fastener(BaseEntity):
    SCHEMA_VERSION = 2
    price: float                   # this was 'cost' in version 1

    @classmethod
    def migrate(cls, data, from_version):
        if from_version == 1:
            data["price"] = data.pop("cost")
        return data

old = {"name": "f", "isactive": True, "type": "Fastener", "schema_version": 1, "cost": 3.0}
assert Fastener.from_dict(old).price == 3.0
```

A class that has never versioned itself writes exactly what it wrote before versioning existed,
and data with no version reads as version 1.

## Serialization round trips

```python
import json

class Assembly(BaseEntity):
    parts: List[Part]
    spare: Optional[Part]
    codes: Tuple[int, ...]

assembly = Assembly(name="a", parts=[bolt], spare=None, codes=(1, 2))
data = json.loads(json.dumps(assembly.to_dict()))
restored = Assembly.from_dict(data)

assert restored == assembly
assert isinstance(restored.codes, tuple)     # JSON had a list; the annotation says tuple
assert restored.parts[0].price == 6.0
```

The annotation is the schema: JSON has no tuple, so the declared type is what says the list was
one.

## Errors

```python
from msb_arch import errors

try:
    Part(name="bad", price=-1.0, material="steel", quantity=1, tags=[])
except errors.ConstraintError as error:
    assert "must be positive" in str(error)

try:
    depot.load(store, path="nowhere.json")
except errors.NotFoundError:
    pass

response = depot.configure(bolt, no_such_method=None, raise_on_error=False)
assert response["status"] is False
```

A facade raises the kind of failure that happened. Ask for the response instead when you would
rather read it.

## One domain, any adapter

MSB is the domain layer; everything that talks to the outside world is an adapter around it. This
section keeps one small domain — customers — and puts it behind a web service, a command line and a
database in turn. **The domain does not change once.** That is the point: moving from files to SQL,
or from a desktop tool to an HTTP service, is replacing an adapter, not rewriting the application.

```python
from msb_arch import BaseContainer, BaseEntity, Manipulator, Super, invariant

class Customer(BaseEntity):
    email: str = ""
    credit: float = 0.0

    @invariant("credit cannot be negative")
    def _solvent(self) -> bool:
        return self.credit >= 0

class Customers(BaseContainer[Customer]):
    pass

class Discount(Super):
    OPERATION = "discount"

    def _discount_customers(self, obj, attributes):
        rate = attributes.get("rate", 0.1)
        return {customer.name: round(customer.credit * rate, 2) for customer in obj.get_items()}

class Service(Manipulator):
    pass

crm = Customers(name="crm")
service = Service(base_classes=[Customer, Customers], managing_object=crm)
service.register_operation(Discount(service))
```

### CRUD is four requests

Create, read, update and delete are requests like any other. An object on the far side of a wire is
named by its **address**, and `locate` turns the address back into the object:

```python
# create
service.configure(crm, add=Customer.from_dict({"name": "ada", "email": "ada@example.com",
                                                "credit": 120.0}))
# read
assert service.inspect(service.locate(["crm", "ada"]), get="credit") == 120.0
# update -- the invariant still guards it
service.configure(service.locate(["crm", "ada"]), set={"params": {"credit": 80.0}})
assert crm.get("ada").credit == 80.0
# delete
service.configure(crm, remove="ada")
assert len(crm) == 0
```

A refused update comes back as a failed response rather than a corrupted record:

```python
service.configure(crm, add=Customer(name="bob", credit=10.0))
refused = service.configure(service.locate(["crm", "bob"]), set={"params": {"credit": -5.0}},
                            raise_on_error=False)
assert refused.ok is False and crm.get("bob").credit == 10.0
```

### Behind HTTP

A web framework only translates JSON into a request and the response back. With FastAPI:

```text
from fastapi import FastAPI

app = FastAPI()

@app.post("/request")
def handle(body: dict):
    target = service.locate(body["path"]) if body.get("path") else None
    response = service.process_request({"operation": body["operation"], "obj": target,
                                        "attributes": body.get("attributes", {})})
    return dict(response)

@app.get("/operations")
def operations():
    return service.describe_operations()      # the API describes itself
```

```text
POST /request  {"operation": "configure", "path": ["crm", "bob"],
                "attributes": {"set": {"params": {"credit": 50.0}}}}
POST /request  {"operation": "discount", "attributes": {"rate": 0.2}}
```

Flask and Django are the same three lines inside their own view. The responses are plain
dictionaries, so they serialize as they are. `tests/test_adapters.py` runs this service through
FastAPI's test client whenever FastAPI is installed.

### Behind a command line — with no list of flags

A handler's parameters are derived from its code, so the command line builds its flags from the
catalogue instead of repeating them. Add a parameter to the handler and the flag appears:

```text
import argparse

accepts = service.describe_operations("discount")["discount"]["customers"]["accepts"]
parser = argparse.ArgumentParser(prog="discount")
for key in accepts:
    parser.add_argument(f"--{key}", type=float)

arguments = parser.parse_args(["--rate", "0.5"])
given = {key: value for key, value in vars(arguments).items() if value is not None}
assert service.discount(**given) == {"bob": 5.0}
```

A dialog does the same thing with a form field per key.

The catalogue reads a handler's source, so this runs on classes defined in a module — which is
every real application — and not on ones typed into an interactive session. `tests/test_adapters.py`
runs it.

### Moving the storage from files to SQL

`save` and `load` are defaults. Registering operations of the same name replaces them, and nothing
that calls `service.save(...)` notices. Here the model moves into SQLite using only the standard
library; SQLAlchemy, a document store or an HTTP API has the same shape:

```python
import json
import sqlite3

class SqlSave(Super):
    OPERATION = "save"

    def _save(self, obj, attributes):
        with sqlite3.connect(attributes["path"]) as db:
            db.execute("CREATE TABLE IF NOT EXISTS models (name TEXT PRIMARY KEY, data TEXT)")
            db.execute("INSERT OR REPLACE INTO models VALUES (?, ?)",
                       (obj.name, json.dumps(obj.to_dict())))
        return True

class SqlLoad(Super):
    OPERATION = "load"

    def _load(self, obj, attributes):
        with sqlite3.connect(attributes["path"]) as db:
            (data,) = db.execute("SELECT data FROM models WHERE name = ?", (obj.name,)).fetchone()
        return type(obj).from_dict(json.loads(data))

service.register_operation(SqlSave(service))      # replaces the JSON default
service.register_operation(SqlLoad(service))

service.save(crm, path="crm.db")
assert service.load(crm, path="crm.db") == crm     # rules re-checked on the way in
```

The invariants, the constraints and every operation came along unchanged, and so did their tests.
That is what an independent domain layer is for.

### Keep the ORM out of the entities

It is tempting to make an entity an ORM model as well. Don't: the entity then depends on the
database, the database's rules start leaking into the domain's, and the property that let the
storage be swapped above is gone. Map between the two in an adapter — `to_dict` and `from_dict` are
the seam — and the domain stays testable without a database at all.
