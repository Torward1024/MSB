# API reference

This document provides a complete API reference for the MSB Framework.

## Base Module

### BaseEntity

Abstract base class for entities with type validation and serialization.

#### Constructor

```python
BaseEntity(name: str, isactive: bool = True, use_cache: bool = False, **kwargs)
```

**Parameters:**
- `name` (str): Entity identifier (required, cannot be None)
- `isactive` (bool): Activation status (default: True)
- `use_cache` (bool): Enable caching for serialization (default: False)
- `**kwargs`: Additional attributes defined in type annotations

**Raises:** `TypeError`, `ValueError`

#### Methods

##### `set(params: Dict[str, Any]) -> None`

Update multiple attributes with validation.

**Parameters:**
- `params` (Dict[str, Any]): Attributes to update

**Raises:** `ValueError`, `TypeError`

##### `get(key: Union[str, List[str], None] = None) -> Union[Any, Dict[str, Any]]`

Retrieve attribute(s).

**Parameters:**
- `key` (str, List[str], or None): Attribute name(s) to retrieve

**Returns:** Attribute value, dict of values, or all public attributes

**Raises:** `KeyError`

##### `activate() -> None`

Set entity as active.

##### `deactivate() -> None`

Set entity as inactive.

##### `clone() -> BaseEntity`

Create a deep copy of the entity.

**Returns:** New entity instance

##### `to_dict() -> dict`

Serialize entity to dictionary.

**Returns:** Serialized dictionary

##### `from_dict(data: dict) -> BaseEntity` (classmethod)

Create entity from dictionary.

**Parameters:**
- `data` (dict): Serialized data

**Returns:** New entity instance

**Raises:** `TypeError`, `ValueError`

##### `revision -> int` (property)

How many times this object has been written to. 0 for one nobody has changed. About this object,
not what it holds, and not serialized.

##### `fingerprint() -> str`

A hash of everything this object holds, itself and below. Sixteen hexadecimal characters; equal
contents give equal strings.

##### `has_attribute(key: str) -> bool`

Check if attribute exists.

**Parameters:**
- `key` (str): Attribute name

**Returns:** True if attribute exists and is set

##### `clear() -> None`

Clear all non-internal attributes to release references.

##### `__getitem__(key: str) -> Any`

Access an attribute using dictionary-like syntax.

**Parameters:**
- `key` (str): Attribute name

**Returns:** Attribute value

**Raises:** `KeyError`

##### `__setitem__(key: str, value: Any) -> None`

Set an attribute using dictionary-like syntax.

**Parameters:**
- `key` (str): Attribute name
- `value` (Any): Value to set

**Raises:** `KeyError`, `TypeError`

##### `__contains__(key: str) -> bool`

Check if attribute exists using 'in' operator.

**Parameters:**
- `key` (str): Attribute name

**Returns:** True if attribute exists

##### `_use_cache() -> bool`

Get current cache usage setting.

**Returns:** True if caching is enabled

##### `_cached_to_dict() -> dict`

Get cached dictionary representation if available.

**Returns:** Cached dictionary or None

### BaseContainer[T]

Generic container for managing collections of BaseEntity objects.

#### Constructor

```python
BaseContainer(items: Dict[str, T] = None, name: str = None, isactive: bool = True, use_cache: bool = False)
```

**Parameters:**
- `items` (Dict[str, T]): Initial items dictionary
- `name` (str): Container identifier
- `isactive` (bool): Activation status
- `use_cache` (bool): Enable caching

#### Methods

##### `add(item: Union[T, List[T], BaseContainer[T]], copy_items: bool = True) -> None`

Add item(s) to container.

**Parameters:**
- `item`: Single item, list of items, or another container
- `copy_items` (bool): Whether to deep copy items

##### `set_item(name: str, item: T) -> None`

Set/replace item by name.

**Parameters:**
- `name` (str): Item name
- `item` (T): Item to set

##### `remove(name: str) -> None`

Remove item by name.

**Parameters:**
- `name` (str): Item name to remove

