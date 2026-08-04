# MSB Roadmap

Two things live here: what a review of the 0.1.3 MVP turned up and where each finding was
resolved, and where the framework is going next.

Nothing from the review is open. The sections after it are planning, not a backlog: each
entry records what would have to be decided before it could be built, because guessing
those answers is how two of the bugs below got in.

## Resolved, by release

Thirty-two findings, closed across five releases on 2026-08-03. Each release carries an
upgrade table in [`CHANGELOG.md`](../CHANGELOG.md).

### 0.2.0 — the review

| # | Finding | Breaking |
| --- | --- | --- |
| F1 | `_validate_type` compared `get_origin()` against `typing.List`, so element types inside `List[T]` were never checked and nested generics raised on valid data | **yes** |
| F2 | An attribute named `value` could not be None, so `clear()` produced objects that could not be restored | no |
| R1 | `_type_cache` was shared across the hierarchy and keyed by name, so two modules declaring the same name collided | no |
| R2 | `__del__` called `clear()`, and a container emptied the caller's dict on garbage collection | no |
| R3 | Cache invalidation walked every item, making `add` quadratic: 4000 items took 1.4 s | no |
| R4 | `@lru_cache` on an instance method meant no `Manipulator` was ever collected | no |
| R5 | Importing the package seized the root logger and wrote `output.log` in the working directory | **yes** |
| R6 | Cyclic references exhausted the stack despite being advertised as supported | no |
| R7 | `from_dict` resolved types through the framework module's globals, so polymorphic restore never worked | no |
| R8 | Internal fields leaked into `clear()`, `__eq__` and `__repr__` | `repr` only |
| R9 | `Super.execute` resolved any attribute named in a request; `method="clear"` wiped the instance | **yes** |
| R10 | An operation named after a `Manipulator` method shadowed it and recursed | only broken registrations |
| R11 | Validating the cache re-serialized everything it was meant to save, and still missed the stale case | read-only mapping |
| R12 | `__eq__` without `__hash__` made every entity unhashable | no |
| R14 | `_create_container` built a class per call, so two projects held incomparable containers | no |
| R15 | `Project.from_dict` was abstract with a body, forcing a stub nobody could fill | no |
| R16 | `remove()` logged a warning and then failed with a bare `KeyError` | no |
| R17 | `add()` deep copies by default; the cost and the identity change are now documented | no |
| R18, R18b | Unreachable cache machinery removed; what remained now caches handler resolution | no |
| R20–R22, R24–R26 | `py.typed`, `MANIFEST.in` paths, version badge, copy-paste leftovers, flaky timing assertions, a documentation claim that did not hold | no |
| R23 | Tests imported from `src/`, so the built distribution was never exercised | no |

### 0.3.0 — the hierarchy

| # | Finding | Breaking |
| --- | --- | --- |
| R13 | `BaseContainer` inherited `BaseEntity` and gave fourteen members a different meaning. `Serializable` is now the shared base and the two are siblings | **yes** |
| R27 | The class registry held strong references, so nothing declared was ever released | no |
| R28 | Invalidation reached one owner, so an item shared by two containers left one stale | no |
| R29 | `Super`'s extension points documented; its last unused helpers removed | only removals |

### 0.3.1 — a break of our own making

| # | Finding | Breaking |
| --- | --- | --- |
| R31 | Cycle detection threaded its state through a `_seen` parameter, so every downstream override written as `def to_dict(self)` failed. The state moved to a context variable | no, a repair |

### 0.3.2 — concurrency

| # | Finding | Breaking |
| --- | --- | --- |
| R19 | Shared state was unguarded: sixteen threads building the first project of a type produced up to fifteen competing container classes, and the handler cache lost entries. Both are covered by tests that fail without the guards | no |

### 0.4.0 — the operation layer

| # | Finding | Breaking |
| --- | --- | --- |
| R32 | Every handler wrote the same loop by hand. `Super._apply_methods` owns it, and a result now reports every method it ran rather than the last, which is what makes a request history replayable | no, opt-in |
| R33 | The sequence form of `process_request` had no facade, hence no users and no coverage. `Manipulator.batch` is that facade | no |
| R30 | Consumer side: the 22 handlers in pAstroCORE moved onto `_apply_methods`, 667 lines becoming 81, and the failure policy they disagreed on was settled | the policy changed for `configure` |

