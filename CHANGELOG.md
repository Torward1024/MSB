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

## [1.8.0] - 2026-08-13

### Added

- **`Response`: one type for what a request produced.** Reported from downstream, where a facade
  answering with a value under `raise_on_error=True` and with the whole response under
  `raise_on_error=False` had grown this line at every call site that wanted the second:

  ```python
  result = response["result"] if isinstance(response, dict) and "status" in response else response
  ```

  That line is also wrong for the common case. A request naming one method holds
  `{"get_price": {"status": True, "result": 4.5}}` under `result`, and the facade unwraps it; the
  hand-written version does not, so the two answers differ exactly where it matters.

  Every response is now a `Response` -- still a `dict`, still logged and journalled and sent over
  a wire as one -- with four properties:

  | | |
  | --- | --- |
  | `ok` | Whether it succeeded |
  | `value` | What it produced, unwrapped exactly as a facade unwraps it. None for a failure |
  | `error`, `error_type` | The message and the name of the exception class |
  | `raise_if_failed()` | Raise the kind that failed, or return the response for chaining |

  The unwrapping rule lives in one function that both the facade and `value` call, so they cannot
  answer differently.

- Responses from `process_request`, from every entry of a `batch`, and from every step of a
  pipeline -- **including a step skipped because the one it waited for failed**, which was the one
  place still handing back a bare dictionary.

### Changed

- Nothing. `raise_on_error=True` returns the value it always did, `raise_on_error=False` returns
  something that compares equal to the dictionary it always did, and code reading `response["..."]`
  is untouched.

### Upgrading from 1.7.0

Nothing to do. Where an application unwraps a response by hand, `response.value` replaces it and
is right about the one-method case.

## [1.7.0] - 2026-08-13

### Added

- **`Manipulator.plan_for(operation, wanted)`** -- the handlers to run so that everything
  `wanted` can be, each after what it needs.

  ```python
  manipulator.plan_for("calculate", ["uv_coverage"])
  # ['time_arrays', 'telescope_positions', 'source_visibility', 'uv_coverage']
  ```

  The parts were both here already -- `requirements_of` and `order_handlers` -- and joining
  them was left to whoever needed it, which meant the same six lines in every application that
  orchestrates an operation.

  It deliberately stops there. What a step is *called*, what it is passed, and whether a result
  already exists are an application's decisions, and a plan of names is what a framework can
  know without borrowing an application's vocabulary.

### Upgrading from 1.6.0

Nothing to do. `plan_for` is new.

## [1.6.0] - 2026-08-13

### Changed

- **A journal is a record, not a retainer.** An entry used to hold the request as it ran --
  including the live object it named -- and the response it produced. So a bounded journal of
  500 entries pinned up to 500 objects *and* whatever each request computed.

  Found downstream in an application whose entire storage design exists to keep results out of
  memory (407 MB to 71 MB across sixty observations): its journal held a reference to every
  result frame it had recorded, so evicting one freed nothing. Measured there: eight entries
  from one run, seven pinning a live model object and seven pinning a result.

  An entry is now plain data and nothing else:

  ```python
  {"operation": "calculate", "object": "obs_5fb2", "method": "uv_coverage",
   "attributes": {"time_step": 600.0}, "status": True, "error": None, "seconds": 0.31}
  ```

  Objects inside the attributes are named too -- a batch carries requests, and each of those
  names an object, which is the same leak one level down. Anything neither plain nor named, a
  callable passed in to report progress say, is recorded as what it was rather than kept.

- **Which is what makes a session portable.** `json.dumps(journal.entries)` works, so a session
  can be written to a file, and it replays against whatever model it is replayed on rather than
  only against the objects it recorded.

### Added

- **`Manipulator.find(name)`** -- the object called `name` in whatever the orchestrator manages,
  found by walking what it holds. This is what `replay` resolves a recorded step with.

- **Replay resolves names.** A step names its object; `replay` looks it up in the model in hand.
  Where the object is still alive in the process that recorded it, replay reaches it directly:
  the journal keeps a **weak** reference beside each entry, so an orchestrator that manages
  nothing -- a request made straight on an object -- replays exactly as before while the
  journal still pins nothing.

