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

## Planned, not scheduled

Four directions that are wanted and deliberately not started. Each was raised on 2026-08-03
and left until there is a real case to design against.

| # | Item | Notes |
| --- | --- | --- |
| P1 | **Pipelines**: a request in a batch that depends on the result of an earlier one | `batch` runs independent requests. Feeding one result into the next must not be done with callables between steps: a request would stop being data, and with it go serialization, history and replay -- the properties the orchestrator exists for, and the reason an external caller can drive it at all. The shape that keeps them is a reference inside the request, `Ref("step_id", "method_name")`, substituted before the step runs. Three things need deciding first: how a reference addresses a result now that a step reports every method it ran, what happens to steps that depend on a failed one, and whether substitution belongs in the Manipulator or in a layer above it. None of that should be guessed: there is no dependent batch anywhere yet, so there is nothing to design against |
| P2 | **Asynchronous Manipulator**: `await manipulator.calculate(...)` | The calculations in the downstream project are long, and the GUI blocks on them today. The awkward part is not the plumbing but the contract: whether an operation may be sync and async at once, whether `Super` handlers become coroutines or run in an executor, and what a batch means when its requests overlap in time. The thread-safety work in 0.3.2 is a prerequisite and is done |
| P3 | **Built-in `Inspector` and `Configurator`** | Requested by a downstream author on 2026-08-03, and the natural continuation of `_apply_methods`: the framework took the loop, and the handler around it turns out to be nearly empty too. Measured on pAstroCORE after that migration, 20 of its 21 handlers contain no domain logic at all -- six are literally a type check and one call, and the type check is redundant because dispatch already selected the handler by type. Shipping an `Inspector` and a `Configurator` would delete all of them but one, `_configure_scheduleproject`, which really does have domain logic. Three things decide whether it works: the nested descent is not uniform, since containers expose `get(name)` while a `Project` exposes `get_observation(name)`, so it needs a hook rather than a convention; a built-in `Configurator` returns `MethodResults` instead of the bespoke value each handler invents today, which touches 2 of 62 call sites because a configure result is almost never read; and the classes have to stay thin over `_apply_methods` with named hooks, or subclasses will override everything and end up worse off than with a hand-written handler. Only `inspect` and `configure` generalise -- they fall straight out of the request model, where an attribute names a method -- while operations such as `calculate` and `visualize` are domain work and stay bespoke. Those two cover 185 of the 194 facade calls downstream |
| P4 | **Generating an application from the data model** | The downstream author is building a WYSIWYG editor that lays out entities and their Super classes and emits Python skeletons. Measuring pAstroCORE shows where the leverage actually is: 74.5% of it is already generated, by Qt Designer, and of the rest the data model is 4.4% and the operations 7.5% -- of which the handlers this would scaffold are 81 lines, four each. Skeletons that small are faster to type than to find in an editor. The 11.7% written by hand is GUI wiring: tables over containers, dialogs over entity attributes, validation, saving back. MSB already holds everything that needs -- `_fields` with types, which attributes are optional, `Literal` as a ready list of choices, nested entities, containers, validation -- so the target worth aiming at is generating those forms and tables, not the handler stubs. One constraint to design in from the start: a template carrying "your logic here" cannot be regenerated once it has been edited. Generating only what follows from the model, into files nobody edits, and leaving user code in subclasses beside them, keeps regeneration possible. For the digital-twin and platform cases mentioned alongside this, two things are missing first: persistence beyond `to_dict`/`from_dict`, and P2 |

## What 1.0.0 should mean

A 1.0 is a promise rather than a feature count: that the contract will not break outside a
major version. Four releases went out on 2026-08-03, three of them changing the contract, so
the promise is not close yet. It becomes possible when there is nothing left that would
force a break, which puts these in the way.

**Decisions that must be made first.** Each of the three planned directions changes
something a caller depends on, so 1.0 cannot precede them -- they have to be decided, not
necessarily built:

- P1 changes the shape of a request, by putting references to earlier results inside it.
- P2 changes every signature, because retrofitting async is not additive.
- P3 changes what a handler looks like, and therefore what a downstream author writes.

**What must then hold:**

| | |
| --- | --- |
| The request and response protocol is frozen | Including `MethodResults` and what a facade unwraps |
| The extension contract is frozen | What a `Super` subclass implements and which helpers it may call |
| The entity model is frozen | Settled in 0.3.0 when `Serializable` split the hierarchy |
| A deprecation policy is written down | How long a name survives after it is superseded, and how it is announced |
| There is a guide to building an application | The docs describe the API well and never show how to start a project on it |
| More than one project depends on it in earnest | Already true: pAstroCORE and an observatory scheduling system |

**What 1.0 is not.** Not persistence, not a UI generator, not a plugin system. Those belong
to whatever is built on MSB. A framework earns 1.0 by holding still, not by growing.
