# Changelog

All notable changes to the MSB Framework are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Dates are ISO-8601.

Open findings, planned directions and what 1.0.0 should mean are in
[`docs/ROADMAP.md`](docs/ROADMAP.md).

Every release from 0.2.0 onwards carries an upgrade table: the symptom you would see, what
causes it, and what to do about it. Start there when moving between versions. An entry
records what was true at the time of that release and is not rewritten afterwards; where a
statement has since been overtaken, a note says where it was resolved.

## [0.6.0] - 2026-08-04

The data contract. An annotation now says what a value may be as well as what type it is,
serialized data survives a real JSON round trip and carries the version that wrote it, and the
two hot paths in the base layer stop repeating work.

Second stage on the road to 1.0.0. See [the roadmap](docs/ROADMAP.md).

### Added

- **Constraints on annotations.** `price: Annotated[float, Positive()]` is enforced by the
  model. Six constraints -- `Positive`, `NonNegative`, `NonZero`, `NonEmpty`, `Range`,
  `Predicate` -- wrap the helpers that had been in `utils/validation.py` all along with
  nothing connecting them to a field. A `Constraint` subclass needs only a `check` method, and
  several on one field all apply. They hold on construction, on `set`, on restoring from
  serialized data and on adding to a container, because they run inside the one check every
  path to a value goes through.
- **`SCHEMA_VERSION` and `migrate`.** Every mapping carries the version of the class that
  wrote it. Raise `SCHEMA_VERSION` when a field is renamed or given a new meaning, and
  override `migrate(data, from_version)` to bring older data forward. The default refuses,
  naming both versions, so a class that changes shape without saying how fails at the boundary
  rather than later on a missing field.
- **`DISCRIMINATORS`** for data MSB did not write: a mapping of field name to the key in the
  incoming data that names the type. Needed only where a `Union`'s members have the same shape
  and nothing else can tell them apart.

### Fixed

- **Serialization did not reach into collections.** `to_dict` descended into an entity held
  directly by a field and stopped there, so an entity inside a `List` or a `Dict` was left in
  the mapping as a live object: `json.dumps` refused such a mapping, `from_dict` could not
  restore it, and a cached mapping held references that changed under it. The README's promise
  of nesting to any depth did not hold through a collection.
- **`Set`, `FrozenSet` and `Tuple` did not round-trip.** JSON has none of the three. They are
  now written as lists and restored from the annotation, which is the only thing that can say
  which of them a list was.
- A set is serialized in a stable order, so the same object always produces the same output.
  Without it, hashing or diffing serialized data was meaningless.

### Changed

- **`to_dict` output gains a `schema_version` key.** Anything comparing whole mappings against
  a literal will see it. Data written before this carries none and is read as version 1.
- Entity construction is **17x a plain object, down from 44x**, and introspects its
  annotations **no times per instance, down from ten**: a validator is compiled once per class.
  The structural walk still decides everything parameterized, and a test compares the two paths
  so they cannot drift apart.
- Cache invalidation **stops climbing the ownership graph when nothing caches**, which is the
  default: 413 µs to 39 µs at 500 owners.

### Upgrading from 0.5.0

| Symptom | Cause | What to do |
| --- | --- | --- |
| A test comparing `to_dict()` to a literal mapping fails | The mapping now carries `schema_version`. | Compare the fields you mean, or add the key. |
| An entity that used to serialize now writes nested mappings where it wrote objects | Collections are serialized properly. This is the fix. | Nothing, unless code depended on reaching a live object through `to_dict()` output. |
| `SerializationError: cannot read data written under schema version N` | The class raised `SCHEMA_VERSION` without overriding `migrate`. | Override `migrate`, or leave `SCHEMA_VERSION` alone. |
| A value that used to be accepted is now rejected | A constraint was added to that annotation. | Intended. Remove the constraint if it was wrong. |

## [0.5.0] - 2026-08-04

Errors and measurement. The framework gains its own exceptions, a type variable resolves to
what it was actually parameterized with, and performance and documentation stop being
defended by memory: benchmarks fail a build on a regression, and every example in the
documentation runs.

First release of the road to 1.0.0, whose scope is now closed and written down in
[the roadmap](docs/ROADMAP.md).

### Added