## Audit of the 2026-08-04 feedback list

A list of concerns was raised for review. Each was checked against the code rather than
accepted, because several turned out to describe something other than what is there. The
evidence column is what was measured, not what was expected.

| Concern | Verdict | Evidence |
| --- | --- | --- |
| `TypeVar` in `_resolve_type` breaks on complex annotations | **confirmed, three separate bugs** | `Generic[T, U]` resolves both parameters to `args[0]`, so the second field gets the first type; `TypeVar('V', int, str)` accepts only `int`; an unparameterized `Generic[U]` raises at construction |
| `_resolve_type` for `Union` in `from_dict` may pick the wrong type | **not confirmed** | `to_dict` always writes `type`, and both entity attributes and container items restore correctly. Without it the call fails loudly rather than guessing |
| — but nothing can read foreign JSON that has no `type` | **real gap, newly found** | There is no way to declare a discriminator or a default, so data not produced by MSB cannot be ingested |
| `_invalidate_cache` walks the graph synchronously and may be expensive | **confirmed, and worse than stated** | 3.3 µs with no owners against 413 µs with 500. The walk also runs when nothing caches at all, costing 277 µs of the 413 for no result |
| The `to_dict` cache has no size limit and may grow | **not as stated** | One mapping per object with `use_cache=True`, so it is bounded by the object graph: 3.8 MB for a 20 000-item container. It is never evicted and duplicates the data, which is worth documenting rather than capping |
| No object pooling for many small objects | **real cost, wrong remedy** | Constructing an entity costs 10.5 µs against 0.56 µs for a plain dict. Profiling puts the time in repeated type-hint introspection — `get_origin` and `get_args` are each called 150 000 times for 30 000 objects — not in allocation, which pooling would not touch |
| No runtime contract checking, Pydantic style | **confirmed** | Types are checked, values are not: a dish accepts `diameter=-5.0` and an empty band. `utils/validation.py` already has `check_positive`, `check_range` and the rest, but nothing connects them to annotations |
| `Manipulator` and `Super` are tightly coupled through `_manipulator` | **confirmed, and small** | `Super` calls exactly one method on it, `get_methods_for_type`, so a one-method protocol replaces the dependency |
| No asynchrony | true | Recorded as P2 |
| No persistence | true | Recorded below |
| No monitoring, hard to debug in production | true | Recorded below |
| Parallel serialization with `asyncio.gather` | **wrong** | `to_dict` is pure CPU. Gathering eight containers of 3 000 items takes 1.69x the sequential time; a thread pool takes 1.11x |
| Asynchronous `_invalidate_cache` | **wrong** | Microseconds of pure CPU; awaiting it costs more than doing it |
| No profiling of hot spots | true | There is no benchmark suite, so a regression is only visible when someone measures by hand |
| Tests are critical for maintenance | already done | 485 tests, 90% coverage, including concurrency tests that fail without their guards |

Two further gaps came out of the same pass, neither of them on the list:

| Gap | Evidence |
| --- | --- |
| **No exception taxonomy** | Ninety `raise` statements, all of them bare `ValueError`, `TypeError` or `KeyError`, and no exception type of the framework's own. A caller cannot tell a validation failure from a misconfiguration from an ordinary Python error |
| **No schema version in serialized data** | `to_dict` writes `type` but nothing about the shape it was written with. Rename a field and every file saved before it becomes unreadable, with no way to migrate. pAstroCORE saves projects to disk, so this is not hypothetical |

## The road to 1.0.0

A 1.0 is a promise that the contract will not break outside a major version. The work below
is ordered by whether it blocks that promise, not by how interesting it is.

### Blocking — each changes something a caller depends on

