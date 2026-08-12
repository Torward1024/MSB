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
| P10 | **Persistence** beyond `to_dict`/`from_dict` | Nothing technical. It is a product of its own -- a storage format, migrations, partial reads -- and no release so far has needed to carry it. `save` and `load` (P18) cover the case every application actually has |
| P15 | **Lineage**: provenance derived from the request journal, then content hashing for memoisation | A decision about identity for mutable objects, which is the same decision incremental recomputation needs. **Revision counters shipped in 1.3.0** -- the one step that needed no such decision |
| P4 | **Generating an application from the data model** | P10. P14 is done. Aim at the GUI wiring: measured downstream, 74.5% is already Qt Designer output and the handler stubs a generator would emit are 81 lines |
| P16 | **Performance**, as a story of its own | Now unblocked: P1 has shipped, so what "fast" means is settled. Entity construction is 17x a plain object after P5, against roughly an order of magnitude better for a Rust-backed validator. Wants a real workload to measure against rather than a microbenchmark -- and the measurement discipline this project learned the hard way, twice |

### Pipelines: what was reserved, and what it became

Settled on 2026-08-04, shipped in 1.3.0, and all three held without amendment:

- **A step names its input**, so a chain is the one-edge case of a dependency graph rather than a
  rival syntax to it. Written as a value, since passing the step where the value goes says both
  *when* and *what*; `once()` is for the edges that are only about when.
- **Adaptation between two steps is itself a step**, written as an ordinary `Super`. There is
  deliberately no way to put a callable between two steps: a function is not data, and a pipeline
  holding one could not be stored, sent, journalled or replayed.
- **Substitution happens before the interceptor chain**, so an interceptor always sees a concrete
  request and a recorded session stays replayable. Checked by reading what an interceptor saw.

Four things the design earned while being built, none of them foreseen:

| Found | Answer |
| --- | --- |
| Writing a file and reading it back looked independent | `once()`: wait for a step without taking anything from it |
| A step after `configure` silently ran on the managing object | An operation that applies methods reports what they returned rather than handing the object on, so that is refused and says why |
| A step that ran four methods has no obvious output | One method, its value; several, `step["method"]` says which |
| A plan naming a live object could not be stored | An object travels as its own data under its type's name |

What is deliberately not there: recomputing only what changed. It needs to know whether an input
is the same input as last time, which is P15.

### Performance, now unblocked

Where it stands: entity construction is 17x a plain object with the same four attributes, down
from 44x, and introspection per instance is gone. A Rust-backed validator is roughly an order of
magnitude ahead of that, and pretending otherwise helps nobody.

It waited for P1 because a scheduler changes what the word means -- shaving microseconds off
constructing an object is worth little beside not recomputing a branch at all. P1 has shipped, so
the question is open again, with one condition attached: measure against a real workload rather
than a microbenchmark. This project has twice been wrong about where its own time went, and both
times the guess was reasonable.

### Lineage, and the one hard problem

The valuable half of a dependency graph is provenance, and it needs no execution engine: the
journal shipped in 0.7.0 already records what each request consumed and produced. What is
unsolved is identity. Entities are mutable and addressed by `name`, so once an object changes,
the state that produced an earlier result has nothing to point at.

Four ways out, composing rather than competing. **The first shipped in 1.3.0**, being the one
that needs no answer about identity:

| Approach | Cost | What it gives |
| --- | --- | --- |
| ~~A revision counter, bumped on write~~ | one `int` | **Done, 1.3.0.** "Did this change", without keeping a copy of what it was. Bumped where the cache is invalidated, as predicted: 114 ns against a 2 900 ns write. It counts writes rather than differences, is about one object rather than what it holds, and is not serialised |
| The request journal | O(operations) | provenance itself, and any past state by replay from a checkpoint |
| A content hash, cached and invalidated like `to_dict` | a traversal | "is this the same input as last time", which memoisation needs |
| Snapshots through `to_dict` | O(model size) | exact past states, affordable as checkpoints rather than per step |

Order: counters, then the journal, then hashing, with snapshots only as the checkpoints replay
starts from. One constraint on all of it -- **replay assumes determinism**. A handler that reads
the clock, a file or a random seed cannot be reconstructed from its request alone.

### Shipped after 1.0

| # | Item | Release |
| --- | --- | --- |
| P1 | **Pipelines**, and the scheduler over them | 1.3.0. A tree of requests: every step is an ordinary `process_request`, and what a pipeline adds is which step needs which, what one takes from another, and what to do with the rest when one fails. Every operation is a method on the pipeline with the facade's own signature, so a pipeline is written by writing the calls you would have made -- and the reference each call hands back is the edge. Topological stages fall out of the edges; two independent 0.3 s steps take 0.31 s through `arun` against 0.61 s in sequence. Built and run through the manipulator, and a plan is data, so what one end builds the other end replays. The three shapes reserved in 1.0 all held |
| P14 | **A derived model-graph API** | 1.3.0. `holds` is what a class declares; `held_by` is the same edges reversed, which is the direction nothing in the code answers and every caller asks in. `describe_model` on the manipulator, `catalogue` with `method="model"` as a request |
| P18 | **`save` and `load` as built-in operations** | 1.3.0. JSON over `to_dict` as a default an application replaces by registering its own, and an atomic write, which were the two conditions for it being better than each application doing it itself |
| P19 | **Routine work says nothing at INFO** | 1.3.0. Six messages moved to DEBUG; a check counts what is said while building, serialising and reading a container of a thousand items and expects nothing |
| P15a | **Revision counters** | 1.3.0. The first of P15's four steps, and the one needing no decision about identity |
| P17 | A nested-descent hook on the built-in `Inspector` and `Configurator` | 1.1.0. Predicted under P3 before the built-ins existed, and confirmed downstream: ten container handlers existed for exactly this |
| -- | Mapping keys restored from the annotation | 1.0.1. Also found downstream: a `Dict[float, float]` could not round-trip through JSON at all |

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
- **A machine's noise can be larger than the change being measured.** The revision counter
  looked like a 7.8% cost on the write path; three runs of the *same* code then gave 5.6, 4.1 and
  3.4 us. Sampling both sides in one pass said 114 ns.
- **Profile before optimising, even when the plan already says what to do.** Entity construction
  cost was 42 `isinstance` calls and ten introspection calls per object, all re-deriving the
  same answer about the same annotation -- not allocation, which is what pooling would have
  addressed.
