# Base Module

The base layer defines three classes.

`Serializable` holds everything an object needs to be validated, serialized and cached:
the annotated fields and their type checking, the `name` and `isactive` state, `to_dict`,
the cache and the ownership graph invalidation travels through.

`BaseEntity` and `BaseContainer` both derive from it, and neither derives from the other. An
entity addresses its attributes; a container addresses its items, and both spell that with the
same words: `get`, `set`, `clear`, `[]`, `in`. While the container inherited from the entity,
each of those names carried two meanings in one hierarchy.

| You want | Use |
| --- | --- |
| `isinstance` that accepts either | `Serializable` |
| A typed object addressed by attributes | `BaseEntity` |
| A named collection of such objects | `BaseContainer[T]` |

## Thread safety

What MSB shares between objects is guarded: declaring classes, resolving type hints,
generating a project's container class and resolving an operation handler can all happen on
several threads at once. `to_dict` keeps its traversal marks in a context variable, so
concurrent serializations never interfere.

A single object is not guarded, exactly as a plain Python object is not. Two threads writing
attributes of the same entity, or adding to the same container, must be serialized by the
caller; with `use_cache=True` a write racing a read can leave a stale cached mapping.

`entity.get("field")` reads an attribute; `container.get("name")` returns an item. Emptying them
is two different jobs and has two names: `entity.reset_attributes()` nulls the attributes,
`container.remove_all()` removes the items. (`clear()` did both, meaning something different on
each side; it was deprecated in 1.9.0 and removed in 2.0.) A container stored as an attribute of
an entity is serialized and restored normally, because both sides are `Serializable`.



## BaseEntity

`BaseEntity` is an abstract base class that provides attribute management, type validation, serialization, and common entity functionality.

**Attributes:**

- `name` (str): An identifier for the entity.
- `isactive` (bool): Indicates whether the entity is active or inactive.
- `_fields` (Dict[str, type]): Class-level mapping of attribute names to their expected types (from annotations).

Abstract: subclass it. Attributes are validated against the annotations, and `to_dict` and
`from_dict` cover every annotated attribute, nested entities included.

### A worked example

```python
from msb_arch.base import BaseEntity

class MyEntity(BaseEntity):
    name: str
    value: int
    description: str = "Default description"

# Create instance
entity = MyEntity(name="test_entity", value=42)
print(entity.name)  # "test_entity"
print(entity.isactive)  # True

# Modify attributes
entity.set({"value": 100, "description": "Updated"})
print(entity.get("value"))  # 100

# Serialize
data = entity.to_dict()
print(data)
# {'name': 'test_entity', 'isactive': True, 'value': 100, 'description': 'Updated', 'type': 'MyEntity'}

# Deserialize
new_entity = MyEntity.from_dict(data)
```

### Nested entities

```python
class Address(BaseEntity):
    street: str
    city: str

class Person(BaseEntity):
    name: str
    age: int
    address: Address

address = Address(name="Adress1", street="123 Main St", city="Anytown")
person = Person(name="John", age=30, address=address)

# Serialization handles nesting automatically
data = person.to_dict()
# {'name': 'John', 'isactive': True, 'age': 30,
#  'address': {'street': '123 Main St', 'city': 'Anytown', 'name': None, 'isactive': True, 'type': 'Address'},
#  'type': 'Person'}
```

### What a wrong type does

```python
# This will raise TypeError
try:
    invalid_entity = MyEntity(name="test", value="not_a_number")
except TypeError as e:
    print(e)  # "Attribute 'value' must be of type <class 'int'>, got <class 'str'>"
```

### Construction

The `__init__` method initializes a new `BaseEntity` instance with a required name, optional activation status, and additional attributes.

**Parameters:**

- `name` (str): Required identifier for the entity.
- `isactive` (bool, optional): Initial activation status. Defaults to True.
- `use_cache` (bool, optional): Enable caching for serialization. Defaults to False.
- `**kwargs`: Additional keyword arguments for annotated attributes.

**Raises:**

- `TypeError`: If an attribute value does not match its annotated type, or if 'name' is None.
- `ValueError`: If an unknown attribute is provided.

**Example:**

