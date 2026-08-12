# Super module

A `Super` is an operation. Subclass it, name the operation, and write handlers; the orchestrator
picks the handler by operation and by the type of the object.

This page also covers `Project`, a named collection of entities with a factory.

## The class

| | |
| --- | --- |
| `OPERATION` | The operation's name. Set it on the class, or pass a name to `register_operation` |
| `_manipulator` | Whatever drives it. Anything answering `get_methods_for_type` will do |
| `_methods` | Methods registered on this instance for a type, tried before the manipulator's |
| `execute(obj, attributes, method)` | Resolves a handler and runs it. The manipulator calls this |

Handlers are named `_<operation>` or `_<operation>_<something>`. Nothing else is reachable: the
name arrives inside a request, so allowing any method would let a caller invoke anything on the
instance.

### How a handler is chosen

1. The requested name, if it already denotes a handler of this operation
2. `_<operation>_<name>` -- the name a request asked for
3. `_<operation>_<type>` -- the type of the object, lower-cased
4. `_<operation>_basecontainer` -- for any container
5. `_<operation>` -- the fallback

A request naming something outside the operation falls through to a more general handler rather
than reaching it.

## The built-in operations

Five are registered for you, in `msb_arch.super.builtins`:

| Class | Operation | What it does |
| --- | --- | --- |
| `Inspector` | `inspect` | Applies the methods a request names, reporting every outcome |
| `Configurator` | `configure` | The same, stopping at the first failure |
| `Catalogue` | `catalogue` | What is registered, and the shape of the model |
| `Persistence` | `save` | Writes an object to a file as JSON, atomically |
| `Loader` | `load` | Reads one back |

Each is thin -- usually one call to `_apply_methods` -- so subclassing one to change the
behaviour for a single type leaves the rest working:

```python
from msb_arch import BaseEntity, Configurator, Manipulator, RequestError

class Widget(BaseEntity):
    price: float

    def set_price(self, value: float) -> bool:
        self.price = value
        return True

class Careful(Configurator):
    def _configure_widget(self, obj, attributes):
        if attributes.get("set_price", 0) > 100:
            raise RequestError("too expensive")
        return self._apply_methods(obj, attributes, strict=True)

class Workshop(Manipulator):
    pass

workshop = Workshop(base_classes=[Widget])
workshop.register_operation(Careful(workshop), operation="configure")

widget = Widget(name="hinge", price=5.0)
assert workshop.configure(widget, set_price=500.0, raise_on_error=False)["status"] is False
assert widget.price == 5.0
```

Registering over a built-in replaces it silently, since it is a default rather than a collision.

A handler refuses by raising, not by returning a failed response: `execute` wraps whatever a
handler returns, so a returned failure ends up as the successful result of a request. Raise one
of MSB's own errors and the kind survives to the caller.

## Writing your own Super

A subclass supplies handlers and builds them out of the helpers below. They carry a single
underscore in the sense the language intends, **protected rather than private**: the
framework never calls them, your handlers do. They are part of the contract, and their
signatures will not change without a major version.

| Helper | Purpose |
| --- | --- |
| `_apply_methods(obj, attributes, valid_methods, extra_args, strict)` | Apply every method the request named and report each outcome. **Start here**: it is the whole body of most handlers |
| `_build_response(obj, status, method, result, error)` | Produce the response dictionary a handler returns |
| `_get_methods(obj_type)` | Methods registered for a type, from this instance first, then the Manipulator |
| `_validate_and_apply_method(obj, name, args, valid_methods, extra_args)` | Apply one method. Use it when a handler needs finer control than `_apply_methods` |
| `_do_nested(obj, attributes, key, getter, handler)` | Descend into a member of a container and run a handler on it |
| `register_method(obj_type, name, method)` | Add a method for a type at run time |

### The result protocol

`_apply_methods` returns a `MethodResults`: a mapping of method name to
`{"status", "result"}`, with `"error"` added where one failed. The shape does not depend on
how many methods the request named, which is what lets a request history record and replay
exactly what happened.

The examples from here on run against this setup:

```python
from msb_arch import BaseEntity, Manipulator, Super

class Widget(BaseEntity):
    price: float

    def get_code(self) -> str:
        return self.name

    def get_price(self) -> float:
        return self.price

    def set_price(self, value: float) -> bool:
        self.price = value
        return True

class Inspector(Super):
    OPERATION = "inspect"

    def _inspect(self, obj, attributes):
        return self._apply_methods(obj, attributes)

class Workshop(Manipulator):
    pass

manipulator = Workshop(base_classes=[Widget])
manipulator.register_operation(Inspector(manipulator))
widget = Widget(name="T1", price=25.0)
```

