# Super Module

The Super module provides operation handling and project management capabilities. It consists of the `Super` abstract base class for operation processing and the `Project` class for managing collections of entities.

## Super Class

`Super` is an abstract super-class providing common functionality for operation handlers. Designed to work with a Manipulator, this class defines a framework for executing operations on objects based on attributes. Subclasses implement specific operations (e.g., configuration, inspection, calculation, etc.) by defining methods with naming conventions like `_<operation>_<type>` or `_<operation>`.

### Attributes

- `_manipulator` (Manipulator): The associated Manipulator instance for method lookup.
- `_methods` (Dict[Type, Dict[str, Callable]]): Custom method registry for specific object types.
- `_method_cache` (OrderedDict): Cache method.
- `_cache_size` (int): Cache size.
- `OPERATION` (str): The operation name, set by Manipulator during registration.

### Notes

- Method resolution order: explicit method, prefixed method (`_<operation>_<method>`), type-specific method (`_<operation>_<type>`), default method (`_<operation>`).
- Logging is integrated via `utils.logging_setup.logger`.
- Results are returned as dictionaries with keys: status (bool), object (str), method (str | None), result (Any), error (str | None, included only if status=False).

### Key Features

- **Method Resolution**: Automatic method lookup with fallback strategies
- **Caching**: Method resolution caching for performance
- **Standardized Responses**: Consistent response format for all operations
- **Nested Operations**: Support for operations on nested objects
- **Extensible**: Easy to subclass for specific operation types

### Method Resolution Order

When executing an operation, `Super` follows this resolution order:

1. Explicit method call (if `method` parameter provided)
2. Prefixed method (`_<operation>_<method>`)
3. Type-specific method (`_<operation>_<object_type>`)
4. Container method (`_<operation>_basecontainer`)
5. Default method (`_<operation>`)

### Basic Usage

```python
from msb_arch.super import Super
from msb_arch.base import BaseEntity

class Calculator(Super):
    _operation = "calculate" # if you don't use manipulator

    def _calculate_add(self, obj, attributes):
        """Add two numbers"""
        a = attributes.get("a", 0)
        b = attributes.get("b", 0)
        return a + b

    def _calculate_multiply(self, obj, attributes):
        """Multiply two numbers"""
        a = attributes.get("a", 1)
        b = attributes.get("b", 1)
        return a * b

# Usage
calc = Calculator()
result = calc.execute(None, {"method": "add", "a": 5, "b": 3})
print(result)
# {"status": True, "object": None, "method": "_calculate_add", "result": 8}
```

### Advanced Features

#### Custom Method Registration

```python
class DataProcessor(Super):
    def __init__(self):
        super().__init__()
        self.register_method(str, "uppercase", lambda s: s.upper())
        self.register_method(list, "length", lambda l: len(l))

processor = DataProcessor()

# Process string
result = processor.execute("hello", {"method": "uppercase"})
print(result["result"])  # "HELLO"

# Process list
result = processor.execute([1, 2, 3], {"method": "length"})
print(result["result"])  # 3
```

#### Nested Operations

```python
class NestedProcessor(Super):
    def _do_nested_get(self, obj, attributes, key, getter_method, nested_handler):
        # Custom nested operation logic
        return self._do_nested(obj, attributes, key, getter_method, nested_handler)

# Usage with containers
from msb_arch.base import BaseContainer, BaseEntity

class Item(BaseEntity):
    name: str
    value: int

class Items(BaseContainer[Item]):
    pass

container = Items(name="items")
container.add(Item(name="item1", value=100))

processor = NestedProcessor()
result = processor.execute(container, {"item": "item1", "operation": "get_value"})
```

## Project Class

`Project` is an abstract class for managing collections of `BaseEntity` objects within a structured project context. It provides high-level operations for project management.

### Key Features

- **Entity Management**: Add, remove, and query project items
- **Bulk Operations**: Activate/deactivate all items, clear project
- **Serialization**: Project-level serialization with all items
- **Validation**: Name validation and type checking
- **Extensible**: Abstract `create_item()` method for custom entity creation

### Basic Usage

```python
from msb_arch.super import Project
from msb_arch.base import BaseEntity

class Task(BaseEntity):
    name: str
    priority: int
    completed: bool = False

class TaskProject(Project):
    _item_type = Task

    def create_item(self, item_code="TASK", isactive=True):
        """Create a new task with default values"""
        return Task(name=f"{item_code}_{len(self._items) + 1}",
                   priority=1, isactive=isactive)

# Create project
project = TaskProject(name="my_tasks")

# Add items
task1 = Task(name="design", priority=2)
project.add_item(task1)
project.create_item("develop")  # Creates and adds automatically

# Query items
high_priority = project.get_active_items()
print(f"Active tasks: {len(high_priority)}")

# Serialize project
project_data = project.to_dict()
print(project_data["name"])  # "my_tasks"
print(len(project_data["items"]))  # 2
```

### Project Operations

#### Item Management

```python
# Add existing item
project.add_item(Task(name="test", priority=1))

# Create and add new item
new_task = project.create_item("review")
project.add_item(new_task)

# Get items
all_tasks = project.get_items()
active_tasks = project.get_active_items()

# Modify items
project.activate_item("design")
project.deactivate_item("test")

# Remove items
project.remove_item("test")
```

#### Bulk Operations

```python
# Activate/deactivate all
project.deactivate_all()
project.activate_all()

# Clear project
project.clear()

# Drop by status
project.drop_active()  # Remove all active items
project.drop_inactive()  # Remove all inactive items
```

#### Project Configuration

```python
# Get project info
info = project.get_project()
print(info["name"])
print(len(info["items"]))

# Set project configuration
new_config = {
    "name": "updated_tasks",
    "items": {
        "task1": {"name": "task1", "priority": 1, "completed": False, "isactive": True, "type": "Task"}
    }
}
project.set_project(**new_config)
```

## Integration with Manipulator

The Super classes work seamlessly with the Manipulator class for complex operation orchestration:

```python
from msb_arch.mega import Manipulator

# Create manipulator
manipulator = Manipulator()

# Register operations
manipulator.register_operation(Calculator())
manipulator.set_managing_object(TaskProject(name="tasks"))

# Process requests
result = manipulator.process_request({
    "operation": "calculate",
    "attributes": {"method": "add", "a": 10, "b": 20}
})

print(result["result"])  # 30
```

## Best Practices

1. **Naming Conventions**: Use clear operation names and follow the `_<operation>_<method>` pattern for methods.

2. **Error Handling**: Always return standardized response dictionaries with proper status and error information.

3. **Caching**: Enable caching for frequently used operations to improve performance.

4. **Type Safety**: Use specific types in method signatures for better validation.

5. **Documentation**: Document all operation methods with clear docstrings.

## Response Format

All Super operations return responses in this format:

```python
{
    "status": bool,        # True if successful, False otherwise
    "object": Any,         # Name or identifier of the processed object
    "method": str,         # Name of the method that was executed
    "result": Any,         # Result of the operation (if status=True)
    "error": str           # Error message (if status=False)
}
```

## Error Handling

- **ValueError**: Invalid parameters or method not found
- **TypeError**: Type mismatches in operation parameters
- **AttributeError**: Missing required attributes
- **KeyError**: Object not found in collections

All errors are logged and returned in the standardized response format.