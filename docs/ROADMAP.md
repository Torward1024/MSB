# MSB Fix Roadmap

Findings from the 0.1.3 MVP review, ordered by descending criticality. Cost is a rough
estimate of effort plus regression risk: **S** is a contained change, **M** needs new tests,
**L** reworks the public API. "Breaking" means downstream consumers have to adapt.

Status: `[x]` merged into main, `[ ]` open. The level tables list only what is still open;
everything closed moves to the Done table.

## Done

| # | Item | Breaking |
| --- | --- | --- |
| F1 | `_validate_type` rewritten for parameterized type hints, nested to any depth | yes - `List[int]` no longer silently accepts foreign elements |
| F2 | Removed the hardcoded `value` attribute guard | no - a loosening only |
| R4 | Registry held per `Manipulator` instead of an `lru_cache` keyed on `self` | no |
| R3 | Cache invalidation no longer walks the items; `add` is flat at ~12 us | no |
| R2 | All five `__del__` methods removed; the container copies the incoming mapping | no |
| R24 | `ScheduleManipulator` / `ScheduleProject` leftovers removed with those finalizers | no |
| R8 | Underscore-prefixed fields kept out of `clear()`, `__eq__` and `__repr__` | `repr` output only |
| R25 | Caching performance tests assert cache identity instead of racing micro-timings | no |
| R14 | Generated container class cached per item type | no |
| R18 | `_make_hashable`, `_update_cache` and `BaseContainer.__getattribute__` removed | no |
| R20 | `py.typed` marker added and verified in the built wheel | no |
| R21 | `MANIFEST.in` paths corrected for the `src/msb_arch` layout | no |
| R22 | README version badge synchronised with pyproject | no |
| R1 | `_type_cache` is per class; name lookup prefers the declaring module; the duplicated `_resolve_type` in `BaseContainer` is gone | no |
| R7 | `EntityMeta` registers every class, so nested entities and container items restore as the class named in the payload | no |
| R6 | `to_dict` threads its `seen` set through the recursion, so genuine cycles terminate | no |
| R11 | Invalidation travels up a weak ownership chain; the cache-validation walk is gone | cached mapping is documented read-only |
| R26 | Cyclic reference support is now real, so the documentation claim holds | no |

## Level 1 - data loss, leaks, wrong results

| # | Item | Where | Cost | Breaking |
| --- | --- | --- | --- | --- |
| R5 | Importing the package seizes the **root logger**, creates `output.log` in the working directory and reroutes the host application's logging. Every `logger.debug(f"...")` formats its f-string unconditionally | `logging_setup.py` plus ~100 call sites | M | **yes** |

## Level 2 - documented behaviour that does not hold

| # | Item | Where | Cost | Breaking |
| --- | --- | --- | --- | --- |
| R9 | `Super.execute` resolves `getattr(self, method)` from a request string with no allowlist. `_operation` is never initialized from `OPERATION`, so an unregistered `Super` raises `AttributeError` before the `try` block | `super.py` | M | **yes** |
| R10 | Facades are installed with `setattr(self, operation, ...)` without checking the name, so an operation called `process_request` shadows the method and recurses | `manipulator.py` | S | **yes** |
| R12 | `__eq__` without `__hash__` makes entities unhashable, so they cannot go into a set or be used as dict keys | `baseentity.py` | S | no |

## Level 3 - API design

| # | Item | Where | Cost | Breaking |
| --- | --- | --- | --- | --- |
| R13 | `BaseContainer(BaseEntity)` violates LSP: `get`, `clear` and `set` carry incompatible semantics. This is the root cause behind R2, and composition would fix it | `basecontainer.py` | **L** | **yes, widely** |
| R15 | `Project.from_dict` is `@classmethod @abstractmethod` **with a body**, forcing subclasses to write a stub - the README's has a broken signature | `project.py` | S | no |
| R16 | `remove()` logs a warning for a missing key and then raises `KeyError` anyway | `basecontainer.py` | S | **yes** |
| R17 | `add(copy_items=True)` deep-copies by default, so `container.get(x) is item` is False | `basecontainer.py` | S | **yes** |
| R18b | Leftover from R18: `Super` still carries `_method_cache`, `_cache_size`, the `cache_size` constructor argument and `clear_cache()`, none of which cache anything now that the only writer is gone. Removing them changes the public signature, so it needs a decision | `super.py` | S | **yes** |
| R19 | No thread safety, with mutable state held at class level | package-wide | L | no |

## Level 4 - hygiene and packaging

| # | Item | Cost |
| --- | --- | --- |
| R23 | Tests import `from src.msb_arch` and CI never installs the package, so the **installed** distribution is never exercised | S-M |

## Working order

Ordered by cost and regression risk rather than strictly by criticality.

- [x] **Wave 1** - cheap, critical, leaves the API alone: R4, R3, R2, R8, R14, R18, plus R20, R21, R22, R24, R25
- [x] **Wave 2** - critical, moderate cost, needs new tests: R1, R7, R6, R11. R1 and R7 both touch `_resolve_type`, so they belong together
- [ ] **Wave 3** - contract changes, each needs a decision before code: R5, R9, R10, R12, R15, R16, R17, R18b
- [ ] **Wave 4** - separate minor release: R13, R19, R23

## Release notes

The validation contract changes in F1, and most of wave 3 changes it further, so the next
release is **0.2.0** rather than 0.1.4. A `CHANGELOG.md` with an explicit breaking-changes
section is worth adding: two downstream projects upgrade against it.

R13 is the only **L** item that reshapes the base hierarchy, and it drags R2, R16 and R17
along with it. Recommendation: keep it out of 0.2.0 and do it deliberately on a stable base.