| # | Item | Why it blocks |
| --- | --- | --- |
| B1 | Fix `TypeVar` resolution: resolve by parameter position, treat constraints as a union, fall back to `Any` when unparameterized | Corrects a wrong type today, so it changes behaviour |
| B2 | Value constraints on annotations, e.g. `Annotated[float, Positive()]`, wired to the helpers already in `utils/validation.py` | Adds to what an annotation means; `_check_type` already unwraps `Annotated`, so the hook exists |
| B3 | An exception taxonomy: `MSBError` with `ValidationError`, `ResolutionError`, `OperationError` beneath it, each still deriving from the built-in it replaces | What a caller may catch is part of the contract |
| B4 | A schema version in serialized data, and a migration hook | Otherwise 1.0 promises to read files it will not be able to read |
| B5 | A protocol for what `Super` needs from `Manipulator`, replacing the concrete reference | The extension contract must name an interface, not a class |
| B6 | Decide P1 pipelines | Changes the shape of a request |
| B7 | Decide P2 asynchrony | Cannot be added later without touching every signature |
| B8 | Decide P3 built-in `Inspector` and `Configurator` | Changes what a downstream handler looks like |
| B9 | Ingesting foreign data: a declared discriminator, or a default type per field | Changes `from_dict` |
| B10 | Write down the deprecation policy and mark the public surface | The promise needs stating before it can be kept |

### Should be in 1.0, but breaks nothing

| # | Item | Measured reason |
| --- | --- | --- |
| P5 | Compile a validator per field once per class instead of re-deriving `get_origin`/`get_args` per instance | 150 000 introspection calls for 30 000 objects; entity construction is 19x a plain dict |
| P6 | Skip the invalidation walk when no owner caches | 277 µs of the 413 µs at 500 owners is spent reaching nothing |
| P7 | A benchmark suite in CI, so a performance regression fails a build | Yesterday every performance number was measured by hand |
| P8 | Observability hooks: serialization time, cache size, invalidation frequency, validation failures | Asked for, and cheap once there is one place to hang them |
| P11 | Repair the ten documentation examples that no longer run, and add a test that executes every fenced Python block so they cannot rot again | Executing each document's blocks in order, as a reader would: `mega.md` 6 of 17 broken, `super.md` 2, `base.md` 1, `examples.md` 1. `api.md` blocks are signature fragments and are not meant to run |
| P9 | Documented memory behaviour of the cache: one mapping per object, duplicated, never evicted | Cheaper than capping it, and enough for a reader to decide |

### After 1.0

| # | Item | Note |
| --- | --- | --- |
| P4 | Generating an application from the data model | The WYSIWYG editor. Aim at the GUI wiring rather than the handler stubs — see the entry below |
| P10 | Persistence beyond `to_dict`/`from_dict` | A store is a product of its own; 1.0 should not carry it |

## Planned, not scheduled

Four directions that are wanted and deliberately not started. P1, P2 and P3 block 1.0 as
decisions -- they have to be settled, not necessarily built -- while P4 follows it.