##### `get(name: str) -> Optional[T]`

Get item by name.

**Parameters:**
- `name` (str): Item name

**Returns:** Item or None

##### `get_all() -> Dict[str, T]`

Get all items as dictionary.

**Returns:** Dictionary of all items

##### `get_items() -> List[T]`

Get all items as list.

**Returns:** List of all items

##### `get_active_items() -> List[T]`

Get only active items.

**Returns:** List of active items

##### `get_inactive_items() -> List[T]`

Get only inactive items.

**Returns:** List of inactive items

##### `get_by_value(conditions: Dict[str, Any]) -> List[T]`

Query items by attribute values.

**Parameters:**
- `conditions` (Dict[str, Any]): Attribute conditions

**Returns:** Matching items

##### `set_items(items: Dict[str, T]) -> None`

Set or replace all items in the container.

**Parameters:**
- `items` (Dict[str, T]): Items to set

**Raises:** `ValueError`, `TypeError`

##### `clear() -> None`

Remove all items.

##### `clone(deep: bool = True) -> BaseContainer[T]`

Create container copy.

**Parameters:**
- `deep` (bool): Deep copy items

**Returns:** New container

##### `activate_item(name: str) -> None`

Activate specific item.

**Parameters:**
- `name` (str): Item name

##### `deactivate_item(name: str) -> None`

Deactivate specific item.

**Parameters:**
- `name` (str): Item name

##### `activate_all() -> None`

Activate all items.

##### `deactivate_all() -> None`

Deactivate all items.

##### `drop_active() -> None`

Remove all active items.

##### `drop_inactive() -> None`

Remove all inactive items.

##### `has_item(name: str) -> bool`

Check if item exists.

**Parameters:**
- `name` (str): Item name

**Returns:** True if exists

##### `to_dict(handle_cyclic_refs: str = "mark") -> dict`

Serialize container to dictionary.

**Parameters:**
- `handle_cyclic_refs` (str): How to handle cycles ("mark", "ignore", "raise")

**Returns:** Serialized dictionary

**Notes:**
- Cycles of any length are detected. The second visit to an entity within one call is
  replaced with `CYCLIC_REFERENCE`, skipped, or reported, according to the parameter.
- With `use_cache=True` the same mapping is returned on every call. Treat it as read only
  and copy it before making changes, or the cache is corrupted.

##### `from_dict(data: dict) -> BaseContainer` (classmethod)

Create container from dictionary.

**Parameters:**
- `data` (dict): Serialized data

**Returns:** New container

**Raises:** `TypeError`, `ValueError`

## Super Module

### Super

Abstract base class for operation handlers.

#### Constructor

```python
Super(manipulator: Manipulator = None, methods: Optional[Dict[Type, Dict[str, Callable]]] = None, cache_size: int = 2048)
```

**Parameters:**
- `manipulator` (Manipulator): Associated manipulator
- `methods` (Optional[Dict]): Custom method registry
- `cache_size` (int): Method cache size

#### Methods

##### `execute(obj: Any, attributes: Dict[str, Any] = None, method: str = None) -> Dict[str, Any]`

Execute operation on object.

**Parameters:**
- `obj` (Any): Target object
- `attributes` (Dict): Operation attributes
- `method` (str): Specific method to call

**Returns:** Response dictionary

##### `register_method(obj_type: Type, method_name: str, method: Callable) -> None`

Register custom method for type.

**Parameters:**
- `obj_type` (Type): Object type
- `method_name` (str): Method name
- `method` (Callable): Method function

##### `clear_cache() -> None`

Clear the method cache.

##### `clear() -> None`

Clear all references for cleanup.

### The built-in operations

In `msb_arch.super.builtins`. All are registered by a `Manipulator` unless `builtins=False`.

| Class | `OPERATION` | Handlers |
| --- | --- | --- |
| `Inspector` | `inspect` | `_inspect` |
| `Configurator` | `configure` | `_configure` |
| `Catalogue` | `catalogue` | `_catalogue`, `_catalogue_order`, `_catalogue_model` |
| `Persistence` | `save` | `_save` |
| `Loader` | `load` | `_load` |

