# MSB Fix Roadmap

Findings from the 0.1.3 MVP review, ordered by descending criticality. Cost is a rough
estimate of effort plus regression risk: **S** is a contained change, **M** needs new tests,
**L** reworks the public API. "Breaking" means downstream consumers have to adapt.

Status: `[x]` merged into main, `[ ]` open.

## Done

| # | Item | Breaking |
| --- | --- | --- |
| F1 | `_validate_type` rewritten for parameterized type hints, nested to any depth | yes - `List[int]` no longer silently accepts foreign elements |
| F2 | Removed the hardcoded `value` attribute guard | no - a loosening only |

## Level 1 - data loss, leaks, wrong results

| # | Item | Where | Cost | Breaking |
| --- | --- | --- | --- | --- |
| R1 | `_type_cache` is shared across the hierarchy and keyed by type *name*. Two modules defining a class with the same name collide; the loser gets a `TypeError` on its own objects | `baseentity.py`, `basecontainer.py`, `_resolve_type` in both | M | no |
| R2 | `__del__` calls `clear()`. A container keeps the caller's `items` dict **by reference** and empties it on garbage collection | five `__del__` methods across the package | S | no |
| R3 | `_invalidate_cache` walks every item, making `add` quadratic: 4000 items take 1.4 s and 2000 inserts issue 2M `hasattr` calls. Runs even when `_use_cache` is False | `basecontainer.py` | S-M | no |
| R4 | `@lru_cache` on an instance method puts `self` in the key, so no `Manipulator` is ever collected; the cache is shared class-wide and `clear_cache()` clears it for every instance | `manipulator.py` | S | no |
| R5 | Importing the package seizes the **root logger**, creates `output.log` in the working directory and reroutes the host application's logging. Every `logger.debug(f"...")` formats its f-string unconditionally | `logging_setup.py` plus ~100 call sites | M | **yes** |

## Level 2 - documented behaviour that does not hold

| # | Item | Where | Cost | Breaking |
| --- | --- | --- | --- | --- |
| R6 | Cyclic references raise `RecursionError`. `seen` is local to a single call, so a nested `to_dict` starts over. The README advertises support | `baseentity.py`, `basecontainer.py` | M | no |
| R7 | `from_dict` looks types up in the **framework module's** `globals()`, so user types are never found and polymorphic deserialization does not work | `baseentity.py`, `basecontainer.py` | M | no |
| R8 | Internal fields (`_type_cache` and friends) leak into `__eq__`, `__repr__` and `clear()`. Identical entities compare unequal and `repr` dumps internals. One root cause: `_fields` is not filtered | `baseentity.py` | S | `repr` output only |
| R9 | `Super.execute` resolves `getattr(self, method)` from a request string with no allowlist. `_operation` is never initialized from `OPERATION`, so an unregistered `Super` raises `AttributeError` before the `try` block | `super.py` | M | **yes** |
| R10 | Facades are installed with `setattr(self, operation, ...)` without checking the name, so an operation called `process_request` shadows the method and recurses | `manipulator.py` | S | **yes** |
| R11 | The `to_dict` cache hands out the **live** dict, so a caller can corrupt it, and validating the cache serializes nested entities anyway - exactly the work the cache should save | `baseentity.py` | M | no |
| R12 | `__eq__` without `__hash__` makes entities unhashable, so they cannot go into a set or be used as dict keys | `baseentity.py` | S | no |

## Level 3 - API design

| # | Item | Where | Cost | Breaking |
| --- | --- | --- | --- | --- |
| R13 | `BaseContainer(BaseEntity)` violates LSP: `get`, `clear` and `set` carry incompatible semantics. This is the root cause behind R2, and composition would fix it | `basecontainer.py` | **L** | **yes, widely** |
| R14 | `_create_container` builds a new class on every call, so two projects hold containers of different classes, `__eq__` breaks and classes leak | `project.py` | S | no |
| R15 | `Project.from_dict` is `@classmethod @abstractmethod` **with a body**, forcing subclasses to write a stub - the README's has a broken signature | `project.py` | S | no |
| R16 | `remove()` logs a warning for a missing key and then raises `KeyError` anyway | `basecontainer.py` | S | **yes** |
| R17 | `add(copy_items=True)` deep-copies by default, so `container.get(x) is item` is False | `basecontainer.py` | S | **yes** |
| R18 | Dead code: `_method_cache`, `_make_hashable` and `_update_cache` are never reached from `execute`; `__getattribute__` is an identity wrapper | `super.py`, `basecontainer.py` | S | no |
| R18b | Leftover from R18: `Super` still carries `_method_cache`, `_cache_size`, the `cache_size` constructor argument and `clear_cache()`, none of which cache anything now that the only writer is gone. Removing them changes the public signature, so it needs a decision | `super.py` | S | **yes** |
| R19 | No thread safety, with mutable state held at class level | package-wide | L | no |

## Level 4 - hygiene and packaging

| # | Item | Cost |
| --- | --- | --- |
| R20 | No `py.typed` marker, so a package built around typing ships none to its consumers | S |
| R21 | `MANIFEST.in` includes `msb`; the package is `msb_arch` | S |
| R22 | The README version badge says 0.1.0 while pyproject says 0.1.3 | S |
| R23 | Tests import `from src.msb_arch` and CI never installs the package, so the **installed** distribution is never exercised | S-M |
| R24 | Copy-paste artefacts from pAstroCORE: `"ScheduleManipulator"`, `"ScheduleProject"` | S |
| R25 | Flaky performance assertions of the form `assert time_with_cache < time_no_cache` | S |
| R26 | Documentation promises cyclic reference support; retract it or close it together with R6 | S |

## Working order

Ordered by cost and regression risk rather than strictly by criticality.

- [ ] **Wave 1** - cheap, critical, leaves the API alone: R4, R3, R2, R8, R14, R18, plus R20, R21, R22, R24, R25
- [ ] **Wave 2** - critical, moderate cost, needs new tests: R1, R7, R6, R11. R1 and R7 both touch `_resolve_type`, so they belong together
- [ ] **Wave 3** - contract changes, each needs a decision before code: R5, R9, R10, R12, R15, R16, R17
- [ ] **Wave 4** - separate minor release: R13, R19, R23

## Release notes

The validation contract changes in F1, and most of wave 3 changes it further, so the next
release is **0.2.0** rather than 0.1.4. A `CHANGELOG.md` with an explicit breaking-changes
section is worth adding: two downstream projects upgrade against it.

R13 is the only **L** item that reshapes the base hierarchy, and it drags R2, R16 and R17
along with it. Recommendation: keep it out of 0.2.0 and do it deliberately on a stable base.