### Upgrading from 1.5.0

| Symptom | Why | What to do |
| --- | --- | --- |
| `entry["request"]` or `entry["response"]` raises `KeyError` | Neither is retained | Read `operation`, `object`, `method`, `attributes`, `status`, `error`, `seconds`. Neither key was documented |
| A replayed step fails with no object | Its name is not in the model being replayed against | `Manipulator.find(name)` says whether it is there. A session records the names it ran on |
| `changed()` returns nothing | Unchanged: it still needs `fingerprints=True` | -- |

## [1.5.0] - 2026-08-13

### Added

- **`accepts`: the attribute keys a handler reads, derived rather than declared.** The catalogue
  already saves an application from writing down what operations exist and which handler needs
  which. The third copy is the parameters: a dialog builds a control per filter, a command line
  builds a flag, a caller with values in hand decides which to pass — each from its own list of
  what a handler takes.

  ```python
  described = manipulator.describe_operations("visualize")
  accepted = described["visualize"]["uv_coverage"]["accepts"]
  # ['baselines', 'frequencies', 'scans', 'source_name', 'store_key', 'units']
  ```

  It appears on every entry `describe_operations()` and the built-in `catalogue` operation
  return, beside `requires`, `calls`, `touches` and `label`.

  Measured on a fourteen-handler application: it reproduced by derivation five hand-written lists
  that decided which arguments each plot was given, and found one plot that had been left out of
  two of them.

### Notes

- Unlike `calls`, `accepts` is **not** an upper bound. A helper contributes only what it reads
  from the mapping it was actually handed, at the parameter it landed on — positionally or by
  keyword — and a closure that renames the mapping is followed through its annotation. A handler
  that hands its attributes to nothing reports exactly what its own body reads.
- It is a lower bound in one shape: a key read under a name computed at run time is invisible.
  So it says what a caller may offer, not what a caller may refuse. Asserted in the suite, so
  the limit is known rather than discovered.
- The derivation is cached with the rest of the handler table, per class and operation, so this
  costs nothing on the path that already asked.

### Upgrading from 1.4.0

Nothing to do. `accepts` is a new key on a returned dictionary; code reading the others is
unaffected. A caller that compares a whole entry against a literal dictionary would see the new
key — the entries are described by their keys, and were never promised to have only those.

## [1.4.0] - 2026-08-12

### Added

- **An operation whose `Super` is built the first time it is needed.**

  ```python
  manipulator.register_deferred("plot", lambda: Plotting(manipulator))
  ```

  Registering an operation costs whatever its module costs to import. For one reached from a menu
  -- a plot, a report -- that is paid on every start whether or not anyone opens the menu.
  Measured downstream: two such operations pulled in matplotlib, astropy.coordinates and scipy,
  which was 2.3 s of a 4.0 s start.

  The operation counts as registered from the moment it is declared: it appears in
  `get_supported_operations()`, it has a facade, and a pipeline step may name it. The factory is
  called once, under a lock, by whatever needs it first -- a request, a plan, or a question about
  what the operation offers, since `describe_operations` reads its handlers and a dialog building
  a menu from the catalogue must not be told an operation has none.

- **`Manipulator.warm(operations=None)`**, which builds everything deferred. For an application
  that would rather pay the cost in the background than at the first click: start a thread, call
  it, and anything asking meanwhile waits on the same lock rather than building a second
  instance.

### Notes

- Registering an instance under a name already declared deferred replaces the declaration, since
  an application changing its mind is not colliding with itself. Two deferrals of one name still
  raise, as two registrations always have.
- Declaring a name a built-in holds displaces the built-in immediately, or dispatch would keep
  finding it and the factory would never run.

### Upgrading from 1.3.0

Nothing to do. `register_deferred` is new; everything else behaves as it did.

## [1.3.0] - 2026-08-12

The release that finishes the 1.0 roadmap: pipelines, a derived model graph, built-in `save` and
`load`, scaffolding, and the first step of lineage. Plus six bugs, a sweep of every hot path, and
the documentation rewritten.

Nothing on the public surface changed meaning. One name is deprecated.

### Added