`save` takes `path`, and optionally `indent` (4) and `overwrite` (True); it answers
`{"path": str}`. `load` takes `path`, and optionally `kind` — a class or its name — and answers
with the object itself.

`Inspector` and `Configurator` both take `NESTED_KEY` (`"name"`) to address one member of a
collection, and both have a `_nested_getter(obj)` hook returning how to fetch a member.

### PipelineRun

What `pipeline` and `replay` return. A `dict` of responses keyed as the plan keyed its steps.

| | |
| --- | --- |
| `output` | What the last step produced |
| `of(name)` | What one step produced. Raises `NotFoundError` if it produced nothing |
| `failed` | The names of the steps that did not succeed |

### Project

Abstract base class for managing entity projects.

#### Constructor

```python
Project(name: str, items: Dict[str, BaseEntity] = None)
```

**Parameters:**
- `name` (str): Project name
- `items` (Dict): Initial items

#### Methods

##### `add_item(item: BaseEntity) -> None`

Add item to project.

**Parameters:**
- `item` (BaseEntity): Item to add

##### `create_item(item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None` (abstractmethod)

Create new item (must be implemented by subclasses).

##### `set_item(name: str, item: BaseEntity) -> None`

Set/replace item by name.

##### `remove_item(name: str) -> None`

Remove item by name.

##### `get_item(name: str) -> BaseEntity`

Get item by name.

**Returns:** Item instance

##### `get_items() -> Dict[str, BaseEntity]`

Get all items.

**Returns:** Items dictionary

##### `get_active_items() -> List[T]`

Get active items.

**Returns:** List of active items

##### `get_inactive_items() -> List[T]`

Get inactive items.

**Returns:** List of inactive items

##### `activate_item(name: str) -> None`

Activate specific item.

##### `deactivate_item(name: str) -> None`

Deactivate specific item.

##### `activate_all() -> None`

Activate all items.

##### `deactivate_all() -> None`

Deactivate all items.

##### `drop_active() -> None`

Remove active items.

##### `drop_inactive() -> None`

Remove inactive items.

##### `to_dict() -> Dict[str, Any]`

Serialize project.

**Returns:** Serialized dictionary

##### `from_dict(data: Dict[str, Any]) -> Project` (classmethod)

Create project from dictionary.

**Parameters:**
- `data` (Dict): Serialized data

**Returns:** New project

##### `clear() -> None`

Clear all items.

## Mega Module

### Manipulator

Central orchestrator for operations and objects.

#### Constructor

```python
Manipulator(managing_object: Optional[Any] = None, base_classes: Optional[List[Type]] = None,
            operations: Optional[Dict[str, Callable]] = None, strict_type_check: bool = False,
            builtins: bool = True, max_workers: Optional[int] = None)
```

**Parameters:**
- `managing_object` (Optional[Any]): Default object for operations
- `base_classes` (Optional[List[Type]]): Base classes for method discovery
- `operations` (Optional[Dict]): Initial operations
- `strict_type_check` (bool): Enforce strict typing
- `builtins` (bool): Register `inspect`, `configure`, `catalogue`, `save` and `load`
- `max_workers` (Optional[int]): Size of the executor the asynchronous surface uses

#### Methods

##### `set_managing_object(obj: Any) -> None`

Set default managing object.

**Parameters:**
- `obj` (Any): Object to set

##### `get_managing_object() -> Optional[Any]`

Get current managing object.

**Returns:** Managing object or None

##### `register_operation(super_instance: Callable, operation: Optional[str] = None) -> None`

Register operation handler.

**Parameters:**
- `super_instance` (Callable): Super instance with execute method
- `operation` (Optional[str]): Operation name (auto from OPERATION if None)

**Raises:** `ValueError`

##### `process_request(request: Dict[str, Any]) -> Dict[str, Any]`

