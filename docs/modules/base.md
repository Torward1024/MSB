# Base Module

The base layer defines three classes.

`Serializable` holds everything an object needs to be validated, serialized and cached:
the annotated fields and their type checking, the `name` and `isactive` state, `to_dict`,
the cache and the ownership graph invalidation travels through.

`BaseEntity` and `BaseContainer` both derive from it, and **neither derives from the
other**. An entity addresses its attributes; a container addresses its items. They spell
that with the same words -- `get`, `set`, `clear`, `[]`, `in` -- which is exactly why they
have to be siblings: while the container inherited from the entity, each of those names
carried two incompatible meanings inside one hierarchy.

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

`entity.get("field")` reads an attribute; `container.get("name")` returns an item.
`entity.clear()` nulls the attributes; `container.clear()` removes the items. A container
stored as an attribute of an entity is serialized and restored normally, because both sides
are `Serializable`.



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
  Unset annotated attributes are initialized to None by `__init__`, so a mandatory attribute
  cannot be expressed through its annotation; enforce it in the subclass instead.

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

- **Every hint above round-trips through JSON.** `to_dict` writes only data -- a set, a
  frozenset and a tuple all become lists, and entities held inside a list or a dict are
  serialized like any other -- and `from_dict` restores the declared type from the annotation.
  A set is written in a stable order, so the same object always produces the same output.
- `None` elements inside collections are skipped, mirroring the top-level rule for attributes.
- Elements of abstract collections are deliberately left unchecked so that validation never
  consumes an arbitrary iterable.
- A hint that cannot be resolved to a class is accepted rather than raising, so an exotic
  annotation never blocks an otherwise valid assignment.

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

inventory.add(more_products)  # Merges containers

# Activate/deactivate
inventory.deactivate_all()
active_items = inventory.get_active_items()  # Empty list

inventory.activate_all()
active_items = inventory.get_active_items()  # All items
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
| `clear()` | Remove all items |
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
| `clear()` | Clear all non-internal attributes |
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

- **The mapping is returned as it is, not copied.** Mutating what `to_dict` returns corrupts
  the cache for every later reader. Copy it before changing it.
- **Invalidation climbs the ownership graph.** Changing a nested entity or a container item
  refreshes every cache above it, so a write is not free: with many owners the walk is the
  dominant cost, and it currently runs even when no owner caches at all. That is item P6 in
  [the roadmap](../ROADMAP.md).

Use it for objects serialized repeatedly and written rarely -- a model rendered to a GUI on
every redraw. Avoid it for write-heavy objects, where every write pays for the walk and
throws the mapping away, and for one-shot serialization, where nothing reads the cache twice.

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