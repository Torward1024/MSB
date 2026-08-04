# MSB Roadmap

The path from 0.4.0 to 1.0.0, as a work list. Four releases, 17 open items, each with the
release it belongs to, what it depends on and what can go wrong.

**How to use this.** Take the next unstarted item in the release table currently in progress.
Do not take an item from a later release; the order exists to keep risky changes off an
unmeasured base.

## The scope rule

**The 1.0 scope is closed.** It is the 16 items in [The work](#the-work) and nothing else.

| Situation | What happens |
| --- | --- |
| A new idea arrives | Goes to [After 1.0](#after-10). No exceptions for small ones |
| A bug is found | Fixed if it breaks a documented promise; otherwise it goes after 1.0 |
| An item turns out bigger than its row | Cut it down or move it out. Do not grow the release |
| An item could be "improved further" | It is done when its exit criterion in the table is met. Nothing is done twice |

This section exists because the failure mode of this project is not missing features. It is
polishing without a stopping condition.

## Releases

| Release | Theme | Closes | Contract risk | Exit criterion |
| --- | --- | --- | --- | --- |
| **0.5.0** | Errors and measurement | B3, B1, P7, P9, P11 | **Low** — nothing changes what an annotation or a request means | CI fails on a performance regression; every documented example runs |
| **0.6.0** | The data contract | B2, B4, B9, B12, P5, P6 | **Medium** — annotations and serialized data gain meaning | A file written by 0.6.0 declares its version, survives a JSON round trip, and enforces a constraint on an annotation |
| **0.7.0** | The request contract | B11, P8, P12, B5, B8 | **Medium-high** — how a request is processed changes | Every request passes an interceptor chain; a `Manipulator` works with no `Super` written by hand |
| **0.8.0** | The async surface | B7 | **Low** — purely additive | `await manipulator.acalculate(...)` keeps an event loop responsive |
| **1.0.0** | The freeze | B10, P13 | **None** — no code changes | Deprecation policy published, public surface marked, an application guide exists |

Sequencing rationale, once: measurement before optimisation, so 0.5.0 precedes 0.6.0. Data
semantics before request semantics, because `_apply_methods` validates what the data layer
defines. The additive surface after both, so it wraps a settled protocol. The freeze last.

## The work

Status: **done** (merged or on a branch), **next** (the item to pick up), **open**.

### 0.5.0 — errors and measurement

| # | Item | Depends on | Risk | Exit criterion | Status |
| --- | --- | --- | --- | --- | --- |
| B3 | Exception taxonomy: `MSBError` root, 16 types, each also deriving from the built-in it replaces | — | Behaviour visible to anyone catching exceptions | No bare built-in raised in the package; no existing test changed | **done** |
| B1 | `TypeVar` resolution: resolve by parameter position, treat constraints as a union, fall back to `Any` when unparameterized | — | Corrects a type that is wrong today, so behaviour changes | `Generic[T, U]` resolves each parameter to its own type | **done** |
| P7 | Benchmark suite in CI | — | None | A performance regression fails a build | **done** |
| P9 | Document the cache's memory behaviour | — | None | The reader can predict the cost without measuring | **done** |
| P11 | Repair the 11 documentation examples that no longer run | — | None | `STALE` in `tests/test_documentation.py` is empty | **done** |

### 0.6.0 — the data contract

| # | Item | Depends on | Risk | Exit criterion | Status |
| --- | --- | --- | --- | --- | --- |
| B2 | Value constraints on annotations: `Annotated[float, Positive()]`, wired to `utils/validation.py` | B3 | Adds meaning to an annotation | A negative price is rejected by the model, not by a hand-written `__init__` | **done** |
| B4 | Schema version in serialized data, and a migration hook | B3 | Changes what `to_dict` writes | A file written by an earlier version still loads, or fails with a migration error naming the version | **done** |
| B9 | Ingest foreign data: a declared discriminator, or a default type per field | B4 | Changes `from_dict` | JSON not produced by MSB restores into a declared model | **done** |
| B12 | Make `to_dict`/`from_dict` actually round-trip through JSON | B4 | Changes what `to_dict` emits | `json.loads(json.dumps(obj.to_dict()))` restores an equal object for every supported annotation | **done**. Larger than the row implied: descent stopped at the attribute, so entities inside a list or dict were left as live objects, not just sets and tuples mis-typed |
| P5 | Compile a validator per field once per class | B2, P7 | Rewrites the validation hot path | Entity construction measurably faster; the benchmark budgets of 65x and 12 introspection calls tightened to match | open |
| P6 | Skip the invalidation walk when no owner caches | P7 | Small, isolated | The idle walk costs nothing when nothing caches | **next** |

### 0.7.0 — the request contract

| # | Item | Depends on | Risk | Exit criterion | Status |
| --- | --- | --- | --- | --- | --- |
| B11 | Interceptor chain around `process_request` | B3 | Changes how every request is processed | An interceptor sees each request before it runs and its response after, on both the sync and async paths | open |
| P8 | Observability hooks as the first interceptor | B11 | None beyond B11 | Serialization time, cache size, invalidation frequency and validation failures are observable without a dependency | open |
| P12 | Request journal: a built-in interceptor recording what each request consumed and produced | B11 | None beyond B11 | A session can be replayed from its journal; a result can be traced to the request that produced it | open |
| B5 | A protocol for what `Super` needs from `Manipulator`, replacing the concrete reference | — | Changes the extension contract | `Super` names an interface, not a class. One method: `get_methods_for_type` | open |
| B8 | Built-in `Inspector` and `Configurator`, registered by default | B5 | Changes the duplicate-name rule | A `Manipulator` handles `inspect` and `configure` with no `Super` written by hand; an application registering its own still works unchanged | open |

### 0.8.0 — the async surface

| # | Item | Depends on | Risk | Exit criterion | Status |
| --- | --- | --- | --- | --- | --- |
| B7 | Additive async surface: `aprocess_request` and async facades, sync handler on an executor, coroutine handler awaited directly | B11 | Additive only; no sync signature changes | An event loop stays responsive during a long operation; the sync API is untouched | open |

### 1.0.0 — the freeze

| # | Item | Depends on | Risk | Exit criterion | Status |
| --- | --- | --- | --- | --- | --- |
| B10 | Publish the deprecation policy; mark the public surface | all above | None | Every underscore-prefixed name is either a documented extension point or private | open |
| P13 | A guide to building an application on MSB | all above | None | A reader who has never seen MSB has a working application by the end | open |

## Decisions taken

Settled, with the reasoning compressed to its conclusion. Reopen only on new evidence.

| # | Question | Decision | Evidence |
| --- | --- | --- | --- |
| B6 | Pipelines: dependent steps in a batch | **After 1.0.** Shape reserved: a step names its input explicitly, so a chain is the one-edge case of a graph rather than a rival syntax. Adaptation between steps is itself an operation, never a callable | No dependent pipeline exists to design against. 1.0 forecloses nothing: attribute values reach handlers unexamined |
| B7 | Asynchrony | **Additive surface**, not async all the way down | An `async def` entry point over a synchronous handler let the event loop run 0 times during a 0.5 s operation — the same as a plain call. Only an executor helped (20 times) |
| B8 | Built-in `Inspector` and `Configurator` | **Ship, registered by default.** A user registration replaces a built-in silently; two user registrations of one name still raise | 20 of 21 downstream handlers hold no domain logic; `inspect` and `configure` serve 185 of 194 facade calls |
| — | Metrics, audit, rate limiting, authorisation | **One hook, not four features.** All are interceptors (B11) | A library choosing a metrics backend would end the zero-dependency property |
| — | Graceful shutdown, health checks | **Not applicable.** MSB owns no processes or connections | A library has no health; the service hosting it does |
| — | Lineage | **Separable from scheduling, and precedes it.** Recording rides on B11 (P12); the graph is derived from the journal, not declared in advance | A request is already data and `to_dict` already exists, so the expensive precondition is met |
| — | Mutable identity for lineage and incremental recompute | Revision counters first, then the journal, then content hashing, with snapshots only as checkpoints | A counter rides on the invalidation walk that already exists; a hash costs a traversal; snapshots cost the model size |
| — | A dependency graph over `Super` classes | **Rejected.** Ordering between operations is a property of a workflow, not of a class; attaching it to the class freezes one scenario and destroys reuse. The real graph is over steps, which is B6 | The entity graph, by contrast, already exists twice: statically in `_fields` and `_item_type_hint()`, at runtime in `_parents` |
| — | A wizard that draws the graphs | Belongs to P4, and reads the entity graph rather than authoring it | Two sources of truth would drift. The annotations already are the graph |

## Not in 1.0

The stop list. Each of these is a reasonable idea, and each is out.

| Item | Why not |
| --- | --- |
| Persistence beyond `to_dict`/`from_dict` | A store is a product of its own, and how data is kept is the application's decision. What MSB owes it is a serialization API good enough to build any store on: a faithful round trip (B12), a version to migrate from (B4), and a discriminator for data it did not write (B9). Those are in 1.0; the store is not |
| Pipelines and the DAG scheduler | Nothing to design against yet; see B6 |
| Application generation from the model (P4) | Follows persistence and the async surface |
| A plugin system | Nothing has asked for one |
| A metrics backend, a rate limiter, an auth model | Policies. MSB provides the hook (B11) and no dependencies |
| Object pooling | Profiling puts entity construction cost in type-hint introspection, which P5 removes; pooling would not touch it |
| Parallel serialization, async invalidation | Measured as slower. `to_dict` of 8 containers × 3 000 items: 1.69× sequential with `asyncio.gather`, 1.11× with threads |
| A cache size limit | Bounded by the object graph already, not by traffic: one mapping per caching object, 275 bytes per item, 5.25 MB at 20 000. Documented (P9) rather than capped |

## After 1.0

| # | Item | Blocked on |
| --- | --- | --- |
| P1 | Pipelines, then the dependency-graph scheduler: topological order, parallel branches, incremental recomputation | A real dependent pipeline to design against; a declared output per step |
| P10 | Persistence | — |
| P4 | Generating an application from the data model | P10, B7. Aim at GUI wiring: downstream, 74.5% is already Qt Designer output and the handler stubs a generator would emit are 81 lines |
| P14 | A derived model-graph API: "what depends on `Telescope`" | — . Cheap: a read over `_fields`, `_item_type_hint()` and `_parents` |

## What 1.0.0 means

A promise that the contract will not break outside a major version. Five releases went out on
2026-08-03, four of them breaking, so the promise is earned by the work above, not declared.

| What is frozen | Settled by |
| --- | --- |
| The request and response protocol, including `MethodResults` and what a facade unwraps | B11, B7 |
| The extension contract: what a `Super` implements and what it sees instead of a `Manipulator` | B5, B8 |
| The entity model and what an annotation means | 0.3.0, then B1, B2 |
| Serialized data, carrying its own version | B4, B9 |
| The exception types a caller may catch | B3 |
| The public surface, and how long a superseded name survives | B10 |
| Performance, defended by CI rather than by memory | P7 |

Already true, and not to be re-litigated: more than one project depends on MSB in earnest
(pAstroCORE and an observatory scheduling system), there are 519 tests at 90% coverage, and
the framework has no external dependencies.

## History

Thirty-two review findings, closed across five releases on 2026-08-03. Each release carries
an upgrade table in [`CHANGELOG.md`](../CHANGELOG.md).

| Release | What it settled | Breaking |
| --- | --- | --- |
| 0.2.0 | 26 findings from the 0.1.3 review: nested generic validation, cache correctness and cost, the root-logger seizure, cyclic references, polymorphic restore, `Super.execute` resolving any named attribute | yes |
| 0.3.0 | `BaseContainer` stopped inheriting `BaseEntity`; `Serializable` became the shared base and the two became siblings. Weak class registry; invalidation reaching every owner | yes |
| 0.3.1 | `to_dict()` takes no arguments again; cycle-detection state moved to a context variable | a repair |
| 0.3.2 | Thread safety: the class registry, the container-class cache and handler resolution are guarded, with tests that fail without the guards | no |
| 0.4.0 | `Super._apply_methods` owns the handler loop; a result reports every method it ran; `Manipulator.batch`. Downstream, 22 handlers of 667 lines became 81 | opt-in |

### Audit of the 2026-08-04 feedback list

Kept because it records what was measured rather than assumed. Concerns not listed here were
confirmed and became items above.

| Concern | Verdict |
| --- | --- |
| `_resolve_type` picks the wrong `Union` member in `from_dict` | **Not confirmed.** `to_dict` always writes `type`; without it the call fails loudly rather than guessing. The real gap was ingesting foreign data — B9 |
| The `to_dict` cache grows without limit | **Not as stated.** One mapping per caching object, bounded by the object graph |
| No object pooling | **Real cost, wrong remedy.** 13.1 µs per entity against 0.30 µs for a plain class with the same four attributes — 44x — but the time is in introspection, ten `get_origin`/`get_args` calls per object, not allocation. P5 |
| Parallel serialization, async invalidation | **Wrong.** Both measured slower than doing the work |
| `_invalidate_cache` is expensive | **Confirmed, and worse.** 3.3 µs with no owners against 413 µs with 500, of which 277 µs is spent reaching nothing. P6 |
| No runtime contract checking | **Confirmed.** Types are checked, values are not. B2 |
| `Super` and `Manipulator` are tightly coupled | **Confirmed, and small.** One method is called on it. B5 |
| Tests are critical | Already true: 519 tests, 90% coverage, including concurrency tests that fail without their guards |

Two gaps came out of the same pass that nobody had listed: no exception taxonomy (B3) and no
schema version in serialized data (B4).