Process single or batch request.

**Parameters:**
- `request` (Dict[str, Any]): Request specification

**Returns:** Response dictionary

**Raises:** `TypeError`, `ValueError`

##### `get_methods_for_type(obj_type: Type) -> Dict[str, Callable]`

Get methods for object type.

**Parameters:**
- `obj_type` (Type): Object type

**Returns:** Methods dictionary

**Raises:** `ValueError`

##### `update_registry(additional_classes: Optional[List[Type]] = None, clear_operations: bool = False) -> None`

Update method registry.

**Parameters:**
- `additional_classes` (Optional[List[Type]]): Additional classes
- `clear_operations` (bool): Clear existing operations

##### `batch(requests, raise_on_error: bool = False) -> Dict[str, Any]`

Run several requests in order and report the outcome of each.

**Parameters:**
- `requests` (Sequence[dict] or Dict[str, dict]): Requests to run. A sequence is numbered
  from zero; a mapping keeps the identifiers you chose.
- `raise_on_error` (bool): Raise as soon as a request fails. Off by default, since a report
  is the point of a batch.

**Returns:** Identifier mapped to the response of that request

**Notes:**
- Sugar over the sequence form of `process_request`, as the per-operation facades are sugar
  over its single form.
- Requests are independent: nothing feeds the result of one into the next. For steps that do,
  use `pipeline`.

##### `register_deferred(operation: str, factory: Callable[[], Super]) -> None`

Register an operation whose `Super` is built the first time it is needed.

**Parameters:**
- `operation` (str): The operation's name
- `factory` (Callable): Called once, with no arguments, to build the `Super`. Import inside it

**Raises:** `RegistrationError` for the same reasons `register_operation` raises, and if the
factory is not callable

The operation counts as registered immediately: it appears in `get_supported_operations()`, it
has a facade, and a pipeline may name it. It is built by the first request that needs it, or by
`describe_operations`, `order_handlers` or `requirements_of`, which read its handlers.

##### `warm(operations: Optional[List[str]] = None) -> List[str]`

Build every deferred operation now, or only the ones named. Returns the names built by this
call. Safe from any thread; a caller that asks meanwhile waits rather than building a second
instance.

##### `pipeline(plan=None, raise_on_error=True, concurrent=False, name=None) -> Any`

Run several requests that feed each other, or return a draft when no plan is given.

**Parameters:**
- `plan` (Optional[Union[Dict, Sequence]]): Steps keyed by name, or a sequence of them
- `raise_on_error` (bool): Raise on the first failure, or record it and skip its branch
- `concurrent` (bool): Run each stage's independent steps together
- `name` (Optional[str]): What to call a draft

**Returns:** `PipelineRun` — the response of every step — or a draft

**Raises:** `RequestError` for a malformed plan, a missing reference or a cycle;
`DispatchError` for an unregistered operation

##### `apipeline(plan, raise_on_error=True) -> PipelineRun` (coroutine)

The same from inside an event loop. Always concurrent within a stage.

##### `describe_operations(operation=None, interpret=None, acronyms=None) -> Dict[str, Any]`

What is registered: per operation, each handler with `requires`, `calls`, `touches` and `label`.

##### `order_handlers(operation: str, names: List[str]) -> List[str]`

The named handlers, each after the ones it needs that were also asked for.

##### `requirements_of(operation: str, name: str) -> List[str]`

Everything a handler needs, directly or through what it needs.

##### `describe_model(roots=None) -> Dict[str, Any]`

The model graph: `{type: {"holds": {field: [type]}, "held_by": {type: [field]}, "container": bool}}`.

##### `dependents_of(name: str, roots=None) -> List[str]`

Every type that would feel a change to this one. Sorted, transitive.

##### `scaffold(operation: str, roots=None, only=None) -> str`

Python source: a `Super` with one handler per type in the model.

##### `journal() -> Optional[RequestJournal]`

The journal registered as an interceptor, if there is one.

##### `history(name=None, changed_only=False) -> List[Dict[str, Any]]`

