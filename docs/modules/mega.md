# Mega Module

The Mega module provides the `Manipulator` class, which serves as the central orchestration component of the MSB Framework. It manages operations, processes requests, and coordinates interactions between objects and Super classes.

## Abstract Manipulator Class

`Manipulator` is an abstract class for managing and processing operations on objects. It acts as a registry for operations and provides a unified interface for executing complex workflows.

### Key Features

- **Operation Registry**: Register and manage multiple operation handlers
- **Request Processing**: Handle single and batch requests with detailed error handling
- **Method Discovery**: Automatic method registry generation for base classes
- **Facade Methods**: Dynamic facade method creation for simplified operation calls
- **Caching**: LRU caching for method resolution and serialization
- **Type Safety**: Optional strict type checking for objects

### Basic Usage

```python
from msb_arch.mega import Manipulator
from msb_arch.super import Super

class MathOperations(Super):
    OPERATION = "math"

    def _math_add(self, obj, attributes):
        return attributes.get("a", 0) + attributes.get("b", 0)

    def _math_multiply(self, obj, attributes):
        return attributes.get("a", 1) * attributes.get("b", 1)

# Create manipulator
manipulator = Manipulator()

# Register operation
manipulator.register_operation(MathOperations())

# Process requests
result = manipulator.process_request({
    "operation": "math",
    "obj": int,
    "attributes": {"method": "add", "a": 5, "b": 3}
})

print(result)
# {"status": True, "object": None, "method": "_math_add", "result": 8}

# Use facade method (created automatically)
result = manipulator.math(int, a=10, b=4, method="multiply")
print(result)  # 40
```

### Advanced Features

#### Managing Objects

```python
# Set a central managing object
from msb_arch.base import BaseContainer, BaseEntity

class Item(BaseEntity):
    name: str
    value: int

class ItemsContainer(BaseContainer[Item]):
    pass

container = ItemsContainer(name="items")
manipulator.set_managing_object(container)

# Now operations can work on the managing object implicitly
result = manipulator.process_request({
    "operation": "math",
    "attributes": {"method": "add", "a": 1, "b": 2}
})
```

#### Batch Processing

```python
# Process multiple requests
requests = {
    "req1": {
        "operation": "math",
        "attributes": {"method": "add", "a": 1, "b": 2}
    },
    "req2": {
        "operation": "math",
        "attributes": {"method": "multiply", "a": 3, "b": 4}
    }
}

results = manipulator.process_request(requests)
print(results["req1"]["result"])  # 3
print(results["req2"]["result"])  # 12
```

#### Base Class Registration

```python
# Register base classes for method discovery
manipulator = Manipulator(base_classes=[list, dict, str])

# Now methods from these classes are available
result = manipulator.process_request({
    "obj": [1, 2, 3],
    "operation": "custom_operation",  # Assuming operation that uses list methods
    "attributes": {"method": "append", "value": 4}
})
```

### Operation Registration

#### Automatic Registration

```python
class DataProcessor(Super):
    OPERATION = "process"  # Auto-register with this name

processor = DataProcessor()
manipulator.register_operation(processor)  # Uses "process" as operation name
```

#### Manual Registration

```python
manipulator.register_operation(processor, operation="data_process")
```

#### Multiple Operations

```python
class Calculator(Super):
    def _calculate_add(self, obj, attributes):
        return attributes["a"] + attributes["b"]

class Formatter(Super):
    def _format_upper(self, obj, attributes):
        return str(obj).upper()

manipulator.register_operation(Calculator(), operation="calc")
manipulator.register_operation(Formatter(), operation="format")

# Use both operations
add_result = manipulator.calc(a=5, b=3)  # 8
upper_result = manipulator.format(obj="hello")  # "HELLO"
```

### Request Processing

#### Single Request Format

```python
request = {
    "operation": "operation_name",    # Required
    "obj": object_to_process,         # Optional (uses managing object if None)
    "method": "specific_method",      # Optional
    "attributes": {                   # Optional
        "param1": "value1",
        "param2": "value2"
    }
}

result = manipulator.process_request(request)
```

