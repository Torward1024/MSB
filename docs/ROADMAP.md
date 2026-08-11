# MSB Roadmap

1.0.0 is released. The road to it is closed, and this page is now about what comes after.

The scope rule that got it here still applies, and is the reason the release exists rather than
being perpetually one improvement away:

| Situation | What happens |
| --- | --- |
| A new idea arrives | It goes in the table below and waits its turn |
| A bug is found | Fixed if it breaks a documented promise; otherwise it queues with everything else |
| An item turns out bigger than its row | Cut it down or move it out. The release does not grow |
| An item could be "improved further" | It is done when its exit criterion is met. Nothing is done twice |

## After 1.0

Nothing here is scheduled. Each says what has to be true before it could sensibly start,
because guessing those answers is how two of the worst defects in this project's history got in.

| # | Item | Blocked on |
| --- | --- | --- |
| P1 | **Pipelines**, then a dependency-graph scheduler: topological order, parallel branches on the executor 0.8.0 introduced, incremental recomputation | One real dependent pipeline to design against, and a rule for which of a step's method results is its output |
| P10 | **Persistence** beyond `to_dict`/`from_dict` | Nothing technical. It is a product of its own, and 1.0 deliberately does not carry it |
| P18 | **`save` and `load` as built-in operations**, beside `Inspector` and `Configurator` | Nothing technical -- both mechanisms it needs already exist. Written out in pAstroCORE and measured there: the generic half is **57 lines with nothing domain-specific in them**, which every MSB application will otherwise write word for word, against 73 lines of genuinely application-specific overrides. `register_operation` already treats a built-in as a default an application may replace, and `_{operation}_{type}` resolution already lets one type take over without the generic method knowing. **Not worth a release of its own; it ships with P1.** Two things it must get right or it is worse than each application doing it itself: the file format stays a *default* (JSON over `to_dict`) that an application overrides rather than a law, and the write is atomic -- temporary file then rename -- which the pAstroCORE version deliberately does not do, because an interrupted write leaving a maimed file is tolerable in one application and not in a framework. The reason it matters is not code reuse: without it the request surface has a hole at the last step of every pipeline, so a journal replays every calculation of a session and not the save that ended it |
| P19 | **Routine serialization logs at INFO** | Reported from downstream, where opening one project filled the log with twenty identical lines: `Converted scan '...' to dictionary`, at INFO, once per scan per conversion. The count was a caller's fault and was fixed there, but the level is ours -- converting an object to a dictionary is the most ordinary thing this library does, and a message a user sees for it is noise by construction. INFO should mean something happened that a person would want to know about. Worth a sweep rather than one line: the same pattern is likely in every container | No routine `to_dict` or `from_dict` logs above DEBUG; a check counts INFO records emitted while serialising a container of a thousand items and expects none |
| P14 | **A derived model-graph API**: "what depends on `Telescope`" | Nothing. Cheap: a read over `_fields`, `_item_type_hint()` and `_parents`, all of which already hold the answer |
| P20 | **Derive the operation graph instead of asking for it** | Prototyped downstream and measured, which is why this is a line rather than a hope. A `Super`'s handlers already name themselves (`_calculate_*`), so the **node table and the labels need no declaration at all**. The edges between them are in the code: handlers call each other directly, and walking the AST of `ScheduleCalculator` recovered **all 14 result-to-result edges exactly** -- `times` as the root, `uv_coverage` needing visibility and positions, `beam_pattern` needing nothing. That is the graph P1 schedules on, derived from source with nothing written by hand. **What cannot be derived is which parts of the *model* a handler reads**: the same walk over-approximates, because a shared helper fetches telescopes, sources and scans whether the caller uses them or not -- six of fourteen came out wider than the truth. Deriving that would restore the coarseness the declaration exists to avoid, so it stays declared and the derivation becomes its *check*: a declaration naming something the code never touches is a typo, and one wider than the code is a leftover | The registry is a request. A framework user writes a handler and a schema entry and gets the graph; nothing asks them to restate what their own code already says |
| P4 | **Generating an application from the data model** | P10 and P14. Aim at the GUI wiring: measured downstream, 74.5% is already Qt Designer output and the handler stubs a generator would emit are 81 lines |
| P15 | **Lineage**: revision counters, then provenance derived from the request journal, then content hashing for memoisation | A decision about identity for mutable objects, which is the same decision incremental recomputation needs |
| P16 | **Performance**, as a story of its own and taken together with P1 | P1. Entity construction is 17x a plain object after P5, against roughly an order of magnitude better for a Rust-backed validator. Worth attacking, but not before pipelines: a scheduler changes what fast means |

### Pipelines, and the shape reserved for them

Settled on 2026-08-04 and worth not re-deciding:

- **A step names its input explicitly**, so a chain is the one-edge case of a dependency graph
  rather than a rival syntax to it.
- **Adaptation between two steps is itself a step**, written as an ordinary `Super`, never a
  callable between steps -- a callable would stop a request being data, and with it go
  serialization, history and replay.
- **Substitution happens before the interceptor chain**, so an interceptor always sees a
  concrete request and a recorded session stays replayable.

1.0 forecloses none of it: attribute values reach handlers unexamined, so a reference object
travels through `process_request` untouched today.

### Performance, and why it waits for pipelines