What has been requested in this session, optionally about one object, optionally only the
requests that changed something.

**Raises:** `NotFoundError` if no journal is registered

##### `metrics() -> Optional[Dict[str, Dict[str, Any]]]`

What `RequestMetrics.snapshot()` reports, or None if none is registered.

##### `replay(journal=None, skip_failures=True, concurrent=False) -> PipelineRun`

Run a recorded session again, as a pipeline.

##### `add_interceptor(interceptor) -> None`, `remove_interceptor(interceptor) -> None`, `get_interceptors() -> List`

Manage the chain that wraps every request. The first added is the outermost.

##### `close() -> None`

Shut down the executor. Also happens on exit from the manipulator as a context manager.

##### `get_supported_operations() -> List[str]`

Get list of supported operations.

**Returns:** List of operation names

##### `clear_cache() -> None`

Clear method resolution cache.

##### `clear_base_classes() -> None`

Clear base classes registry.

##### `clear_ops() -> None`

Clear all operations.

## Utils Module

### Logging Setup

#### `setup_logging(log_file: str = "output.log", log_level: int = logging.INFO, clear_log: bool = False) -> logging.Logger`

Attach file and console handlers to the `msb_arch` logger.

**Parameters:**
- `log_file` (str): Log file path
- `log_level` (int): Logging level
- `clear_log` (bool): Clear log file

**Returns:** Logger instance

**Notes:**
- Optional and never called on import. MSB logs to a `msb_arch` logger carrying only a
  `NullHandler`, so it neither writes files nor touches the root logger by itself.
- Configuring `logging` in the application works just as well; this helper only exists for
  the common case.

#### `update_logging_level(log_level: int) -> None`

Update logging level.

**Parameters:**
- `log_level` (int): New logging level

#### `update_logging_clear(log_file: str, clear_log: bool) -> None`

Update log clearing behavior.

**Parameters:**
- `log_file` (str): Log file path
- `clear_log` (bool): Clear log file

### Validation Functions

#### `check_type(value, expected_type, name: str) -> None`

Validate value type.

**Parameters:**
- `value`: Value to check
- `expected_type`: Expected type
- `name` (str): Parameter name

**Raises:** `TypeError`

#### `check_range(value: float, min_val: float, max_val: float, name: str) -> None`

Validate numeric range.

**Parameters:**
- `value` (float): Value to check
- `min_val` (float): Minimum value
- `max_val` (float): Maximum value
- `name` (str): Parameter name

**Raises:** `TypeError`, `ValueError`

#### `check_positive(value: float, name: str) -> None`

Validate positive value.

**Parameters:**
- `value` (float): Value to check
- `name` (str): Parameter name

**Raises:** `TypeError`, `ValueError`

#### `check_non_negative(value: float, name: str) -> None`

Validate non-negative value.

**Parameters:**
- `value` (float): Value to check
- `name` (str): Parameter name

**Raises:** `TypeError`, `ValueError`

#### `check_non_empty_string(value: str, name: str) -> None`

Validate non-empty string.

**Parameters:**
- `value` (str): String to check
- `name` (str): Parameter name

**Raises:** `TypeError`, `ValueError`

#### `check_list_type(lst: list, expected_type, name: str) -> None`

Validate list element types.

**Parameters:**
- `lst` (list): List to check
- `expected_type`: Expected element type
- `name` (str): Parameter name

**Raises:** `TypeError`

#### `check_non_zero(value: float, name: str) -> None`

Validate non-zero value.

**Parameters:**
- `value` (float): Value to check
- `name` (str): Parameter name

**Raises:** `TypeError`, `ValueError`

#### `update_logging_level(log_level: int) -> None`

Update the logging level for the singleton logger.

**Parameters:**
- `log_level` (int): New logging level

#### `update_logging_clear(log_file: str, clear_log: bool) -> None`

Update logging configuration to clear the log file.

**Parameters:**
- `log_file` (str): Path to the log file
- `clear_log` (bool): Whether to clear the log file