- **Pipelines.** Several requests that feed each other, in one call, taking data — the same
  convention as `process_request` and `batch`:

  ```python
  manipulator.pipeline({
      "loaded":  {"operation": "load",    "obj": thing,     "path": "in.json"},
      "checked": {"operation": "inspect", "obj": "@loaded", "get": "value"},
      "written": {"operation": "save",    "obj": "@loaded", "path": "out.json"},
  })
  ```

  A step is a request with three additions: `"@name"` anywhere means what that step produced,
  `after` waits for a step without using its value, and any key that is not `operation`, `obj`,
  `method` or `after` is an attribute.

  Over a batch it adds exactly three things: the order the edges imply, substitution of what a
  step produced, and skipping the branch below a failure. Every step is one `process_request`, so
  it meets the interceptors, the journal and the metrics like any other.

  Steps that wait for nothing run together with `concurrent=True`, or `await apipeline(plan)`
  from inside an event loop: two independent 0.3 s steps take 0.31 s against 0.61 s in sequence.

  `manipulator.pipeline()` with no plan returns a draft that writes one by calling the
  operations. It produces a plan and hands it back to `pipeline`; there is one execution path and
  the draft is not it.

- **`save` and `load` as built-in operations.** JSON over `to_dict`, written atomically —
  a temporary file beside the target, then a rename — so an interrupted write leaves the previous
  file rather than a truncated one. The format is a default: register your own `save` and it
  takes over. `load` accepts `kind` as a class or as a name, which is how a type arrives in a
  plan or over a wire.

- **A derived model graph.** `manipulator.describe_model()` reports which type holds which, and
  the reverse — `held_by`, the direction nothing in the code answers and every caller asks in.
  `dependents_of(name)` walks it transitively. Read from the annotations, so a field added to a
  class changes the answer. Reachable as a request: `catalogue(method="model")`.

- **Scaffolding.** `manipulator.scaffold("measure")` returns the source of a `Super` with one
  handler per type in the model: containers get a working walk over their items, entities get a
  stub that raises. The names are the ones dispatch looks for, which is the part worth
  generating.

- **`revision` and `fingerprint()`.** Two answers to "did this change", with different costs.
  `revision` counts writes to one object and costs an increment on the path that already
  invalidates the cache. `fingerprint()` hashes the whole subtree, costs one serialisation, and
  holds across processes.

- **The session, through the orchestrator.** `manipulator.journal()`, `history(name,
  changed_only)`, `metrics()` and `replay(journal)`. A journal is an interceptor the orchestrator
  already holds, so a caller need not keep its own reference. `RequestJournal(fingerprints=True)`
  records a hash either side of each request, so the journal can say which requests actually
  changed something.

- **`error_type` in a failed response.** The name of the exception class — a name, not an
  exception, so a response stays data. A facade re-raises the kind of failure that happened, so a
  caller can tell a missing file from a corrupt one without reading the message.

- **`apipeline`**, the `a`-prefixed twin `pipeline` was missing.

### Changed

- **`load` answers with the object** rather than `{"object": ...}`, so a pipeline step reading a
  file hands the object straight to the next step. It never shipped in another shape.
- **Routine work says nothing at INFO.** Six messages moved to DEBUG: initialising a project,
  reading its configuration, a nested operation, registering a method, setting the managing
  object, updating the registry. A check counts what the library says while building, serialising
  and reading a container of a thousand items, and expects nothing.
- **Every numeric check refuses NaN**, and a `bool` stops being a number to them.

### Deprecated

- **`RequestJournal.replay(manipulator)`** — use `manipulator.replay(journal)`. The orchestrator
  is what runs requests, and replaying a session is running a plan. The old name warns, works
  unchanged, and goes in 2.0.

### Fixed

- **A cached container did not see a change to an item it was built with.** Items handed to the
  constructor were never adopted, so writing to one did not invalidate the container's cached
  mapping and `to_dict` went on reporting the value the item used to hold. Silent, and only with
  `use_cache=True`. Items added later were adopted and worked, which is why nothing caught it.
- **NaN passed or failed depending on how a rule was spelled.** `value <= 0` is false for NaN, so
  `Positive()` accepted it; `not 0 <= value <= 1` is true, so `Range()` refused it.
