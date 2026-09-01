# Roadmap

**The queue is empty, and the API is closed.** Everything planned after 1.0 shipped. What each
release changed is in [`CHANGELOG.md`](../CHANGELOG.md); what will not break is in
[`COMPATIBILITY.md`](COMPATIBILITY.md).

From here MSB takes bug fixes and performance work. New surface needs a reason no existing part
of the framework can serve, and the table below is where that argument starts.

## Decided against

Each was considered and closed. Recorded so it is decided once rather than argued again.

| Idea | Verdict |
| --- | --- |
| **`pickle` of a model** | `save`/`load` already put a model on disk, and do it better: the data survives a change of class (migrations), reads in anything, and executes no code on load. The other use, moving a model between processes, does not arise — the executor is threads on purpose, since numerical libraries release the GIL |
| **An `inplace=False` mode** — operations that return a copy | Doubles the meaning of every operation, and every handler would have to implement both or the mode works by accident. Identity is load-bearing here: the ownership graph, cache invalidation, `address`/`locate` and replay all address the object in the model, and a returned copy is in no model. `clone()` plus a write on the copy is the same thing in two lines |
| **Incremental recomputation** — run only the steps whose inputs changed | The parts are already exposed: `fingerprint()` answers "did this change", and a `PipelineRun` holds each step's result. What is left is policy — what counts as a step's input, how long a cached answer is trusted — and that belongs to the calculation, not to the scheduler |
| **A faster validation path** | A Rust-backed validator would be about an order of magnitude better and would end the promise of no dependencies. Building an entity is 5 µs; a 10 000-object model is 0.3 s |
| **Distribution** — a command line, a server | A request is data, a plan is data, a session replays. Both are wrappers, and both belong in whatever uses MSB |
| **Persistence beyond `to_dict`/`from_dict`** — a storage format, partial reads | A product of its own. `save`/`load` cover the case every application has and can be replaced, since they are defaults rather than laws |
| A dependency graph over `Super` **classes** | Ordering between operations is a property of a workflow, not of a class. The real graph is over steps, which is what a pipeline has |
| A metrics backend, a rate limiter, an authorisation model | Policies. MSB supplies the interceptor and no dependencies |
| Splitting `Manipulator` into namespaces | It is the single entry point on purpose. A flat surface is what makes a request reach everything the same way |
| Object pooling | Entity construction cost was introspection, not allocation, and the introspection is now done once per class |
| Parallel serialization, asynchronous invalidation | Measured slower than doing the work: 1.69x with `asyncio.gather`, 1.11x with threads |
| A cache size limit | Bounded by the object graph, not by traffic. Reported by `cache_statistics()` |
| Health checks | A property of a service, not of a library |

## How anything new gets in

| Situation | What happens |
| --- | --- |
| A new idea arrives | It goes in the table above with a verdict, or waits there for a reason to start |
| A bug is found | Fixed if it breaks a documented promise; otherwise it queues |
| An item could be "improved further" | It is done when its exit criterion is met. Nothing is done twice |

## Lessons kept

The places where the obvious answer was wrong. Kept because each will be proposed again.

| Where it went wrong | The rule that came out of it |
| --- | --- |
| A counter "cost 7.8%"; the same code then measured 5.6, 4.1 and 3.4 µs | Measure both sides in one process, take the median, and alternate the order — a difference that flips sign when you swap the order is the machine, not the code |
| Entity construction was 42 `isinstance` calls, not allocation; the catalogue was assumed cheap and was 112 ms | Profile before optimising, even when the plan already says what to do |
| An `async` entry point over a synchronous handler let the loop run zero times in 0.5 s | Awaiting is not concurrency. The work has to leave the loop |
| A documentation block printed `result: 8` and produced an error response | Claims are `assert`s, and the suite runs every page |
| `schema_version` written unconditionally broke every hand-written `from_dict` downstream | A field for a feature most never use does not go in everybody's data |
| Compiled validators lost the message naming which element failed | A fast path answers yes or no; a no goes the long way for its message |
| A name resolved a replayed step onto `store/left/bolt` instead of `store/right/bolt` | Whatever refers to an object across a file, a process or a wire has to say *where* |
| "Treat the cached mapping as read only" was true, correct, and useless | A documented rake is still a rake |
| The base module promised every hint round-trips; `Type[X]` and `Callable` did not | A promise in the documentation is a claim about the code |
| Containers had a base-class fallback for handlers and entities did not | An asymmetry is a bug waiting to be reported |
| `clear()` nulled attributes, removed items, and dropped references | One name for three jobs reads as consistency and is not |
| Every cache added for speed was probed afterwards — inheritance, mixed types, threads, classes whose fields change | A cache is where the next bug lives |