## Response Formats

### Standard Response

All operations return responses in this format:

```python
{
    "status": bool,        # Operation success
    "object": Any,         # Target object name/id
    "method": str,         # Executed method name
    "result": Any,         # Operation result (if status=True)
    "error": str           # Error message (if status=False)
}
```

### Batch Response

Batch operations return dictionaries mapping request IDs to responses:

```python
{
    "request_id_1": { /* response dict */ },
    "request_id_2": { /* response dict */ }
}
```

## Exception Hierarchy

Everything MSB raises lives in `msb_arch.errors` and is exported from `msb_arch`. Each type
derives from `MSBError` **and** from the built-in it replaces, so `except TypeError` and
`except ValueError` written against earlier versions keep catching exactly what they caught.

```text
MSBError                          anything from the framework
├── ValidationError               the data given to MSB is wrong   (grouping only)
│   ├── TypeValidationError       a value does not match its annotation      (TypeError)
│   ├── ConstraintError           a value fails a value constraint           (ValueError)
│   ├── UnknownAttributeError     an attribute that was never declared       (ValueError)
│   └── ItemNameError             an item's name is unusable in a container  (ValueError)
│       └── DuplicateNameError    ...because something already has it
├── ResolutionError               a type could not be resolved               (TypeError)
├── NotFoundError                 a name was looked up and is not there      (KeyError)
│   └── AttributeNotFoundError    ...and the name was an attribute      (+ AttributeError)
├── SerializationError            a round trip failed          (ValueError and TypeError)
└── OperationError                the operation layer              (grouping only)
    ├── RegistrationError         an operation was registered wrongly        (ValueError)
    ├── DispatchError             nothing can serve this object              (ValueError)
    ├── RequestError              the request is malformed     (ValueError and TypeError)
    └── HandlerError              a handler ran and failed                 (RuntimeError)
```

The built-in each one answers to is in the right-hand column. Three levels let a caller be
as broad or as narrow as it wants:

```python
from msb_arch import MSBError, ValidationError, DuplicateNameError

try:
    ...
except DuplicateNameError:      # exactly this
    ...
except ValidationError:         # anything the caller got wrong
    ...
except MSBError:                # anything from the framework
    ...
```

`ValidationError` and `OperationError` group and are never raised on their own.
`SerializationError` and `RequestError` each derive from two built-ins, because the sites
they replace did not agree on one: a malformed request was a `TypeError` when it was not a
dictionary and a `ValueError` when it was the wrong dictionary.

`HandlerError` carries the original exception as its cause where the framework still holds
it, which is the case in `_apply_methods(strict=True)`. Once a failure has crossed into a
response it is only a message, so a facade raising with `raise_on_error=True` has no cause
to attach.

Method docstrings name the built-in base rather than the specific type, and remain accurate:
a `TypeValidationError` is a `TypeError`.

`NotImplementedError` is still raised directly for abstract methods that were not
implemented, since that is Python's contract rather than MSB's.

## Type Annotations

The framework uses comprehensive type hints:

- `T`: Generic type variable for BaseEntity subclasses
- `Union[A, B]`, `A | B`: Alternative types
- `Optional[T]`: Optional types (Union[T, None])
- `List[T]`, `Set[T]`, `FrozenSet[T]`: Collections of specific types
- `Tuple[A, B]`, `Tuple[T, ...]`: Fixed-length and variadic tuples
- `Dict[K, V]`: Dictionaries with key/value types
- `Literal[...]`: A fixed set of allowed values
- `Type[T]`: Class objects constrained to a subclass of T
- `Callable`: Function types

Entity attributes are validated structurally against these hints, nested to any depth.
See [Type Validation](modules/base.md#type-validation-_validate_type) for the full table.

## Constants

- `logging.DEBUG`, `logging.INFO`, `logging.WARNING`, `logging.ERROR`: Log levels
- `inspect.Parameter.empty`: Empty parameter default
- `ABC`: Abstract base class marker