- **`load(kind="Item")` failed** on `'str' object has no attribute '__name__'`. A name is now
  looked up among the model's own types, and refused when two of them answer to it.
- **`"after": "written"`** iterated the string and waited for steps called `w`, `r`, `i`.
- **A step named with a dot** could not be referred to, because the dot was split before the name
  was looked for.
- **`pipeline(concurrent=True)` inside a running event loop** raised asyncio's own error about
  asyncio. It now says to await `apipeline`, which is the fix.
- **Saving to a directory** surfaced whatever the operating system said about a failed rename, in
  whatever language it was configured for.

### Performance

Everything that recomputed per object what is decided per class. Medians of paired samples, taken
in one pass against the tree before this work:

| | Before | After |
| --- | --- | --- |
| `describe_operations` | 112 ms | 12.8 µs |
| `order_handlers` | 16.1 ms | 4.6 µs |
| `describe_model` | 150 µs | 1.0 µs |
| `scaffold` | 111 µs | 19.5 µs |
| Build an entity | 22.0 µs | 8.4 µs |
| `from_dict`, container of 200 | 9216 µs | 4249 µs |
| `to_dict`, container of 200 | 1919 µs | 711 µs |
| `clone` | 81.9 µs | 46.5 µs |
| `add` | 78.7 µs | 43.1 µs |
| Equality | 9.7 µs | 3.4 µs |
| `inspect` | 25.0 µs | 7.1 µs |
| `configure` | 30.3 µs | 16.0 µs |
| Pipeline of 5, chained | 103 µs | 70.8 µs |
| `_check_type` on a generic | 10.8 µs | 4.1 µs |

What changed: the catalogue parsed the source of every registered class on every call; signatures
were read per call; annotations were resolved per object; the validator for a field was looked up
per value; `to_dict` asked of every value whether it was one of four container types before
noticing it was a number; adoption did the same. The four shapes most models are made of —
`Optional[T]`, `List[T]`, `Set[T]`, `Dict[K, V]` — now compile into one predicate, as a fast path
only: a refusal still goes through the structural walk so the message names the element that
failed, and a test holds the two to each other over 24 hints and 30 values.

Two more found on a second pass: serialising asked `hasattr` and then `getattr` of every field of
every object, and called a function to be told that a number is already data. A value whose exact
type is `str`, `int`, `float`, `bool` or `None` now short-circuits both ways, which cuts the
calls into `_serialize_value` by 63%.

### Documentation

Every page rewritten: what a thing does, how, why where the why is not obvious, and an example
where one helps. The examples use parts, widgets and a workshop, so nothing turns on knowing the
domain MSB was first written for. `README.md` names the one project using MSB, and that is the
only mention of it.

### Upgrading from 1.2.0

| Symptom | Cause | What to do |
| --- | --- | --- |
| `DeprecationWarning: RequestJournal.replay is deprecated` | Replaying moved to the orchestrator | Call `manipulator.replay(journal)`. The old name works until 2.0 |
| A `load` result no longer has `["object"]` | `load` answers with the object itself | Drop the subscript |
| A `Positive()` field that accepted NaN now raises | NaN is refused by every numeric check | Was almost certainly a bug in the caller; if NaN is meant, use `Predicate` |
| A cached container now reports a changed item | Items given to the constructor are adopted | Nothing. The old answer was stale |
| A response has an extra `error_type` key | Facades re-raise the kind of failure | Nothing unless you compare whole responses |

## [1.2.0] - 2026-08-11

### Added

- **A manipulator can be asked what it offers.** An application built on MSB knows what it can
  do twice: once in the handlers that do the work, and again in whatever menu or table offers
  them. The second copy is hand-written and drifts.

  `Manipulator.describe_operations()` reads the first copy back -- every operation registered,
  its handlers, the handlers each one calls, and a label for each. `order_handlers()` sorts
  them so each comes after what it needs. The built-in **`Catalogue`** operation makes both
  reachable as requests: `manipulator.catalogue()` and
  `manipulator.catalogue(method="order", ...)`.

  The split is deliberate. The registry is the manipulator's own state, so it assembles the
  answer; the built-in only exposes it, exactly as `Inspector` exposes an object's own
  attributes. Nothing reaches into `_operations` from outside.

  Nothing is written down: handlers name themselves against the operation they serve and call
  each other by name, so registering a `Super` is all it takes for the answer to include it.