```python
# Valid initialization
entity = MyEntity(name="example", value=42)

# This will raise ValueError for unknown attribute
try:
    invalid_entity = MyEntity(name="test", unknown_attr="value")
except ValueError as e:
    print(e)  # "Unknown attributes provided for MyEntity: {'unknown_attr'}"
```

### What a field starts as

The value written after the annotation is what the field starts as:

```python
from typing import List

class Reading(BaseEntity):
    value: float = 0.0
    unit: str = "Jy"
    tags: List[str] = []
    comment: str                       # nothing declared

reading = Reading(name="r1")
assert reading.value == 0.0
assert reading.unit == "Jy"
assert reading.comment is None         # a field with nothing declared starts as None
```

Three things follow, and each is what the syntax already suggested:

- **A value passed in wins.** `Reading(name="r1", value=9.0)` is 9.0. Passing `None` on purpose
  means None -- asking for nothing is not the same as not asking.
- **A mutable start belongs to the object, not to the class.** `tags: List[str] = []` gives every
  object its own empty list; appending to one leaves the others empty. This is the one place the
  framework departs from a plain class body, where that list would be shared by everything.
- **It is validated like anything else.** `size: int = "large"` fails when the object is built,
  not later, and a constraint on the field applies to the declared value too.

Declared values are inherited, and a subclass overrides one by declaring its own.

> Before 2.0 the declaration was ignored: `value: float = 0.0` left `value` at None on every
> instance while the class itself kept 0.0. Code that relied on that None now gets the declared
> value instead.

### Checking a value yourself

The `_validate_type` method validates that a given value matches the expected type from annotations.

**Parameters:**

- `key` (str): The attribute name being validated.
- `value` (Any): The value to check.
- `expected_type` (Any): The expected type from type annotations.

**Raises:**

- `TypeError`: If the value does not match the expected type, or if 'name' is None.

**Notes:**

- Handles complex types including Union, Dict, List, and nested entities.
- Allows None values for every attribute except 'name', which containers use as the item key.
  A field the constructor is not given starts as whatever the class declared, and as None when
  the class declared nothing -- so a mandatory attribute cannot be expressed through its
  annotation; enforce it with an `@invariant` or in the subclass instead.

**Supported type hints:**

Parameterized hints are checked structurally and nested to any depth, so
`Dict[str, List[Dict[str, int]]]` validates every key, every list element and every leaf value.

| Hint | Checked |
| --- | --- |
| `int`, `str`, custom classes | `isinstance` against the class |
| `Any` | accepted unconditionally |
| `Union[X, Y]`, `Optional[X]`, `X \| Y` | value must match at least one member |
| `List[X]`, `Set[X]`, `FrozenSet[X]` | container type plus every element |
| `Tuple[X, Y]` | exact arity plus each position |
| `Tuple[X, ...]` | tuple type plus every element |
| `Dict[K, V]` | dict type plus every key and value |
| `Literal[...]` | value equals one of the literals, with a matching type |
| `Callable[...]` | value is callable |
| `Type[X]` | value is a class and a subclass of X |
| `Sequence[X]`, `Mapping[K, V]` and other abstract collections | `isinstance` against the origin only |
| `Annotated[X, ...]` | unwrapped to X |

- **Every hint above round-trips through JSON, except `Callable`.** `to_dict` writes only data
  -- a set, a frozenset and a tuple all become lists, a `Type[X]` field is written as the class's
  name, and entities held inside a list or a dict are serialized like any other -- and
  `from_dict` restores the declared type from the annotation. A set is written in a stable order,
  so the same object always produces the same output.
- **A `Callable` field does not survive a file.** A function is code, and restoring one from a
  name would mean importing whatever a file asks for. Such a field is written as it is, which
  `json.dumps` refuses: keep callables out of anything that is saved, or hold the *name* of the
  operation and look it up yourself.
- **A `Type[X]` field is written by name and resolved back within `X`.** `Type[Fastener]` holding
  `Bolt` writes `"Bolt"`, and restoring searches `Fastener` and its subclasses first, then the
  model's types by name. A name nothing answers to is left as it is, so validation reports it
  against the field.
- `None` elements inside collections are skipped, mirroring the top-level rule for attributes.
- Elements of abstract collections are deliberately left unchecked so that validation never
  consumes an arbitrary iterable.
- A hint that cannot be resolved to a class is accepted rather than raising, so an exotic
  annotation never blocks an otherwise valid assignment.

