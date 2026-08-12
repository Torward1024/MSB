# Roadmap

**The queue is empty.** Everything planned after 1.0 shipped in 1.3.0: pipelines and the
scheduler over them, the derived model graph, built-in `save` and `load`, scaffolding from the
model, lineage, and the performance work that waited on the scheduler. 1.4.0 added deferred
registration, which came from an application paying 2.3 s of import on every start for two
operations most sessions never used.

What each release changed is in [`CHANGELOG.md`](../CHANGELOG.md). What will not change is in
[`COMPATIBILITY.md`](COMPATIBILITY.md). This page is what is *not* decided.

## Open

Nothing here is scheduled. Each says what would have to be true before it could sensibly start.

| Item | Would need |
| --- | --- |
| **Incremental recomputation** — run only the steps whose inputs changed | Identity for mutable objects. `revision` and `fingerprint()` answer "did this change"; what is missing is deciding which of them a scheduler should trust, and what a cache keyed on one is allowed to keep |
| **A faster validation path** | A real workload to measure against. Building an entity is 8.4 µs against 0.4 µs for a plain object with the same fields; a Rust-backed validator would be roughly an order of magnitude better than what is left, and would end the promise of no dependencies |
| **Distribution** — a command line, a server | Nothing technical. A plan is data and a session replays, so both are wrappers. Neither belongs in a framework with no dependencies; both belong in whatever uses it |

## Closed by decision

Recorded so each is decided once rather than argued again.

| Idea | Verdict |
| --- | --- |
| **Persistence beyond `to_dict`/`from_dict`** — a storage format, partial reads | **No.** A product of its own. `save`/`load` cover the case every application has, migrations cover a model changing shape, and anything past that is the application's choice — which is why `save` is a default that can be replaced rather than a law |
| A dependency graph over `Super` **classes** | Ordering between operations is a property of a workflow, not of a class. Attaching it to the class freezes one scenario. The real graph is over steps, which is what a pipeline has |
| A metrics backend, a rate limiter, an authorisation model | Policies. MSB supplies the interceptor and no dependencies |
| Object pooling | Entity construction cost was introspection, not allocation, and the introspection is now done once per class |
| Parallel serialization, asynchronous invalidation | Measured slower than doing the work: 1.69x sequential with `asyncio.gather`, 1.11x with threads |
| A cache size limit | Bounded by the object graph, not by traffic. Reported by `cache_statistics()` instead |
| Health checks | A property of a service, not of a library |

## How anything new gets in

| Situation | What happens |
| --- | --- |
| A new idea arrives | It goes in the table above and waits for a reason to start |
| A bug is found | Fixed if it breaks a documented promise; otherwise it queues |
| An item turns out bigger than its row | Cut it down or move it out |
| An item could be "improved further" | It is done when its exit criterion is met. Nothing is done twice |

## Things worth remembering

Not achievements — the places where the obvious answer was wrong, kept because they will be
proposed again.

- **A machine's noise can be larger than the change being measured.** A counter looked like a
  7.8% cost; three runs of the *same* code then gave 5.6, 4.1 and 3.4 µs. Sampling both sides in
  one pass said 114 ns. Measure both sides in one process and take the median.
- **Profile before optimising, even when the plan already says what to do.** Entity construction
  cost was 42 `isinstance` calls re-deriving the same answer about the same annotation — not
  allocation, which is what pooling would have addressed. Later the same mistake in reverse: the
  catalogue was assumed cheap and was 112 ms.
- **An asynchronous entry point over a synchronous handler does nothing.** The loop ran zero
  times during a 0.5-second operation, and nineteen once the work moved onto an executor.
- **An example that runs can still lie.** A documentation block printed `result: 8` and produced
  an error response. Claims are `assert`s now, and the suite runs every page.
- **Putting a field in everybody's data for a feature most never use breaks people.**
  `schema_version` was written unconditionally and broke every hand-written `from_dict` override
  downstream. It is now written only by a class that has versioned itself.
- **A fast path that answers yes or no cannot also explain a no.** Compiled validators lost the
  message naming which element failed; the compiled form is now the yes, and a no goes the long
  way.
- **Two implementations of one rule diverge.** Where speed required a second version — the
  compiled checks — a test holds it against the first over a matrix of values.
- **A cache is where the next bug lives.** Every cache added for speed was probed afterwards:
  inheritance, two containers of different types, threads building one at once, a class whose
  fields change after first use.