### Notes on what it can and cannot tell you

- **Edges between handlers are exact.** A call is a call. Measured on a 2 700-line calculator
  downstream: all fourteen handler-to-handler edges recovered with nothing declared.
- **What a handler touches beyond the operation is an upper bound.** A helper shared between
  handlers is followed for each of them, so six of the fourteen came out wider than the truth.
  Use it to *check* a declaration, never as one -- the wide answer taken as truth restores the
  coarseness that declaring a dependency exists to remove.
- **Nothing here knows what an application is about.** Calls are reported as the names in the
  code; `interpret` is where a caller says what a name means to it.
- **Edges are stored direct and the full set is walked on demand.** Direct is the more
  informative of the two: the closure follows from the edges that were written, and
  recovering which were written from a closure does not. `requirements_of()` -- on the
  module and on the manipulator -- is that walk, so both answers are available and only
  one is kept in step.

## [1.1.2] - 2026-08-10

### Fixed

- **An `int` is now accepted where a `float` is declared**, as PEP 484's numeric tower says it
  must be and as every type checker treats it. `frequency: float` rejected `1`, and
  `Tuple[float, float]` rejected `(0, 90)` -- which is how anyone writes a range of degrees.
  The error named the tuple element, so it read as a collection problem rather than the
  numeric rule it was. `complex` likewise accepts `int` and `float`.

  Nothing widens in the other direction: an annotation asking for an `int` still means it, and
  a value is never quietly converted -- an `int` passed where a `float` is declared stays an
  `int`, and round-trips as one.

  The fix had to be made twice, in the compiled fast path used by the constructor and in the
  general checker used by `set` and item assignment, because the first reached only half the
  routes to an attribute. There is a test that goes through all three.

  Reported downstream, where adding an object with `pitch_range=(0, 90)` failed.

## [1.1.1] - 2026-08-10

### Fixed

- **A container or a project could not be versioned.** `SCHEMA_VERSION` and `migrate` were
  honoured by `BaseEntity.from_dict` and by nothing else, so the classes an application
  actually saves to a file -- a `BaseContainer`, a `Project` -- read their version key and
  ignored it. Raising `SCHEMA_VERSION` on a project did nothing at all, and an older file was
  restored as though its shape had never changed.

  All three now apply the same check, and a `Project` writes its version once it has one.
  Nothing is written while the version is 1, so a file saved by an application that never
  touches this is byte for byte what it always was.

  Found downstream, where the project class is exactly the thing worth versioning before its
  storage format changes.

### Upgrading from 1.1.0

| Symptom | Cause | What to do |
| --- | --- | --- |
| A `SCHEMA_VERSION` on a container or project that seemed to do nothing | It did nothing. | It works now. Write `migrate` before raising the version, or the older file will be refused with a message naming both versions. |
| Nothing else. | A class still at version 1 writes and reads exactly as before. | Nothing. |

## [1.1.0] - 2026-08-10

### Added

- **The built-in `Inspector` and `Configurator` descend into a named member of a collection.**
  A request against a collection means one of two things, and only the request can say which:
  `inspect(frequencies, get_all=None)` asks the collection, while
  `inspect(frequencies, name="IF1", get_frequency=None)` asks one member of it. The key is
  removed before descending, so the member sees only the methods meant for it.

  Two hooks make it work anywhere, because **the descent is not uniform**: `NESTED_KEY` is the
  attribute a request uses to name a member, and `_nested_getter(obj)` returns how to fetch
  one. A `BaseContainer` answers `get(name)`; a `Project` answers `get_observation(name)`;
  something else answers differently again, and overriding one method is enough.

  ```python
  class RegistryInspector(Inspector):
      NESTED_KEY = "entry"

      def _nested_getter(self, obj):
          return obj.get_entry if isinstance(obj, Registry) else super()._nested_getter(obj)
  ```

  Predicted under P3 before the built-ins existed and confirmed downstream, where ten
  container handlers exist for exactly this and could not adopt the built-ins without losing it.