### A rule about the whole object

A constraint guards one value. It cannot say that `end` comes after `start`, that weights sum to
one, or that an array holds at most three antennas -- every value is allowed on its own and the
object is still wrong. That is what `@invariant` is for:

```python
from msb_arch import BaseContainer, BaseEntity, errors, invariant

class Window(BaseEntity):
    start: float = 0.0
    end: float = 1.0

    @invariant("end must be after start")
    def _ordered(self) -> bool:
        return self.end > self.start

Window(name="w", start=1.0, end=2.0)          # fine
```

Checked at the same three points a field constraint is -- when the object is built, when it is
restored, and after each write -- and **a refused change leaves the object as it was**:

```python
window = Window(name="w", start=1.0, end=2.0)
try:
    window.end = 0.5
except errors.InvariantError:
    pass
assert window.end == 2.0                      # the write was undone
```

Two fields that must move together are set together. `set` applies the whole group and checks
once at the end, which is what makes such a rule satisfiable at all:

```python
window.set({"start": 10.0, "end": 20.0})
assert (window.start, window.end) == (10.0, 20.0)
```

A group that leaves the object breaking a rule is refused whole -- every attribute in it goes
back. The same is true through a request, since `configure` writes through `set`.

A container's rule is about what it holds, and is checked after anything that changes that:

```python
class Antenna(BaseEntity):
    diameter: float = 1.0

class Antennas(BaseContainer[Antenna]):

    @invariant("an array holds at most three antennas")
    def _small_enough(self) -> bool:
        return len(self) <= 3

rack = Antennas(name="rack")
rack.add(Antenna(name="a1"))
```

| | |
| --- | --- |
| Message | The argument, or the method's docstring, or its name |
| Inherited | Yes. A subclass overrides a rule by defining a method of the same name |
| Several rules | All are checked; the first that fails is reported |
| A rule that raises | Reported as `InvariantError` naming the rule, rather than escaping as itself |
| `check_invariants()` | Call it by hand after writing attributes directly rather than through `set` |
| Cost | Rules are collected when the class is created. A class that declares none is unaffected |

## BaseContainer

`BaseContainer` is a generic container class for managing collections of `BaseEntity` objects. It provides dictionary-like access with additional functionality.

Typed by its parameter, addressed by item name, and supporting `[]`, `in`, `len()` and
iteration.

### A worked example

```python
from msb_arch.base import BaseEntity, BaseContainer

class Product(BaseEntity):
    name: str
    price: float
    category: str

class MyContainer(BaseContainer[Product]):
    pass

# Create typed container
inventory = MyContainer(name="product_inventory")

# Add items
product1 = Product(name="Widget", price=10.99, category="Tools")
product2 = Product(name="Gadget", price=25.50, category="Electronics")

inventory.add(product1)
inventory.add([product2])  # Add multiple

# Access items
print(inventory["Widget"].price)  # 10.99
print(len(inventory))  # 2
print("Widget" in inventory)  # True

# Query items
electronics = inventory.get_by_value({"category": "Electronics"})
print(len(electronics))  # 1

expensive = inventory.get_by_value({"price": 25.50})
print(len(expensive))  # 1
```

### In bulk

```python
# Add from another container
more_products = MyContainer(name="more_products")
more_products.add(Product(name="Tool", price=5.99, category="Tools"))

inventory.add(more_products)                      # merges them in

# Turn items on and off. `isactive` is a flag on each item; nothing is removed by it
inventory.deactivate_all()
assert inventory.get_active_items() == []
inventory.activate_all()
assert len(inventory.get_active_items()) == len(inventory)

inventory.deactivate_item("Tool")
assert [item.name for item in inventory.get_inactive_items()] == ["Tool"]
inventory.activate_item("Tool")
```

**What each of the bulk methods is for:**

| Doing | Method | Note |
| --- | --- | --- |
| Is it here? | `has_item(name)` | The question `get` answers with None and a warning |
| Take one out | `remove(name)` | Raises `NotFoundError` for a name it does not hold |
| Empty it | `remove_all()` | The container itself stays: its name and its item type |
| Replace everything | `set_items({name: item})` | One step, one cache invalidation |
| Put one under a name | `set_item(name, item)` | Replaces whatever was there |
| Drop by flag | `drop_active()`, `drop_inactive()` | Removes them, unlike `deactivate_*` |
| Copy it | `clone(deep=True)` | A deep copy by default: the items are copies too |

