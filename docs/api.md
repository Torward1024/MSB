# API reference

Every public class and method, with what it takes and what it answers. For *why* any of it is
shaped this way, read the [guide](guide.md) first; for what will not break, read
[compatibility](COMPATIBILITY.md).

| | |
| --- | --- |
| [Base](#base-module) | `BaseEntity`, `BaseContainer[T]`, the read-only cached mapping |
| [Super](#super-module) | `Super`, the built-in operations, `Response` and the result types, `Project` |
| [Mega](#mega-module) | `Manipulator`: requests, batches, pipelines, derivation, addressing, replay |
| [Interceptors](#interceptors-and-protocols) | The hook, `RequestMetrics`, `RequestJournal`, the protocols |
| [Utils](#utils-module) | Logging and the validation helpers |
| [Errors](#exception-hierarchy) | The taxonomy, and the built-in each type answers to |

## Base module

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

**Returns:** Serialized dictionary. A `ReadOnlyMapping` when the object caches — see below.

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

##### `reset_attributes() -> None`

Set every public attribute to None, releasing what it referred to. `name`, `isactive` and
underscore-prefixed fields are kept. The object stays usable.

##### `clear() -> None`

Deprecated in 1.9.0, goes in 2.0 — use `reset_attributes()`.

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

##### Reading the whole collection

| | |
| --- | --- |
| `get_all() -> Dict[str, T]` | Every item, keyed by name |
| `get_items() -> List[T]` | Every item |
| `get_active_items() -> List[T]` | Only the active ones |
| `get_inactive_items() -> List[T]` | Only the inactive ones |
| `has_item(name) -> bool` | Whether that name is here |
| `__len__`, `__iter__`, `__contains__` | Count, iterate, test by name |

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

##### `remove_all() -> None`

Remove every item. The container keeps its name, type and settings.

##### `clear() -> None`

Deprecated in 1.9.0, goes in 2.0 — use `remove_all()`.

##### `clone(deep: bool = True) -> BaseContainer[T]`

Create container copy.

**Parameters:**
- `deep` (bool): Deep copy items

**Returns:** New container

##### Activation

`isactive` is a flag on the item, and a container both reads it and sets it in bulk.

| | |
| --- | --- |
| `activate_item(name)`, `deactivate_item(name)` | One item |
| `activate_all()`, `deactivate_all()` | Every item |
| `drop_active()`, `drop_inactive()` | Remove by that flag |

##### `to_dict(handle_cyclic_refs: str = "mark") -> dict`

Serialize container to dictionary.

**Parameters:**
- `handle_cyclic_refs` (str): How to handle cycles ("mark", "ignore", "raise")

**Returns:** Serialized dictionary

**Notes:**
- Cycles of any length are detected. The second visit to an entity within one call is
  replaced with `CYCLIC_REFERENCE`, skipped, or reported, according to the parameter.
- With `use_cache=True` the same mapping is returned on every call, so it comes back as a
  `ReadOnlyMapping` — see below.

##### `from_dict(data: dict) -> BaseContainer` (classmethod)

Create container from dictionary.

**Parameters:**
- `data` (dict): Serialized data

**Returns:** New container

**Raises:** `TypeError`, `ValueError`

### ReadOnlyMapping, ReadOnlyList

What `to_dict` returns from an object built with `use_cache=True`. That mapping **is** the cache,
so writing to it would change what every later call reports; the write raises
`SerializationError` (also a `TypeError`) instead.

```python
data = box.to_dict()               # box built with use_cache=True

json.dumps(data)                   # a dict holding lists: every read works
assert data == json.loads(json.dumps(data))   # including equality with plain ones

data["name"] = "other"                      # SerializationError
data["items"]["bolt"]["tags"].append("x")    # and so is this, all the way down

editable = dict(data)              # copy it to change it
```

| | |
| --- | --- |
| Reads | Unchanged — both are real `dict` and `list` subclasses |
| Writes | `SerializationError`, naming the copy to make |
| `dict(m)`, `list(v)`, `copy`, `deepcopy`, `pickle` | Plain, writable structures |
| Without `use_cache` | An ordinary `dict`, since nothing else holds it |

## Super module

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

##### `release() -> None`

Drop the orchestrator, the method registry and the cache, breaking the cycle between an operation
and its owner. A released operation cannot serve another request; `clear_cache()` is the narrower
one that only forgets resolved handlers.

##### `clear() -> None`

Deprecated in 1.9.0, goes in 2.0 — use `release()`.

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

### Response

What every request produces — a facade, `process_request`, each entry of a batch, each step of a
pipeline. A `dict` in the shape of `ResponseData`, plus the properties that save a caller
unwrapping it:

| | |
| --- | --- |
| `ok` -> bool | Whether it succeeded |
| `value` -> Any | What it produced, unwrapped as a facade unwraps it. None for a failure |
| `error` -> Optional[str] | The message |
| `error_type` -> Optional[str] | The name of the exception class |
| `raise_if_failed()` -> Response | Raises the kind that failed, or returns this response |

`value` is not `response["result"]`: a request naming one method holds
`{"get_price": {"status": True, "result": 4.5}}` there, and the facade unwraps it. Both call the
same `unwrap`, so they cannot disagree.

### ResponseData, MethodOutcome

`TypedDict`s for the two shapes above — the protocol's own types, for annotating what crosses a
boundary and for reading a response that has been through JSON and is no longer a `Response`.

```python
class ResponseData(TypedDict):
    status: bool                    # whether the request succeeded
    object: Any                     # the name of the object it ran on
    method: NotRequired[Any]        # the handler that ran, when one was named
    result: NotRequired[Any]        # what it produced
    error: NotRequired[Any]         # present only on a failure
    error_type: NotRequired[Any]    # the name of the exception class

class MethodOutcome(TypedDict):
    status: bool
    result: Any
    error: NotRequired[str]
```

A `TypedDict` is not enforced at runtime, so a test checks the declared keys against a real
response — the declaration cannot drift from what ships.

### MethodResults

What the usual handler returns: method name mapped to a `MethodOutcome`. A `dict` subclass, so it
logs and journals like any mapping while staying recognisable — which is what lets `unwrap` reduce
a single-method result to its value.

| | |
| --- | --- |
| `values_only()` | Method name mapped to its value, dropping the per-method status. A failure maps to None |

The shape does not depend on how many methods a request named. A handler that returned only the
last result made the outcome depend on the order of the keys in the request.

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

##### `remove_all() -> None`

Remove every item from the project's container.

##### `clear() -> None`

Deprecated in 1.9.0, goes in 2.0 — use `remove_all()`.

## Mega module

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

What is registered: per operation, each handler with `requires`, `calls`, `touches`, `accepts`
and `label`. `accepts` is the attribute keys the handler reads, for a caller building a menu, a
set of flags or a request without listing them a second time.

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

##### `plan_for(operation: str, wanted: List[str]) -> List[str]`

The handlers to run so that everything `wanted` can be, each after what it needs. The join of
`requirements_of` and `order_handlers`, which every application orchestrating an operation was
writing for itself.

**Raises:** `DispatchError` for an unregistered operation

##### `find(name: str) -> Optional[Any]`

The first object called `name` in whatever this orchestrator manages, found by walking what it
holds and stopping there. A name is unique inside a container, not across a model, so two
containers may each hold a `bolt` and this answers with whichever the walk reaches first — use
`address`/`locate` where it matters. What it costs depends on where the object is: 35 µs against
465 µs for a full walk of a thousand objects.

##### `address(obj: Any) -> List[str]`

Where an object sits in the model: `["store", "right", "bolt"]`. Read from the ownership graph, so
it costs no bookkeeping and moving an object changes its address. A single name for something
nothing owns; empty for anything unnamed.

##### `locate(path: Sequence[str]) -> Optional[Any]`

The object at a path, descending from the managed object. Nothing is searched and nothing is
guessed, so unlike `find` it says which `bolt`. None if any segment is missing.

A model holds its parts in three shapes, and a path is built from *names* rather than from how
they are held, so each segment is looked for all three ways:

| Shape | Reached by |
| --- | --- |
| An item of a container | `get(name)` |
| An item of a project | `get_items()[name]`, since a `Project` calls it `get_item` |
| A container in a field of an entity | the field whose value is named `name` — `bolts: Bolts` holds one called `bolts_of_press`, and the path carries that |

The **top** of a path is optional: the managed object's own name, or the container a project
keeps its items in. That container is plumbing — nothing outside can ask for it by name — so a
path naming it starts below it.

`address` and `locate` are inverses, which is how an object is referred to across a file, a process
or a wire without being sent:

```python
path = manipulator.address(bolt)           # ["store", "right", "bolt"]
assert manipulator.locate(path) is bolt
```

##### `history(name=None, changed_only=False) -> List[Dict[str, Any]]`

What has been requested in this session, optionally about one object, optionally only the
requests that changed something. Each row is plain data — `operation`, the `object` it named, the
`path` it was at, `method`, `attributes`, `status`, `error`, `seconds` — so a session can be
written to a file. A journal records what was asked, not the request as it ran: holding the live
object and the response pins everything it audited.

**Raises:** `NotFoundError` if no journal is registered

##### `metrics() -> Optional[Dict[str, Dict[str, Any]]]`

What `RequestMetrics.snapshot()` reports, or None if none is registered.

##### `replay(journal=None, skip_failures=True, concurrent=False) -> PipelineRun`

Run a recorded session again, as a pipeline.

Each step is resolved **in the model this orchestrator manages**, by the path the entry recorded;
then, when nothing is there, by the object the journal saw if it is still alive — which is the only
address a manipulator managing nothing has; then by name, for a journal written before 1.9.0.

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

## Interceptors and protocols

### Interceptor

Anything callable as `interceptor(request, call_next)`. It sees a request before it runs and its
response after, and may read, refuse, rewrite or time either. The chain is registered on the
orchestrator; the first added is the outermost.

```python
def read_only(request, call_next):
    if request["operation"] == "configure":
        return Response({"status": False, "object": None, "error": "read-only"})
    return call_next(request)

manipulator.add_interceptor(read_only)
```

Returning without calling `call_next` refuses the request; the operation never runs. This is the
one place to hang metrics, auditing, rate limiting and authorisation — none of which the operation
layer has to know about.

### MethodProvider

What a `Super` needs from an object: `get_methods()` returning the callables it offers by name.
Duck-typed, so an object may satisfy it without importing anything.

### RequestMetrics

Counts, times and records failures per operation.

| | |
| --- | --- |
| `snapshot()` | `{operation: {"calls", "failures", "seconds", "slowest"}}`, as plain data |
| `reset()` | Forget everything counted so far |

`manipulator.metrics()` returns the same mapping from the registered instance.

### RequestJournal

Records what each request was and what it produced. Read backwards it answers what produced a
result; replayed forwards it runs the session again.

```python
RequestJournal(limit: Optional[int] = None, fingerprints: bool = False)
```

| | |
| --- | --- |
| `limit` | Keep the most recent N entries, dropping the oldest. None keeps everything |
| `fingerprints` | Hash the object either side of each request, so `changed()` can report which requests altered anything. Costs one serialization each way |

An entry is plain data, so a session can be written to a file:

| Key | |
| --- | --- |
| `operation` | What was asked |
| `object` | The `name` of the object it ran on |
| `path` | Where that object was — `["store", "right", "bolt"]` |
| `method` | The handler named, if any |
| `attributes` | The request's attributes, with model objects reduced to their names |
| `status`, `error` | Whether it worked, and why not |
| `seconds` | How long it took |
| `before`, `after` | Fingerprints, with `fingerprints=True` |

| | |
| --- | --- |
| `entries` | Every entry, in order |
| `failures()` | Only the ones that failed |
| `history(name)` | Every request that named a given object |
| `changed()` | Only the ones that left the object different. Needs `fingerprints=True` |
| `as_plan(skip_failures=True, resolve=None)` | The session as a pipeline plan |
| `clear()` | Discard every entry |

Three things worth knowing:

- **It holds no results and no objects.** An entry is data and the object is held weakly beside
  it. A journal that kept results pinned everything it had ever audited — found in an application
  whose storage design exists to keep results *out* of memory.
- **`limit` makes it a sliding window, not a session.** An overflowed journal replays a suffix.
  Leave it unlimited where replay matters.
- **Replay needs deterministic handlers.** One that reads the clock, a file or a random seed
  cannot be reconstructed from its request.

`manipulator.journal()` returns the registered instance, `manipulator.history(...)` reads it, and
`manipulator.replay(journal)` runs the session again — resolving each step by its recorded path in
the model in hand, which is what makes a session portable.

## Utils module

### Logging setup

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

### Validation helpers

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

## Response formats

One request produces a [`Response`](#response); the shape is [`ResponseData`](#responsedata-methodoutcome).

| Call | Comes back as |
| --- | --- |
| A facade, `raise_on_error=True` | The value, unwrapped. A failure raises |
| A facade, `raise_on_error=False` | The `Response` |
| `process_request` | The `Response` |
| `batch` | `{request id: Response}`, keyed as the requests were |
| `pipeline`, `replay` | A `PipelineRun`: `{step name: Response}`, plus `output`, `of`, `failed` |

## Exception hierarchy

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

## Type annotations

An attribute's annotation is its validation rule, enforced structurally and nested to any depth:
`Union`, `Optional`, `List`, `Set`, `FrozenSet`, `Tuple` (fixed and variadic), `Dict`, `Literal`,
`Type[X]`, `Callable`, and any `Serializable` subclass. Constraints go beside the type —
`price: Annotated[float, Positive()]`.

See [Type Validation](modules/base.md#type-validation-_validate_type) for what each hint accepts
and what it refuses.
