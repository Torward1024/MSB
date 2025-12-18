# Base Module

The Base module provides the fundamental building blocks for the MSB Framework: `BaseEntity` and `BaseContainer`. These classes form the core data management layer.

## BaseEntity

`BaseEntity` is an abstract base class that provides attribute management, type validation, serialization, and common entity functionality.

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

address = Address(street="123 Main St", city="Anytown")
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
from typing import List

class Product(BaseEntity):
    name: str
    price: float
    category: str

# Create typed container
inventory = BaseContainer[Product](name="product_inventory")

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

expensive = inventory.get_by_value({"price": lambda x: x > 20})
print(len(expensive))  # 1
```

### Advanced Operations

#### Bulk Operations

```python
# Add from another container
more_products = BaseContainer[Product](name="more_products")
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
| `get_items()` | Get all items as list |
| `get_active_items()` | Get only active items |
| `clear()` | Remove all items |
| `clone()` | Create deep copy |

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

## Best Practices

1. **Define Clear Type Annotations**: Use specific types in your entity classes for better validation.

2. **Use Meaningful Names**: Entity names should be unique within containers.

3. **Handle Serialization Carefully**: Be aware of cyclic references when nesting entities.

4. **Leverage Container Queries**: Use `get_by_value()` for complex filtering instead of manual loops.

5. **Enable Caching**: Use `use_cache=True` for entities that are serialized frequently.

## Error Handling

The Base module raises specific exceptions:

- `TypeError`: When attribute types don't match annotations
- `ValueError`: When validation rules are violated
- `KeyError`: When accessing non-existent attributes

All operations are logged with appropriate levels (debug, info, warning, error).