| # | Item | Notes |
| --- | --- | --- |
| P1 | **Pipelines**: a request in a batch that depends on the result of an earlier one | `batch` runs independent requests. Feeding one result into the next must not be done with callables between steps: a request would stop being data, and with it go serialization, history and replay -- the properties the orchestrator exists for, and the reason an external caller can drive it at all. The shape that keeps them is a reference inside the request, `Ref("step_id", "method_name")`, substituted before the step runs. Three things need deciding first: how a reference addresses a result now that a step reports every method it ran, what happens to steps that depend on a failed one, and whether substitution belongs in the Manipulator or in a layer above it. None of that should be guessed: there is no dependent batch anywhere yet, so there is nothing to design against |
| P2 | **Asynchronous Manipulator**: `await manipulator.calculate(...)` | The calculations in the downstream project are long, and the GUI blocks on them today. The awkward part is not the plumbing but the contract: whether an operation may be sync and async at once, whether `Super` handlers become coroutines or run in an executor, and what a batch means when its requests overlap in time. The thread-safety work in 0.3.2 is a prerequisite and is done |
| P3 | **Built-in `Inspector` and `Configurator`** | Requested by a downstream author on 2026-08-03, and the natural continuation of `_apply_methods`: the framework took the loop, and the handler around it turns out to be nearly empty too. Measured on pAstroCORE after that migration, 20 of its 21 handlers contain no domain logic at all -- six are literally a type check and one call, and the type check is redundant because dispatch already selected the handler by type. Shipping an `Inspector` and a `Configurator` would delete all of them but one, `_configure_scheduleproject`, which really does have domain logic. Three things decide whether it works: the nested descent is not uniform, since containers expose `get(name)` while a `Project` exposes `get_observation(name)`, so it needs a hook rather than a convention; a built-in `Configurator` returns `MethodResults` instead of the bespoke value each handler invents today, which touches 2 of 62 call sites because a configure result is almost never read; and the classes have to stay thin over `_apply_methods` with named hooks, or subclasses will override everything and end up worse off than with a hand-written handler. Only `inspect` and `configure` generalise -- they fall straight out of the request model, where an attribute names a method -- while operations such as `calculate` and `visualize` are domain work and stay bespoke. Those two cover 185 of the 194 facade calls downstream |
| P4 | **Generating an application from the data model** | The downstream author is building a WYSIWYG editor that lays out entities and their Super classes and emits Python skeletons. Measuring pAstroCORE shows where the leverage actually is: 74.5% of it is already generated, by Qt Designer, and of the rest the data model is 4.4% and the operations 7.5% -- of which the handlers this would scaffold are 81 lines, four each. Skeletons that small are faster to type than to find in an editor. The 11.7% written by hand is GUI wiring: tables over containers, dialogs over entity attributes, validation, saving back. MSB already holds everything that needs -- `_fields` with types, which attributes are optional, `Literal` as a ready list of choices, nested entities, containers, validation -- so the target worth aiming at is generating those forms and tables, not the handler stubs. One constraint to design in from the start: a template carrying "your logic here" cannot be regenerated once it has been edited. Generating only what follows from the model, into files nobody edits, and leaving user code in subclasses beside them, keeps regeneration possible. For the digital-twin and platform cases mentioned alongside this, two things are missing first: persistence beyond `to_dict`/`from_dict`, and P2 |

## What 1.0.0 should mean

A 1.0 is a promise rather than a feature count: that the contract will not break outside a
major version. Five releases went out on 2026-08-03, four of them changing the contract, so
the promise is not close. It becomes possible when nothing is left that would force a break
— which is what the blocking list above enumerates.

**What must hold when the blocking work is done:**

| | |
| --- | --- |
| The request and response protocol is frozen | Including `MethodResults` and what a facade unwraps |
| The extension contract is frozen | What a `Super` subclass implements, which helpers it may call, and the protocol it sees instead of a `Manipulator` |
| The entity model is frozen | Settled in 0.3.0 when `Serializable` split the hierarchy; B1 and B2 are the last changes to what an annotation means |
| Serialized data carries its version | So a file written by 1.0 is still readable by 1.9 |
| Errors are the framework's own types | So a caller can catch precisely rather than by string matching |
| A deprecation policy is written down | How long a name survives after it is superseded, and how it is announced |
| The public surface is marked | Which underscore-prefixed names are protected extension points and which are genuinely private |
| There is a guide to building an application | The docs describe the API well and still never show how to start a project on it |
| Performance is defended by CI | A benchmark suite, so a regression fails a build instead of being noticed months later |
| More than one project depends on it in earnest | Already true: pAstroCORE and an observatory scheduling system |

**What 1.0 is not.** Not persistence, not a UI generator, not a plugin system, not
asynchrony unless P2 is decided in its favour. Those belong to whatever is built on MSB, or
to a later minor. A framework earns 1.0 by holding still, not by growing.

**On "enterprise-grade".** Nothing in the list above is specific to large organisations. A
scientist writing a simulation and a team running a service want the same things from a
framework: that it says no to bad data early, that its errors can be caught precisely, that
files written last year still open, that a mistake is visible in logs, and that the API they
learned still works. The only thing genuinely peculiar to scale is P2 and P10 — concurrency
and a store — and both are recorded as decisions rather than assumptions.
