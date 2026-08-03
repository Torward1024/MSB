# Changelog

All notable changes to the MSB Framework are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Dates are ISO-8601.

Open findings that have not been addressed yet are tracked in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## [Unreleased] - targeting 0.2.0

This release closes the first wave of fixes from a full review of the 0.1.3 MVP. The
validation contract changes, so it is a minor version bump rather than a patch. Read
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

The following were found during the review and are **not** fixed in this release. See
[`docs/ROADMAP.md`](docs/ROADMAP.md) for the full list and the planned order.

- `BaseContainer` inherits from `BaseEntity` while giving `get`, `clear` and `set`
  incompatible meanings, which is an LSP violation and the root cause behind several of the
  fixes above (R13). Reworking it reshapes the base hierarchy, so it is deliberately left
  for a later release.
- Nothing is thread safe, and some state is held at class level (R19).
- The test suite imports from `src/` and CI never installs the package, so the built
  distribution is never exercised (R23).

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