```python
results = manipulator.process_request({
    "operation": "inspect", "obj": widget,
    "attributes": {"get_code": None, "get_price": None},
})["result"]

assert results == {
    "get_code":     {"status": True, "result": "T1"},
    "get_price": {"status": True, "result": 25.0},
}
```

The facade is sugar, so it unwraps the common case: a request naming exactly one method
gives back that value rather than a mapping of one.

```python
assert manipulator.inspect(widget, get_code=None) == "T1"

both = manipulator.inspect(widget, get_code=None, get_price=None)
assert both["get_price"]["result"] == 25.0        # a mapping, not a value
```

`strict=True`, the default, stops at the first failed method and lets `execute` turn it into
a failed response. `strict=False` attempts every method and records what each did, which is
what you want when a caller needs the whole picture rather than the first problem.

A handler is named `_<operation>_<type>` for a specific type, or `_<operation>` as the
fallback, takes `(obj, attributes)` and returns whatever the operation produces; `execute`
wraps that in the standard response.

```python
class Configurator(Super):
    OPERATION = "configure"

    def _configure_widget(self, obj, attributes):
        # a type-specific handler: reached for any object whose class is Widget
        return self._apply_methods(obj, attributes)

    def _configure(self, obj, attributes):
        # the fallback, reached when no more specific handler matches
        return self._apply_methods(obj, attributes)
```

A handler that needs to return something of its own still can; `_apply_methods` is then
used for its effect and the handler decides what comes back.

```python
class ReturningConfigurator(Super):
    OPERATION = "configure"

    def _configure_widget(self, obj, attributes):
        self._apply_methods(obj, attributes)
        return obj.get_price()          # the handler decides what comes back

manipulator.register_operation(ReturningConfigurator(manipulator))
assert manipulator.configure(widget, set_price=30.0) == 30.0
```

Handlers may of course call each other directly. Only the entry point goes through
`execute`, so a helper such as `_generate_observations` does not need to follow the naming
convention as long as one of the handlers calls it.

### A worked example

The operation name comes from `OPERATION`. A `Super` can be driven directly, without a
`Manipulator`, as long as that is set: `__init__` copies it to `_operation`, so assigning
`_operation` on the class instead is overwritten and leaves the instance with no operation.

```python
from msb_arch.super import Super

class Calculator(Super):
    OPERATION = "calculate"

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

calc = Calculator()
result = calc.execute(None, {"method": "add", "a": 5, "b": 3})
assert result["status"] is True
assert result["result"] == 8
```

### Registering a method for a type at run time

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

### Descending into a container

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

### A worked example

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

### Items

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

### In bulk

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

### Reading and writing the whole project

```python
# Get project info
info = project.get_project()
print(info["name"])
print(len(info["items"]))

# Set project configuration. Note the asymmetry: `get_project` reports items as serialized
# mappings, while `set_project` takes the entities themselves, so the two do not compose.
project.set_project(name="updated_tasks",
                    items={"task1": Task(name="task1", priority=1)})
assert project.name == "updated_tasks"
```

## Integration with Manipulator

The Super classes work seamlessly with the Manipulator class for complex operation orchestration:

```python
from msb_arch.mega import Manipulator

class Workbench(Manipulator):
    pass

bench = Workbench(base_classes=[Task])
bench.register_operation(Calculator(bench))
bench.set_managing_object(TaskProject(name="tasks"))

result = bench.process_request({
    "operation": "calculate",
    "attributes": {"method": "add", "a": 10, "b": 20}
})

assert result["result"] == 30
```

## The response

Every handler answers in the same shape, which is what makes a session replayable:

```text
{
    "status": bool,
    "object": Any,         # the object's name
    "method": str,         # the handler that ran
    "result": Any,         # when status is True
    "error": str,          # when status is False
    "error_type": str,     # when status is False: the exception class's name
}
```

`_build_response` produces it. `_apply_methods` produces `MethodResults`, which is that shape per
method named.

## Errors a handler meets

| Error | When |
| --- | --- |
| `RequestError` | The request asked for something that cannot be done: no methods named, no path |
| `DispatchError` | No handler could be resolved for the operation and the object |
| `HandlerError` | A method failed while `strict=True`, or a handler raised something else |
| `NotFoundError` | A named item or file is not there |

Raising one of MSB's own errors from a handler is worth the two extra characters: the type
survives the response boundary, so a facade re-raises the same kind rather than flattening
everything into `HandlerError`.