### Changed

- A request naming `name` against a collection now descends instead of failing with
  `Method 'name' not found`. Nothing could have depended on that failure.

### Upgrading from 1.0.1

| Symptom | Cause | What to do |
| --- | --- | --- |
| A hand-written container handler that only descends | The built-ins now do it. | Delete it, or set `NESTED_KEY` and `_nested_getter` if your model names members differently. |
| Nothing else. | The hook is inert for anything that holds no members. | Nothing. |

## [1.0.1] - 2026-08-10

### Fixed

- **A mapping keyed by anything but `str` could not round-trip through JSON.** JSON has only
  string keys, so a `Dict[float, float]` -- how an instrument table is naturally spelled --
  came back with `"1420.0"` where it went out with `1420.0`, and validation rejected it. Values
  were already restored from the annotation; keys were not, which was an oversight in 0.6.0
  rather than a decision. `int`, `float` and `bool` keys are now restored from what the
  annotation declares, and a key that cannot be converted is left alone so the error still
  names the field.

  Found by a downstream project that keeps every instrument table this way and had written a
  `from_dict` override in each affected class to convert the keys by hand.

### Upgrading from 1.0.0

| Symptom | Cause | What to do |
| --- | --- | --- |
| A hand-written `from_dict` that converts mapping keys | The framework did not restore them. | It does now; the override can go. |
| Nothing else. | Only mappings whose declared key type is not `str` behaved differently, and they behaved by failing. | Nothing. |

## [1.0.0] - 2026-08-04

The contract is frozen. Nothing on the public surface will break outside a major version, and
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) says exactly what that covers -- because a
promise nobody can check is not one.

No behaviour changes here beyond the fix below. 1.0 is what the five releases before it earned,
not a feature.

### Added

- **[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md)**: the public surface, named member by
  member; the protected-but-promised extension points a `Super` subclass calls; what is private
  and therefore free to move; what serialized data guarantees; and the deprecation policy --
  announced in a MINOR release with a `DeprecationWarning` naming the replacement, removed no
  earlier than the next MAJOR. Also what is deliberately *not* promised: exception messages, log
  wording, performance numbers, and the thread safety of a single object.
- **[`docs/guide.md`](docs/guide.md)**: a working application built from nothing, in the order
  you would build it. Every block runs as part of the test suite.

### Fixed

- **`schema_version` is written only by a class that has actually versioned itself.** 0.6.0 put
  it into every serialized mapping, which broke deserialization downstream where `from_dict` is
  overridden per class and a careful override rejects keys it does not recognise. A class at the
  default version now serializes exactly as it did before versioning existed, and a mapping
  carrying no version still reads as version 1. Versioning costs nothing until it is used.

### Upgrading from 0.8.0

| Symptom | Cause | What to do |
| --- | --- | --- |
| A hand-written `from_dict` that broke in 0.6.0 | `schema_version` was written unconditionally. | Nothing — it is no longer written unless your class sets `SCHEMA_VERSION`. |
| Nothing else. | The freeze changes no behaviour. | Read [Compatibility](docs/COMPATIBILITY.md) to see what you may now rely on. |

## [0.8.0] - 2026-08-04

An asynchronous surface, added beside the synchronous one rather than in place of it. Every
signature that existed is what it was.

Fourth stage on the road to 1.0.0, and the last one carrying code. See
[the roadmap](docs/ROADMAP.md).

### Added

- **An `a`-prefixed twin of every facade**, plus `aprocess_request` and `abatch`:
  `await manipulator.ainspect(dish, get_diameter=None)`.
- **`Manipulator.close()` and context-manager support**, to shut the executor down. The
  executor is the one resource MSB owns, and it is created on first asynchronous use and never
  before, so an application that stays synchronous never starts a thread. Size it with
  `Manipulator(max_workers=...)`.
- **Coroutine methods on entities.** An entity may declare `async def fetch(self)`, and the
  asynchronous surface awaits it back on the loop.

### Notes on the design