```python
assert inventory.has_item("Tool") is True
snapshot = inventory.clone()                      # independent of the original
inventory.remove("Tool")
assert inventory.has_item("Tool") is False
assert snapshot.has_item("Tool") is True

inventory.set_items({"Widget": Product(name="Widget", price=10.99, category="Tools")})
assert [item.name for item in inventory.get_items()] == ["Widget"]

snapshot.deactivate_item("Widget")
snapshot.drop_active()                            # removes what is still active
snapshot.drop_inactive()                          # and then the rest
snapshot.remove_all()
assert len(snapshot) == 0
assert snapshot.name == "product_inventory"       # the container itself stays
```

### Serializing a container

```python
# Serialize entire container
data = inventory.to_dict()
print(data["items"]["Widget"])
# {'name': 'Widget', 'isactive': True, 'price': 10.99, 'category': 'Tools', 'type': 'Product'}

# Deserialize
new_inventory = MyContainer.from_dict(data)   # a concrete subclass, not the generic alias
```

### Container Methods

| Method | Description |
|--------|-------------|
| `add(item)` | Add single item, list, or container |
| `remove(name)` | Remove item by name |
| `get(name)` | Get item by name |
| `get_all()` | Get all items as dictionary |
| `get_items()` | Get all items as list |
| `get_active_items()` | Get only active items |
| `set_items(items)` | Set or replace all items |
| `remove_all()` | Remove every item |
| `clone()` | Create deep copy |
| `__str__()` | Returns a string representation of the container |
| `__repr__()` | Returns the official string representation of the container |
| `__eq__(other)` | Compares two containers for equality |
| `__hash__()` | Returns the hash value of the container |
| `__len__()` | Returns the number of items in the container |
| `__iter__()` | Returns an iterator over the container's items |
| `__getitem__(key)` | Gets an item by key |
| `__setitem__(key, value)` | Sets an item by key |
| `__delitem__(key)` | Deletes an item by key |
| `__contains__(key)` | Checks if an item is in the container |

### The cached serialization is a snapshot

With `use_cache=True` the same mapping comes back from every `to_dict` call. That mapping **is**
the cache, so it is handed out read-only: a `ReadOnlyMapping`, with `ReadOnlyList` for the lists
inside it.

```python
import json
import pytest
from msb_arch import BaseContainer, BaseEntity
from msb_arch.errors import SerializationError

class Bolt(BaseEntity):
    price: float
    tags: list

class Bolts(BaseContainer[Bolt]):
    pass

box = Bolts(name="box", use_cache=True)
box.add(Bolt(name="bolt", price=4.5, tags=["fastener"], use_cache=True))

data = box.to_dict()

# A dict holding lists, so everything that reads them works, including equality with plain ones.
assert json.loads(json.dumps(data))["items"]["bolt"]["price"] == 4.5
assert data["items"]["bolt"]["tags"] == ["fastener"]

with pytest.raises(SerializationError):          # which is also a TypeError
    data["name"] = "other"
with pytest.raises(SerializationError):          # all the way down, lists included
    data["items"]["bolt"]["tags"].append("x")

editable = dict(data)                            # this is how you change it: copy first
editable["name"] = "other"
```

Writing to it used to work, and changed the cache for everyone holding it, with no error and no
sign. The docstring said "treat it as read only", which is a rake with a label on it.

Without caching the result is an ordinary dictionary, since nothing else holds it.

Freezing costs one pass over the tree when the cache is filled -- around 60% on top of building
it -- and nothing per call afterwards: a cached `to_dict` of a thousand entities answers in 0.4 µs
against 2.8 ms to rebuild it. `copy`, `deepcopy` and `pickle` all give back plain, writable
structures.

### Entity Methods