#### Batch Request Format

```python
requests = {
    "request_id_1": { /* single request */ },
    "request_id_2": { /* single request */ }
}

results = manipulator.process_request(requests)
# Returns: {"request_id_1": result1, "request_id_2": result2}
```

### Facade Methods

When you register an operation, Manipulator automatically creates a facade method with the same name:

```python
manipulator.register_operation(MathOperations(), operation="math")

# This creates manipulator.math() method
result = manipulator.math(int, a=1, b=2, method="add")
# Equivalent to:
result = manipulator.process_request({
    "operation": "math",
    "obj": int,
    "attributes": {"a": 1, "b": 2, "method": "add"}
})
```

Facade methods support these parameters:
- `obj`: Object to operate on (optional)
- `method`: Specific method to call (optional)
- `raise_on_error`: If True, raises exceptions; if False, returns dict (default: True)
- Any other keyword arguments become attributes

### Method Registry

Manipulator maintains a registry of available methods for different object types:

```python
# Get methods for a type
methods = manipulator.get_methods_for_type(list)
print(methods.keys())  # ['append', 'extend', 'insert', ...]

# Update registry with new classes
manipulator.update_registry(additional_classes=[set, tuple])
```

### Configuration Options

#### Strict Type Checking

```python
manipulator = Manipulator(strict_type_check=True)
# Will raise errors for unsupported object types
```

#### Cache Size

```python
# In Super classes
super_instance = MathOperations(cache_size=500)  # Default is 2048
```

### Error Handling

Manipulator provides comprehensive error handling:

```python
# Synchronous errors (raise_on_error=True)
try:
    result = manipulator.invalid_operation()
except Exception as e:
    print(f"Error: {e}")

# Asynchronous errors (raise_on_error=False)
result = manipulator.invalid_operation(raise_on_error=False)
if not result["status"]:
    print(f"Error: {result['error']}")
```

Common error scenarios:
- **Operation not registered**: `ValueError`
- **Invalid request format**: `TypeError`
- **Method not found**: `ValueError`
- **Type validation errors**: `TypeError`

### Performance Optimization

#### Caching

- Method resolution results are cached using `lru_cache`
- Super instances can have configurable cache sizes
- Registry updates clear relevant caches

#### Best Practices

1. **Batch Operations**: Use batch requests for multiple operations to reduce overhead.

2. **Facade Methods**: Use facade methods for simple operations instead of full request dictionaries.

3. **Managing Object**: Set a managing object when most operations work on the same object.

4. **Operation Naming**: Use consistent, descriptive operation names.

5. **Error Handling**: Use `raise_on_error=False` for programmatic error handling.

## Integration Patterns

### With Base Classes

```python
from msb_arch.base import BaseEntity, BaseContainer

class User(BaseEntity):
    name: str
    email: str

class UserManager(Super):
    def _manage_create(self, obj, attributes):
        user = User(name=attributes["name"], email=attributes["email"])
        if isinstance(obj, BaseContainer):
            obj.add(user)
        return user

class Users(BaseContainer[User]):
    pass

manipulator = Manipulator()
manipulator.register_operation(UserManager(), operation="user")

users = Users(name="users")
manipulator.set_managing_object(users)

# Create users
manipulator.user(name="Alice", email="alice@example.com")
manipulator.user(name="Bob", email="bob@example.com")
```

### With Projects

```python
from msb_arch.super import Project

class TaskProject(Project):
    def create_item(self, item_code="TASK"):
        return Task(name=f"{item_code}_{len(self._items)+1}")

project = TaskProject(name="tasks")
manipulator.register_operation(project, operation="task")

# Project operations
manipulator.task(method="create_item", item_code="FEATURE")
```

## Response Format

All Manipulator operations return standardized responses:

```python
{
    "status": bool,        # Operation success status
    "object": Any,         # Object identifier/name
    "method": str,         # Executed method name
    "result": Any,         # Operation result (if status=True)
    "error": str           # Error message (if status=False)
}
```

For batch operations, returns a dictionary mapping request IDs to response objects.