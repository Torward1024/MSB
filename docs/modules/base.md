# Base Module

The Base module provides the fundamental building blocks for the MSB Framework: `BaseEntity` and `BaseContainer`. These classes form the core data management layer.

## BaseEntity

`BaseEntity` is an abstract base class that provides attribute management, type validation, serialization, and common entity functionality.

**Attributes:**

- `name` (str): An identifier for the entity.
- `isactive` (bool): Indicates whether the entity is active or inactive.
- `_fields` (Dict[str, type]): Class-level mapping of attribute names to their expected types (from annotations).

**Notes:**

- Logging is integrated via `utils.logging_setup.logger` to track initialization and state changes.
- This is an abstract base class and cannot be instantiated directly; it must be subclassed.
- Attributes are validated against type annotations defined in `__annotations__`.
- Serialization methods `to_dict` and `from_dict` automatically handle all annotated attributes, including nested entities.

### Key Features

- **Type Validation**: Automatic validation of attributes against type annotations
- **Serialization**: Bidirectional conversion to/from dictionaries
- **Activation State**: Built-in active/inactive state management
- **Caching**: Optional caching for performance optimization
- **Logging**: Integrated logging for all operations

### Basic Usage

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

### Advanced Features

#### Nested Entities

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

#### Type Validation

```python
# This will raise TypeError
try:
    invalid_entity = MyEntity(name="test", value="not_a_number")
except TypeError as e:
    print(e)  # "Attribute 'value' must be of type <class 'int'>, got <class 'str'>"
```

#### Initialization (__init__)

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

#### Type Validation (_validate_type)

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

- `None` elements inside collections are skipped, mirroring the top-level rule for attributes.
- Elements of abstract collections are deliberately left unchecked so that validation never
  consumes an arbitrary iterable.
- A hint that cannot be resolved to a class is accepted rather than raising, so an exotic
  annotation never blocks an otherwise valid assignment.

## BaseContainer

`BaseContainer` is a generic container class for managing collections of `BaseEntity` objects. It provides dictionary-like access with additional functionality.

### Key Features

- **Generic Typing**: Type-safe container for specific entity types
- **Dictionary Interface**: Supports `[]`, `in`, `len()`, iteration
- **Bulk Operations**: Add/remove multiple items, activate/deactivate all
- **Query Methods**: Find items by attributes or conditions
- **Serialization**: Container-level serialization with nested entities

### Basic Usage

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

### Advanced Operations

#### Bulk Operations

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

#### Serialization

```python
# Serialize entire container
data = inventory.to_dict()
print(data["items"]["Widget"])
# {'name': 'Widget', 'isactive': True, 'price': 10.99, 'category': 'Tools', 'type': 'Product'}

# Deserialize
new_inventory = BaseContainer[Product].from_dict(data)
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

## Best Practices

1. **Define Clear Type Annotations**: Use specific types in your entity classes for better validation.

2. **Use Meaningful Names**: Entity names should be unique within containers.

3. **Handle Serialization Carefully**: Cycles of any length are detected and marked with
   `CYCLIC_REFERENCE`, but a payload carrying that marker cannot be restored by `from_dict`.
   Break the cycle before a round trip.

4. **Leverage Container Queries**: Use `get_by_value()` for complex filtering instead of manual loops.

5. **Enable Caching**: Use `use_cache=True` for entities that are serialized frequently. The
   cached mapping is returned as is, so copy it before mutating. Invalidation travels up the
   ownership chain, so changing a nested entity or a container item refreshes every cache
   above it.

## Error Handling

The Base module raises specific exceptions:

- `TypeError`: When attribute types don't match annotations
- `ValueError`: When validation rules are violated
- `KeyError`: When accessing non-existent attributes

All operations are logged with appropriate levels (debug, info, warning, error).