- **`msb_arch.errors`**, with every type exported from `msb_arch` itself: `MSBError` at the
  root, `ValidationError` and `OperationError` grouping beneath it, and thirteen specific
  types under those. The 93 places that raised a built-in now raise one of them. The full
  tree, and which built-in each answers to, is in
  [the API reference](docs/api.md#exception-hierarchy).
- **A cause on `HandlerError`**: `_apply_methods(strict=True)` attaches the exception the
  handler actually raised, so a failure inside domain code keeps its traceback instead of
  being reduced to a string. A facade raising with `raise_on_error=True` cannot, because by
  then the failure has crossed into a response and only the message survives.
- `BaseContainer._item_type_hint()`, one place that answers what a container was declared to
  hold, replacing five copies of the same lookup.
- **A benchmark suite that can fail a build.** Seven benchmarks asserting ratios, call counts
  and scaling rather than wall-clock times, so a slow CI runner does not fail them and a real
  regression does. CI now also runs on pull requests; before, it ran only after a merge.
- **Documented memory behaviour of the serialization cache**: one mapping per caching object,
  duplicating the data, never evicted, bounded by the model rather than by traffic. Roughly
  275 bytes per item. Caching a container *and* its items stores the same content twice.

### Changed

- **Nothing a caller catches.** Every new type also derives from the built-in it replaces, so
  `except TypeError`, `except ValueError`, `except KeyError` and `except AttributeError` catch
  exactly what they did before. This was the constraint the design was built around rather
  than a happy accident: of 494 existing tests, none needed changing.
- Two types answer to two built-ins, because the sites they replace did not agree on one:
  `RequestError` is a `ValueError` and a `TypeError`, and so is `SerializationError`.
- **A `TypeVar` that nothing determines now resolves to `Any` instead of raising**, so a
  generic entity can be used without being parameterized. This matches what `_check_type`
  already does with any hint it cannot reduce to a class.
- The `Super` guide and the examples were rewritten where they no longer ran, and every claim
  about what an example produces is now an `assert` rather than a comment.

### Fixed

- **A type variable resolved to the wrong type.** Every variable took the *first* type
  argument regardless of its position, so the second field of a `Generic[T, U]` was validated
  against the first parameter's type and accepted wrong values. Resolution is now by
  position, and reaches arguments through an inheritance chain.
- **A constrained type variable accepted only its first constraint**, so `TypeVar('V', int,
  str)` rejected every `str`. Constraints now form a union.

- **A container declared without its type parameter** -- `class Box(BaseContainer)` rather
  than `BaseContainer[Item]` -- failed with `AttributeError: type object 'Serializable' has
  no attribute '__args__'` from inside the framework. The guard meant to catch this looked up
  `__orig_bases__` through inheritance, where it found `BaseContainer`'s own bases and so
  never fired. It now raises `ResolutionError` naming the syntax to use. A subclass of an
  already parameterized container still resolves, since that case relies on the same
  inherited lookup.
- A container whose bases put a mixin before `BaseContainer[Item]` could not resolve its item
  type, because the lookup assumed the parameterized base was first.

### Upgrading from 0.4.0

| Symptom | Cause | What to do |
| --- | --- | --- |
| Nothing. | Every exception still derives from the built-in it replaces. | Nothing. Adopt the specific types where a narrower `except` would help. |
| `ResolutionError: Cannot determine generic type` from a container that used to work | It was declared without a type parameter and failed later, obscurely, or silently resolved to the type variable. | Declare it as `BaseContainer[YourType]`. |
| A generic entity now rejects a value it used to accept | The field was typed by the *first* type argument regardless of position. It is now validated against its own parameter, which is stricter and correct. | Pass a value of the declared type. If the old behaviour was being relied on, the annotation said something other than what was meant. |
| A generic entity now accepts a value it used to reject | Either a constrained `TypeVar` was allowing only its first constraint, or an unparameterized one was raising. | Nothing. Constrain the field explicitly if the wider type is unwanted. |

## [0.4.0] - 2026-08-03

Moves the loop every handler was writing by hand into the framework, and makes the result
of an operation report every method it ran.

### Added

- **`Super._apply_methods(obj, attributes, valid_methods, extra_args, strict)`**: applies
  every method a request names and reports each outcome. It is the loop downstream handlers
  had to write themselves -- look the allowed methods up, apply each one, decide what a
  failure means -- and it reduces a typical handler to a single line. In the project this
  was measured against, 22 handlers of about 800 lines collapse to roughly 60.
- **`MethodResults`**, exported from `msb_arch`: the mapping a handler returns, from method
  name to `{"status", "result"}` with `"error"` where one failed. A plain `dict` subclass,
  so it serializes and replays like any mapping.
- **`Manipulator.batch(requests, raise_on_error=False)`**: sugar over the sequence form of
  `process_request`, which had no facade and therefore no users and no coverage. A sequence
  is numbered, a mapping keeps its identifiers, requests run in order, and the report gives
  the response of each. The requests are independent.

### Changed

- **A handler built on `_apply_methods` reports every method it ran**, not just the last.
  The previous shape made the outcome depend on the order of the keys in the request and
  discarded everything else, which is why a request history could not be reconstructed.
  Handlers that do not use the new helper are unaffected.
- The facades stay sugar and unwrap the common case: a request naming exactly one method
  yields that value rather than a mapping of one, so existing single-method call sites need
  no change. Only `MethodResults` is unwrapped, so a handler returning data of its own is
  left alone.

### Notes

Nothing here is breaking. `_apply_methods` is opt-in, and `batch` is new. The two directions
this work opens -- pipelines, where a step depends on an earlier result, and an asynchronous
Manipulator -- are recorded in [`docs/ROADMAP.md`](docs/ROADMAP.md) and deliberately not
started: there is no dependent batch anywhere yet to design against.

## [0.3.2] - 2026-08-03

Makes the state MSB shares between objects safe to use from several threads, and restores a
method the 0.3.0 split dropped by accident.

### Fixed

- **Two projects of the same item type could end up with unrelated container classes.**
  `_create_container` looked the generated class up and built one on a miss without holding
  a lock, so concurrent first use of a type produced a class per thread: sixteen threads
  yielded up to fifteen competing classes. Their containers then compared unequal, which is
  the defect 0.2.0 fixed for the sequential case and this reopened for the concurrent one.
- **The handler cache could lose entries or outgrow its limit.** A lookup that interleaved
  with an eviction could miss a live entry, and two threads passing the size check together
  could both skip an eviction. Reads are a single lookup now and no longer reorder entries,
  and eviction is guarded.
- **`has_attribute` is back on containers.** Splitting the hierarchy in 0.3.0 left it on
  `BaseEntity`, so containers lost a method they had inherited since 0.1.0. It asks about
  annotated attributes, which a container has as much as an entity, so it now sits on
  `Serializable`; its counterpart for items is `has_item`.

### Added

- `tests/test_concurrency.py`, which shortens the interpreter's thread switch interval and
  hammers each shared structure from sixteen threads. The two defects above fail it on every
  run against the unguarded code.
- A thread-safety section in the `Serializable` docstring and the base module guide, stating
  what is guarded and what is not: shared structures are, a single object is not, exactly as
  for any plain Python object.

## [0.3.1] - 2026-08-03

Fixes a break that 0.2.0 introduced and 0.3.0 carried: a subclass overriding `to_dict`
could no longer be serialized.

### Fixed

- **`to_dict()` takes no arguments again.** Cycle detection, added in 0.2.0, threaded the
  set of already-serialized identities through a `_seen` parameter. Containers and nested
  entities therefore called `item.to_dict(_seen=...)`, and every subclass override written
  as `def to_dict(self)` -- which is how the documentation says to write one -- failed with
  `TypeError: to_dict() got an unexpected keyword argument '_seen'`. The traversal state
  moved into a context variable, so the signature is the one it was in 0.1.3 and overrides
  work again. Being contextual it is also per thread and per task, so concurrent
  serializations no longer share marks.
- **`BaseContainer.to_dict(handle_cyclic_refs)` is positional again.** It was made
  keyword-only in 0.3.0 only to avoid colliding with `_seen`, which no longer exists.
- Removed an orphaned duplicate docstring left inside `Serializable` by the 0.3.0 split.

### Added

- Tests covering a subclass that overrides `to_dict`, both as a container item and as a
  nested attribute. The suite missed the break because its containers were never populated,
  so no item was ever serialized through one; that gap is closed, and the same gap in the
  downstream smoke check is fixed too.

## [0.3.0] - 2026-08-03

Separates the base hierarchy, closes two regressions the 0.2.0 fixes introduced, and writes
down the contract `Super` subclasses were already relying on.

### Breaking

- **`BaseContainer` no longer derives from `BaseEntity`.** Both now derive from a new
  `Serializable`, which holds the annotated fields and their validation, the `name` and
  `isactive` state, serialization, the cache and the ownership graph it is invalidated
  through. The container inherited fourteen members it gave a different meaning, seven with
  incompatible signatures: `get` addressed attributes on one and items on the other, `clear`
  wiped attributes or removed items, and the item operators disagreed the same way. An
  `isinstance` check that should accept either must now name `Serializable`; naming
  `BaseEntity` no longer matches a container. There were seven such checks inside the
  framework and none in pAstroCORE.
- **`BaseContainer.to_dict` takes `handle_cyclic_refs` keyword-only**, because
  `Serializable` declares `to_dict(_seen)` and a positional first argument would mean two
  different things depending on the class.
- **`Super._default_result` and `Super._default_nested_result` are gone.** Neither had a
  caller in the framework or downstream.

### Fixed

- The class registry added in 0.2.0 held strong references, so every class ever declared
  stayed alive for the lifetime of the process; five hundred dynamically built classes
  survived a full collection. Entries are weak now, and `EntityMeta.registered_classes()`
  returns the live ones in a deterministic order.
- Upward cache invalidation recorded a single owner, which was enough only while `add` deep
  copied. With `copy_items=False` -- the documented way to avoid that copy -- one item lands
  in two containers, and only the one that adopted last was invalidated; the other served a
  stale mapping indefinitely. Every owner is tracked and invalidated. They are keyed by
  identity rather than held in a set, because a set hashes and compares its members and
  comparing entities walks their fields, which never returns on a cyclic structure.
- Attribute assignment is faster than before either change, 0.068 s per 20000 sets against
  0.076 s in 0.1.3, because invalidation now skips the graph walk entirely when nothing owns
  the entity.

### Added

- `Serializable`, exported from `msb_arch`, for `isinstance` checks and for annotations that
  accept an entity or a container.
- A "Writing your own Super" section in the module guide. `_get_methods`,
  `_validate_and_apply_method` and `_do_nested` are called 22, 33 and 9 times by pAstroCORE
  and never by the framework: they are the integration surface, the single underscore means
  protected rather than private, and nothing said so. The class docstring lists them as
  extension points.
- Test suite grown from 411 to 426 cases, covering the split hierarchy, registry lifetime,
  multiple owners and the `Super` extension points.

### Upgrade notes: 0.2.0 to 0.3.0

| Symptom after upgrading | Cause | What to do |
| --- | --- | --- |
| `isinstance(x, BaseEntity)` is False for a container | The two classes are siblings now | Use `Serializable` where either is acceptable |
| `TypeError` from `container.to_dict("ignore")` | Was keyword-only in 0.3.0 only | Fixed in 0.3.1; positional again |
| `AttributeError` on `_default_result` | Removed, it had no callers | Call `_build_response(obj, False, ...)` |

## [0.2.0] - 2026-08-03

This release closes a full review of the 0.1.3 MVP: twenty-three findings across three
waves of fixes, plus packaging and test-harness work. The validation contract changes, so
it is a minor version bump rather than a patch. Read
[Upgrade notes](#upgrade-notes-013-to-020) before upgrading a project that depends on MSB.

### Breaking

- **Parameterized type hints are now enforced.** `_validate_type` compared `get_origin()`
  against `typing.List`, which never matches because `get_origin` returns the bare `list`.
  The branch was unreachable, so element types inside `List[T]` were never checked and an
  attribute annotated `List[int]` silently accepted `["a", 3.5, {"x": 1}]`. Values that
  were previously stored unchecked now raise `TypeError`.
- **Attributes named `value` accept `None`.** The name was hardcoded alongside `name` as
  non-nullable, so an entity with such a field could not be constructed without passing it,
  and `clear()` produced objects that `from_dict(to_dict())` and `clone()` could no longer
  restore. Only `name` remains mandatory, because containers index their items by it.
- **`__del__` removed from `BaseEntity`, `BaseContainer`, `Super`, `Project` and
  `Manipulator`.** Code that relied on state being released when an object went out of
  scope must call `clear()` explicitly.
- **`BaseContainer.__init__` copies the mapping it is given.** The container previously
  stored the caller's dict by reference; later changes to that dict are no longer visible
  inside the container.
- **`repr()` of an entity lists only public attributes.** Underscore-prefixed fields such
  as `_type_cache` are no longer printed.
- **`Manipulator.clear_cache()` empties the instance registry** instead of clearing a
  class-wide cache shared by every `Manipulator`.
- **`Super._make_hashable` and `Super._update_cache` removed.** Both were unreachable from
  `execute`; subclasses that called them directly need to supply their own.
- **A cached `to_dict` result is the live mapping and must be treated as read only.**
  Validating the cache used to re-serialize every nested entity, which is the work the
  cache exists to avoid; that walk is gone, so mutating the returned mapping now corrupts
  the cache. Copy it before changing it.
- **`BaseContainer._resolve_type` removed.** The base implementation gained the
  `field_path` argument that was the only difference between the two.
- **The package no longer configures logging.** Importing `msb_arch` used to attach a file
  and a stream handler to the **root** logger and create `output.log` in the working
  directory. Messages now go to a `msb_arch` logger carrying only a `NullHandler`, so an
  application that wants output either configures logging itself or calls `setup_logging()`.
  The helper keeps its signature and configures that logger rather than root.
- **A request can only reach handlers of its own operation.** `Super.execute` resolved
  `getattr(self, method)` from a name supplied in the request with no restriction, so
  `method="clear"` wiped the manipulator and the method registry and `method="execute"`
  recursed. Only `_<operation>` and `_<operation>_*` are reachable now; any other name falls
  through the usual cascade to a general handler instead of being called.
- **An operation may not be named after a `Manipulator` attribute.** Names are installed on
  the instance as facade methods, so registering `process_request` replaced the method and
  every call recursed. Registration now rejects a name that is not an identifier or that
  would shadow an existing attribute.
- **`BaseContainer.remove` raises `KeyError` naming the container.** It previously logged a
  warning and then failed with a bare `KeyError` anyway, so the exception type is unchanged
  and only the message and the stray warning differ.

### Fixed

- Nested generics no longer raise on valid data. `Dict[str, List[int]]` rejected the
  perfectly valid `{"a": [1, 2]}` with *"Subscripted generics cannot be used with class and
  instance checks"*, because the inner branch had the same unreachable comparison.
- `Manipulator` instances are garbage collected again. `_get_method_registry` was decorated
  with `@lru_cache` while being an instance method, so `self` became part of the cache key
  and every instance was retained for the lifetime of the process. The cache also lived on
  the class, which made the registry shared between instances and made `clear_cache()` wipe
  it for all of them.
- Populating a container is no longer quadratic. `_invalidate_cache` walked every stored
  item on each call, and `add` calls it, so 2000 inserts issued two million `hasattr` calls
  and the cost per insert grew with the container. The walk also ran with caching disabled,
  and it invalidated the wrong direction: an item is not stale because its container
  changed.
- A container no longer destroys data its owner still holds. `__del__` called `clear()`,
  which emptied the caller's dict.
- Internal fields no longer leak into the public surface. `EntityMeta` collects every
  annotation into `_fields`, including `_type_cache`, `_cached_to_dict` and `_use_cache`.
  `to_dict` filtered them out but `clear()`, `__eq__` and `__repr__` did not, so `clear()`
  shadowed the shared class-level type cache with `None` on the instance, and two entities
  holding identical data compared unequal.
- `Project._create_container` executed a class statement on every call, so each project got
  a container of its own freshly built class. Two projects of the same type held containers
  that were not instances of each other's class, `__eq__` returned `False` for identical
  contents, and every project leaked one class.
- Attribute reads on a container are roughly four times faster after removing an
  identity-only `__getattribute__` override.
- Two modules each declaring a class of the same name no longer collide. `_type_cache` was
  declared on `BaseEntity` and `BaseContainer` and mutated through item assignment, so every
  subclass shared one dict keyed, for forward references, by a bare class name. Whichever
  module resolved first won, and the other module's entity was rejected against a foreign
  class of the same name. Each class now owns its cache, and a name is resolved against the
  module that declares the class before the framework module is consulted.
- Cyclic references terminate instead of exhausting the stack. `to_dict` built a fresh
  `seen` set per call, so only a reference repeated at one level was recognised; A holding
  B holding A recursed until the stack ran out. The set is threaded through the recursion,
  and `handle_cyclic_refs` now also covers a container reached through its own items.
- A self-referential entity such as `peer: 'Node'` inside `class Node` resolves even where
  the class is not reachable through its module, for instance when declared inside a
  function.
- Polymorphic deserialization works. `from_dict` resolved a nested entity's `type` through
  the framework module's globals, where no user class can appear, so a subclass stored under
  a base-typed attribute came back as the base and a user type was never found at all.
  Containers restore subclasses of their declared item type the same way.
- A cached container no longer serves a stale `to_dict` after one of its items is mutated.
  Invalidation travels up an ownership chain of weak references, rebuilt across a subtree
  whenever it is stored somewhere new, because `deepcopy` treats a weak reference as atomic
  and the copies made by `add` would otherwise still point at the originals.
- A `Super` that was never registered with a `Manipulator` works. `_operation` was only ever
  assigned by `register_operation` and `execute` reads it in its first statement, outside the
  `try` block, so such an instance raised `AttributeError` instead of returning a response.
  It now starts from the class-level `OPERATION`, and a still-missing operation name is
  reported as an ordinary failed response.
- `Project.from_dict` was abstract while carrying a full implementation, forcing every
  subclass to write a stub it could not fill; the one in the README had a broken signature
  and raised when called. It is concrete now, and `create_item` stays abstract because it
  genuinely has nothing to inherit.

### Added

- Structural validation for `Set[T]`, `FrozenSet[T]`, fixed-length `Tuple[X, Y]` including
  arity, variadic `Tuple[X, ...]`, `Literal[...]`, `Callable[...]`, `Type[X]`, PEP 604
  unions (`X | Y`) and `Annotated[X, ...]`, nested to any depth. Abstract collections such
  as `Sequence[int]` are checked against their origin only, so validation never consumes an
  arbitrary iterable, and an unresolvable hint is accepted rather than blocking a valid
  assignment. The full table is in [`docs/modules/base.md`](docs/modules/base.md).
- Error messages that point at the offending element rather than the attribute:
  `Item in list 'tags' must be of type <class 'int'>, got <class 'str'>`.
- `py.typed` marker, so the package finally ships its annotations to consumers.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) with the 26 findings from the review, ordered by
  criticality and grouped into working waves.
- `__hash__` on `BaseEntity` and `BaseContainer`, derived from the concrete class and the
  name. Defining `__eq__` without it made every entity unhashable, so none could go into a
  set or serve as a dictionary key. Equal entities always hash equal; two entities sharing a
  name collide and are separated by `__eq__`. Changing `name` while the entity sits in a set
  makes it unreachable, as for any mutable key.
- The method cache in `Super` does something again: it remembers which handler a requested
  name and object type resolve to, which makes repeated dispatch about 2.5 times faster.
  Only the lookup is cached, never the outcome of an operation, since operations have side
  effects. `cache_size` and `clear_cache()` therefore have meaning once more, and
  `register_method` still drops the cache.
- Test suite grown from 286 to 411 cases, covering every supported type hint, round-trip
  closure after `clear()`, container mapping ownership, object collection, registry
  isolation between `Manipulator` instances, cycle handling, cache invalidation across an
  ownership chain, handler dispatch restrictions and library logging hygiene.
- The tests exercise the **installed** package. They previously imported from `src/`, which
  works only because `tests/` is a package and pytest prepends the repository root, so the
  built distribution was never covered and a packaging mistake could not fail the suite. CI
  now builds the wheel, installs it, checks that `msb_arch` resolves inside `site-packages`,
  and runs the suite against it. Local development needs `pip install -e .` first.

### Removed

- The five `__del__` finalizers described above.
- `Super._make_hashable`, `Super._update_cache` and `BaseContainer.__getattribute__`.
- `ScheduleManipulator` and `ScheduleProject` log strings copy-pasted from pAstroCORE,
  which existed only inside the removed finalizers.

### Changed

- The two caching performance tests asserted `time_with_cache < time_no_cache`. For an
  entity holding a nested entity the cached path re-serializes that entity to check the
  cache is still valid, so both paths cost about the same and the assertion failed roughly
  one run in five. They now assert that the cached call returns the cached mapping itself,
  with a generous timing margin on top.
- `MANIFEST.in` referenced a top-level `msb` directory that has not existed since the
  package was renamed to `msb_arch` under `src/`, so its `recursive-include` matched
  nothing.
- The README version badge advertised 0.1.0 while `pyproject.toml` and `__init__` were on
  0.1.3.

### Known issues

The following were found during the review and were **not** fixed in this release. All three
have been resolved since; the entry is kept as it stood.

- `BaseContainer` inherits from `BaseEntity` while giving `get`, `clear` and `set`
  incompatible meanings, which is an LSP violation and the root cause behind several of the
  fixes above (R13). Reworking it reshapes the base hierarchy, so it is deliberately left
  for a later release. — *resolved in 0.3.0.*
- Nothing is thread safe, and some state is held at class level (R19). — *resolved in 0.3.2.*
- The test suite imports from `src/` and CI never installs the package, so the built
  distribution is never exercised (R23). — *resolved in this release; the CI change landed
  alongside it.*

### Upgrade notes: 0.1.3 to 0.2.0

Run your test suite first. The validation fix surfaces data that was already wrong but had
been accepted silently, so failures point at real defects rather than at the framework.

| Symptom after upgrading | Cause | What to do |
| --- | --- | --- |
| `TypeError: Item in list '<attr>' must be of type ...` | A collection attribute holds elements of the wrong type | Fix the data, or widen the annotation to `List[Union[...]]` or `List[Any]` |
| `TypeError: Attribute '<attr>' must have N items` | A `Tuple[X, Y]` attribute holds a different number of elements | Use `Tuple[X, ...]` if the length is meant to vary |
| An attribute named `value` now accepts `None` | The hardcoded guard is gone | Enforce the requirement in the subclass if it was intentional |
| State is not released when an object goes out of scope | The `__del__` finalizers are gone | Call `clear()` explicitly |
| Changes to a dict passed as `items=` no longer reach the container | The container copies the mapping it is given | Use `add`, `set_item` or `set_items` |
| `TypeError: Ambiguous type '<name>' ...` | Two modules declare an entity class with the same name and the payload does not say which | Rename one of them, or annotate the attribute with the exact class |
| A mapping returned by `to_dict()` changed under you | With caching enabled the same mapping is returned every time | Copy it before mutating |
| No log output at all, and no `output.log` | The package no longer configures logging on import | Configure `logging` in the application, or call `setup_logging()` once at start-up |
| Log records arrive under a different logger | Messages come from `msb_arch` instead of the root logger | Target `logging.getLogger("msb_arch")` when filtering or attaching handlers |
| A request with `method=...` reaches a different handler than before | Only `_<operation>` and `_<operation>_*` can be named | Rename the handler to the `_<operation>_<suffix>` form |
| `ValueError: Operation '<name>' would shadow ...` | The operation name collides with a `Manipulator` attribute | Rename the operation |

## [0.1.3] - 2026-04-22

### Fixed

- `BaseContainer.__init__` raised an unhelpful error when a subclass was declared without
  the `BaseContainer[YourType]` syntax. The generic argument is now resolved once, before
  `super().__init__`, and a missing `__orig_bases__` produces an explicit message naming
  the required syntax.
- `BaseEntity.__init__` validated `isactive` while reporting it as `use_cache`, so an
  invalid `use_cache` argument passed unchecked.

### Added

- A bumpversion setup for keeping `pyproject.toml`, `__init__` and the documentation in
  step.

### Changed

- Documentation examples corrected and unused files removed from the tree.

## [0.1.2] - 2026-04-16

### Changed

- Version synchronised across `pyproject.toml`, `src/msb_arch/__init__.py`, `README.md` and
  `docs/README.md`.

## [0.1.1] - 2026-04-16

### Changed

- Packaging metadata corrections.

## [0.1.0] - 2025-12-19

Initial public release.

### Added

- **Base** layer: `BaseEntity` with annotation-driven attribute validation, activation
  state and serialization, and the generic `BaseContainer[T]` for collections of entities
  with querying and bulk operations.
- **Super** layer: `Super` operation handlers with method resolution, and `Project` for
  organizing entities within a project context.
- **Mega** layer: `Manipulator` for registering operations, generating facade methods and
  processing single or batched requests.
- **Utils** layer: configurable logging setup and standalone validation helpers.
- Full documentation set under `docs/`, including API reference, architecture notes,
  diagrams and per-module guides.
- Unit, integration and performance test suites, and a GitHub Actions workflow running all
  three.
- Packaging under the `src/` layout with hatchling, with no external dependencies beyond
  the standard library.