Making the entry point `async def` and leaving everything below it alone does nothing, and the
suite contains the measurement that says so. Awaiting does not create concurrency; it marks a
point where control *may* be yielded, and a synchronous handler has none. During one 0.5-second
operation an event loop ran **zero** times for a plain call, **zero** for an `async def` entry
point over a synchronous handler, and **nineteen** once the work moved onto an executor.

So the whole synchronous pipeline runs on the executor, **interceptors included**. That is what
lets one interceptor serve both paths with no changes, and it means an interceptor runs on a
worker thread on the asynchronous path and cannot await inside it.

Threads rather than processes: the numerical libraries this was written for release the GIL, so
a thread is real parallelism there, and a process would have to pickle the model to reach the
work.

`abatch` still runs its requests one after another. They are independent and could overlap;
what concurrent requests touching one object should mean is the pipeline question, and it waits
for a real one to design against.

### Upgrading from 0.7.0

| Symptom | Cause | What to do |
| --- | --- | --- |
| Nothing. | Everything here is additive. | Nothing. Use the `a`-prefixed facades where a loop must stay responsive. |
| A thread pool outlives the application | An orchestrator that went asynchronous was never closed. | Call `close()`, or use it as a context manager. |

## [0.7.0] - 2026-08-04

The request contract. Every request can now be wrapped, an operation names the interface it
needs rather than the class it was handed, and reading and writing a model no longer require
writing any operation at all.

Third stage on the road to 1.0.0. See [the roadmap](docs/ROADMAP.md).

### Added

- **Interceptors.** `manipulator.add_interceptor(f)`, where `f(request, call_next)` returns a
  response. It may observe, time, **refuse** without running anything, or **rewrite** the
  request on the way through. Metrics, auditing, rate limiting and authorisation are four uses
  of this one hook, which is why MSB supplies the hook and none of the four: choosing a metrics
  backend would end the promise of no dependencies. Each entry of a batch is intercepted
  separately, and with none registered a request pays one check.
- **`RequestMetrics`**, an interceptor counting calls, failures and timings per operation, with
  `snapshot()` returning a plain mapping to export wherever you like.
- **`RequestJournal`**, an interceptor recording what ran. Read backwards it answers what
  produced a result -- `touching(name)` gives an object's whole history -- and read forwards,
  `replay(manipulator)` runs the session again.
- **`cache_statistics()`**, reporting how many objects cache, how many hold a mapping and how
  many entries those hold, computed on demand.
- **Built-in `inspect` and `configure`.** A `Manipulator` registers them unless told
  `builtins=False`, so an application that only reads and writes its model needs no `Super` of
  its own. `Inspector` applies every method a request names and reports each outcome;
  `Configurator` stops at the first failure, because a half-applied configuration is worse than
  a rejected one.
- **`MethodProvider` and `Interceptor` protocols**, in `msb_arch.protocols`.

### Changed

- **A fresh `Manipulator` has two operations rather than none.** Registering an operation of
  the same name replaces a built-in silently -- a default being overridden, not two intentions
  colliding -- so an application supplying its own `Inspector` behaves exactly as before. Two
  registrations of one name that are both yours still raise.
- **`Super.__init__` takes a `MethodProvider`, not a `Manipulator`.** It calls exactly one
  method on it. Nothing has to change: `Manipulator` satisfies the protocol structurally. The
  operation layer also stops importing the entry-point layer above it, an import that existed
  only to spell a type hint that was already a string.

### Upgrading from 0.6.0

| Symptom | Cause | What to do |
| --- | --- | --- |
| A test asserting a new `Manipulator` has no operations fails | It now has `inspect` and `configure`. | Assert what you mean, or construct with `builtins=False`. |
| `RegistrationError: Operation 'inspect' already registered` | The name was registered twice by your own code. Replacing a built-in is silent; replacing your own is not. | Register it once. |
| Nothing else. | Interceptors are opt-in, and the protocol change is structural. | Nothing. |

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
  framework and none downstream.
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
  `_validate_and_apply_method` and `_do_nested` are called 22, 33 and 9 times downstream
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
- `ScheduleManipulator` and `ScheduleProject` log strings copy-pasted from the application,
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