| Method | Description |
|--------|-------------|
| `set(params)` | Update multiple attributes |
| `get(key)` | Get attribute(s) by name |
| `activate()` | Set isactive = True |
| `deactivate()` | Set isactive = False |
| `clone()` | Create deep copy |
| `to_dict()` | Serialize to dictionary |
| `from_dict(data)` | Deserialize from dictionary |
| `has_attribute(key)` | Check if attribute exists |
| `reset_attributes()` | Set every public attribute to None |
| `__getitem__(key)` | Access attribute using [] |
| `__setitem__(key, value)` | Set attribute using [] |
| `__contains__(key)` | Check attribute existence with 'in' |
| `__str__()` | Returns a string representation of the object |
| `__repr__()` | Returns the official string representation of the object |
| `__eq__(other)` | Compares two objects for equality |
| `__hash__()` | Returns the hash value of the object |

## Serialization

`to_dict` produces plain data and nothing else: every entity is reduced to a mapping however
deeply it is nested, and a `set`, `frozenset` or `tuple` becomes a list, because JSON has none
of the three. `from_dict` restores the declared types from the annotations, which is the only
thing that can say whether a JSON list was a list, a set or a tuple.

```python
import json

restored = MyEntity.from_dict(json.loads(json.dumps(entity.to_dict())))
assert restored == entity
```

A set is written in a stable order, so the same object always produces the same bytes. Without
that, hashing or diffing serialized output would be meaningless.

### Versioning a model

Every mapping carries the version of the class that wrote it, under `schema_version`. Raise
`SCHEMA_VERSION` when a field is renamed, removed or given a new meaning, and say how to read
the older shape:

```python
class Widget(BaseEntity):
    SCHEMA_VERSION = 2
    price: float                 # this was called 'size' in version 1

    @classmethod
    def migrate(cls, data, from_version):
        if from_version == 1:
            data["price"] = data.pop("size")
        return data
```

`migrate` runs only when the version differs, so the ordinary case costs nothing. Raising
`SCHEMA_VERSION` without overriding it is a declaration that old data cannot be read: the
default raises `SerializationError` naming both versions, at the boundary, rather than failing
later on a field that is no longer there. Data written before versioning existed carries no
version and is read as version 1.

### Reading data MSB did not write

Foreign JSON has no `type` field, so the annotation answers instead: a mapping is built into
whatever the field declares, through lists, dicts and containers alike.

A `Union` is resolved by trying its members in order and keeping the first that accepts the
data. That is correct whenever the members differ in shape and a guess when they do not. Where
two members could both accept the same mapping, declare which key in the data decides:

```python
from typing import Union

class Sensor(BaseEntity):
    unit: str

class LookAlike(BaseEntity):        # the same shape, so the data cannot tell them apart
    unit: str

class Station(BaseEntity):
    DISCRIMINATORS = {"device": "kind"}     # the incoming data names the type under 'kind'
    device: Union[Sensor, LookAlike]

station = Station.from_dict({"name": "S1", "device": {"name": "d", "unit": "K",
                                                     "kind": "LookAlike"}})
assert isinstance(station.device, LookAlike)
```

The discriminator key is consumed rather than passed on, so the class being built does not see
an attribute it never declared. It reaches inside collections too, so
`List[Union[Sensor, LookAlike]]` works the same way.

### Emptying an entity

`reset_attributes()` sets every public attribute to None, keeping `name`, `isactive` and the
framework's own state. It is what you want when an object is being reused rather than rebuilt:

```python
sample = Product(name="Widget", price=10.99, category="Tools")
sample.reset_attributes()

assert sample.price is None
assert sample.name == "Widget" and sample.isactive is True
```

## Caching and memory

`use_cache=True` keeps the result of `to_dict` on the object. It is off by default, and what
it costs is predictable enough to decide without measuring.

**One mapping per caching object, and it duplicates the data.** The cache is a full
serialization, not a view, so an entity that caches holds its own attributes twice: once as
attributes, once as a dictionary. Nothing is shared between the two.

**It is bounded by the object graph, not by traffic.** Serializing the same object a million
times produces one mapping, not a million, so the cache cannot grow with request volume. It
grows only when the model does.

**It is never evicted.** A cached mapping lives as long as its object and is replaced, not
released, when invalidated. There is no size limit and no expiry, because there is nothing to
limit: the ceiling is the size of the model.

Measured on 2026-08-04, with entities of two fields beyond `name` and `isactive`:

| Container of 8 000 items | Resident |
| --- | --- |
| Nothing caches | 4.18 MB |
| The container caches | 5.75 MB |
| The container and every item cache | 7.16 MB |