Where it stands: entity construction is 17x a plain object with the same four attributes, down
from 44x, and introspection per instance is gone. That is a reasonable place to stop for 1.0
and a poor place to stop forever -- a Rust-backed validator is roughly an order of magnitude
ahead, and pretending otherwise helps nobody.

It is deliberately coupled to P1 rather than pursued on its own, because a scheduler changes
what the word means. Shaving microseconds off constructing an object is worth little beside not
recomputing a branch at all, and the two answers compete for the same design: memoisation needs
content hashing, hashing needs identity for mutable objects, and identity is what P15 is about.
Optimising the single-object path first would be optimising the part a dependency graph makes
least important.

So the order is P1, then P15, then this -- and only then the question of whether the validation
path itself needs rewriting, measured against a real workload rather than a microbenchmark.

### Lineage, and the one hard problem

The valuable half of a dependency graph is provenance, and it needs no execution engine: the
journal shipped in 0.7.0 already records what each request consumed and produced. What is
unsolved is identity. Entities are mutable and addressed by `name`, so once an object changes,
the state that produced an earlier result has nothing to point at.

Four ways out, composing rather than competing:

| Approach | Cost | What it gives |
| --- | --- | --- |
| A revision counter, bumped on write | one `int` | "did this change", and an ordering. Nearly free: the place that invalidates the cache is the place that would bump it |
| The request journal | O(operations) | provenance itself, and any past state by replay from a checkpoint |
| A content hash, cached and invalidated like `to_dict` | a traversal | "is this the same input as last time", which memoisation needs |
| Snapshots through `to_dict` | O(model size) | exact past states, affordable as checkpoints rather than per step |

Order: counters, then the journal, then hashing, with snapshots only as the checkpoints replay
starts from. One constraint on all of it -- **replay assumes determinism**. A handler that reads
the clock, a file or a random seed cannot be reconstructed from its request alone.

### Shipped after 1.0

| # | Item | Release |
| --- | --- | --- |
| P17 | A nested-descent hook on the built-in `Inspector` and `Configurator` | 1.1.0. Predicted under P3 before the built-ins existed, confirmed by pAstroCORE, whose ten container handlers exist for exactly this |
| -- | Mapping keys restored from the annotation | 1.0.1. Also found by pAstroCORE: a `Dict[float, float]` could not round-trip through JSON at all |

### Rejected, and why

Recorded so each is decided once rather than argued again.

| Idea | Verdict |
| --- | --- |
| A dependency graph over `Super` **classes** | Ordering between operations is a property of a workflow, not of a class. Attaching it to the class freezes one scenario and destroys reuse, which is what a `Super` is for. The real graph is over steps -- P1 |
| A metrics backend, a rate limiter, an authorisation model | Policies. MSB supplies the interceptor and no dependencies |
| Object pooling | Entity construction cost was introspection, not allocation. P5 removed it: ten introspection calls per object became none |
| Parallel serialization, asynchronous invalidation | Measured slower than doing the work. `to_dict` of 8 containers of 3 000 items: 1.69x sequential with `asyncio.gather`, 1.11x with threads |
| A cache size limit | Bounded by the object graph, not by traffic: one mapping per caching object, 275 bytes per item. Documented instead, and reported by `cache_statistics()` |
| Health checks | A property of a service, not of a library |

## How 1.0.0 was reached

Five releases on 2026-08-04, nineteen items, each with an exit criterion decided before the
work started.

| Release | Theme | Closed |
| --- | --- | --- |
| **0.5.0** | Errors and measurement | Exception taxonomy; `TypeVar` resolution; benchmarks in CI; cache memory documented; every documentation example made to run |
| **0.6.0** | The data contract | Constraints on annotations; schema versions and migration; foreign data; a faithful JSON round trip; compiled validators; invalidation that stops when nothing can be stale |
| **0.7.0** | The request contract | The interceptor chain; request metrics; the request journal; the `MethodProvider` protocol; built-in `inspect` and `configure` |
| **0.8.0** | The asynchronous surface | An `a`-prefixed twin of every facade, running on an executor the framework owns |
| **1.0.0** | The freeze | The compatibility promise and the public surface; a guide to building an application |

What each release changed, and what to do about it, is in [`CHANGELOG.md`](../CHANGELOG.md).
What will not change is in [`COMPATIBILITY.md`](COMPATIBILITY.md).

### Things worth remembering

Not achievements -- the places where the obvious answer was wrong, kept because they will be
proposed again.

- **An asynchronous entry point over a synchronous handler does nothing.** Measured against a
  heartbeat: the loop ran zero times during a 0.5-second operation, exactly as for a plain
  call, and nineteen once the work moved onto an executor. Awaiting is not concurrency.
- **A ratio cancels how fast a machine is, not how much it varies.** A benchmark budget set
  from one sample failed CI on the same commit that had passed minutes earlier. Both sides are
  now sampled in one pass and the median taken.
- **An example that runs can still lie.** A documentation block printed `result: 8` and produced
  an error response; the test only caught exceptions. Claims are `assert`s now.
- **Putting a field in everybody's data for a feature most never use breaks people.**
  `schema_version` was written unconditionally in 0.6.0 and broke every hand-written `from_dict`
  override downstream. It is now written only by a class that has actually versioned itself.
- **Profile before optimising, even when the plan already says what to do.** Entity construction
  cost was 42 `isinstance` calls and ten introspection calls per object, all re-deriving the
  same answer about the same annotation -- not allocation, which is what pooling would have
  addressed.