A cached mapping costs roughly 275 bytes per item and scales linearly: 0.27 MB at 1 000
items, 5.25 MB at 20 000.

**Caching at both levels stores the data twice.** A container's mapping already contains every
item serialized inline, so item caches add a second copy of the same content -- the 71%
above, against 38% for the container alone. Cache the level you actually serialize. Caching
items as well pays off only when they are also serialized individually and often.

Two behaviours worth knowing before turning it on:

- **The mapping you get back *is* the cache, and it refuses to be written to.** `to_dict` on a
  caching object returns a `ReadOnlyMapping` (and `ReadOnlyList` for the lists inside it):
  reading, `json.dumps`, unpacking and comparison all work, and a write raises
  `SerializationError`. Take `dict(...)` of it when you need to change something. Without
  `use_cache` nothing is frozen, since nothing else holds the result.
- **Invalidation climbs the ownership graph.** Changing a nested entity or a container item
  refreshes every cache above it, so a write is not free: with many owners the walk is the
  dominant cost.

```python
cached = Product(name="Widget", price=10.99, category="Tools", use_cache=True)
snapshot = cached.to_dict()

try:
    snapshot["price"] = 0.0
except errors.SerializationError as error:
    assert "read-only" in str(error).lower() or "copy" in str(error).lower()

mine = dict(snapshot)                       # a plain, writable copy
mine["price"] = 0.0
```

Use it for objects serialized repeatedly and written rarely -- a model rendered to a GUI on
every redraw. Avoid it for write-heavy objects, where every write pays for the walk and
throws the mapping away, and for one-shot serialization, where nothing reads the cache twice.

**What the caches hold right now**, when a long-lived process wants to know:

```python
from msb_arch import cache_statistics

counts = cache_statistics()
assert set(counts) == {"objects", "populated", "entries"}
```

`objects` is how many live objects have caching enabled, `populated` how many currently hold a
mapping, and `entries` the total number of keys across them -- computed on demand from the
registry invalidation already keeps, so nothing is counted while the framework runs.

## Has this changed?

Two answers, with different costs and different reach.

```python
from msb_arch import BaseContainer, BaseEntity

class Part(BaseEntity):
    price: float

class Parts(BaseContainer[Part]):
    pass

bolt = Part(name="bolt", price=4.5)
assert bolt.revision == 0

bolt.price = 4.5                      # the same value it already held
assert bolt.revision == 1             # it was written to
```

| | `revision` | `fingerprint()` |
| --- | --- | --- |
| Answers | Was this written to | Is the content the same |
| Costs | An increment, on the path that already invalidates the cache | One serialisation |
| Covers | This object | This object and everything below it |
| Survives a restart | No | Yes |

```python
box = Parts(name="box", items={"bolt": bolt})
before = box.revision, box.fingerprint()

bolt.price = 9.0

assert box.revision == before[0]              # the container was not written to
assert box.fingerprint() != before[1]         # but its contents changed
assert Part(name="bolt", price=9.0).fingerprint() == bolt.fingerprint()
```

`revision` counts writes rather than differences, deliberately: comparing values means keeping
the old ones. It is not serialised, since it counts writes in one process's memory.

## Error Handling

The Base module raises the framework's own types, each deriving from the built-in it
replaces, so nothing written against an earlier version stops catching what it caught:

| Raised | Also a | When |
| --- | --- | --- |
| `TypeValidationError` | `TypeError` | an attribute or a container item does not match its annotation |
| `UnknownAttributeError` | `ValueError` | an attribute the class never declared |
| `ItemNameError`, `DuplicateNameError` | `ValueError` | an item has no name, the wrong name, or one already taken |
| `ResolutionError` | `TypeError` | a forward reference, a `TypeVar` or an unparameterized container cannot be resolved |
| `NotFoundError` | `KeyError` | an attribute or item was looked up and is not there |
| `SerializationError` | `ValueError`, `TypeError` | a round trip through a dictionary failed |

All of them derive from `MSBError`, so `except MSBError` catches anything from the framework
and `except ValidationError` catches anything the caller got wrong. The full tree is in the
[API reference](../api.md#exception-hierarchy).

All operations are logged with appropriate levels (debug, info, warning, error).