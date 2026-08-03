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
| R23 | Tests import `msb_arch`; CI builds the wheel, installs it and runs the suite against it | no |
| R13 | `Serializable` becomes the shared base; `BaseEntity` and `BaseContainer` are siblings | **yes** - `isinstance` against `BaseEntity` no longer matches a container |
| R27 | The class registry holds classes weakly, so dynamically built classes are released | no |
| R28 | Cache invalidation reaches every owner, not only the one that adopted last | no |
| R29 | `Super`'s extension points are documented; its last two unused helpers removed | only the removals |
| R19 | Shared state is guarded; the container-class and handler-cache races are fixed and covered by tests that fail without the guards | no |
| R5 | Named logger with a NullHandler, no configuration on import, all 107 log calls lazy | **yes** - the application configures logging |
| R9 | `_operation` defaults from `OPERATION`; dispatch restricted to `_<operation>*` handlers | **yes** - a request can no longer name any other method |
| R10 | An operation name that is not an identifier, or that shadows a Manipulator attribute, is rejected | only already-broken registrations |
| R12 | `__hash__` on `BaseEntity` and `BaseContainer`, keyed by class and name | no |
| R15 | `Project.from_dict` is concrete; `create_item` stays abstract | no |
| R16 | `remove()` raises `KeyError` naming the container instead of warning and failing bare | no |
| R17 | `add()` keeps copying by default; the cost and the identity change are documented | no |
| R18b | The leftover cache now remembers handler resolution, so `cache_size` and `clear_cache()` mean something | no |

## Level 3 - API design

| # | Item | Where | Cost | Breaking |
| --- | --- | --- | --- | --- |
| R30 | The Super and Mega layers are the reason to choose MSB and the least examined part of it: dispatch is driven by strings, facades are installed with `setattr` and are invisible to a type checker, and coverage sits at 82% and 80% against 88% for the base layer | `super.py`, `manipulator.py` | L | depends |

## Working order

Ordered by cost and regression risk rather than strictly by criticality.

- [x] **Wave 1** - cheap, critical, leaves the API alone: R4, R3, R2, R8, R14, R18, plus R20, R21, R22, R24, R25
- [x] **Wave 2** - critical, moderate cost, needs new tests: R1, R7, R6, R11. R1 and R7 both touch `_resolve_type`, so they belong together
- [x] **Wave 3** - contract changes, each needs a decision before code: R5, R9, R10, R12, R15, R16, R17, R18b
- [x] **Wave 4** - R13 shipped in 0.3.0, together with R27 to R29 found while re-assessing it
- [ ] **Wave 5** - the operation layer: R30. R19 shipped in 0.3.2

## Release notes

Waves 1 to 3 and R23 shipped as **0.2.0** on 2026-08-03; see [`CHANGELOG.md`](../CHANGELOG.md)
for the breaking changes and the upgrade table. pAstroCORE was verified against the release
beforehand: 840 entities and 11729 fields re-validated with no violations, and its code paths
behaved identically to 0.1.3.

R13 shipped in **0.3.0** on 2026-08-03. Measuring it first was worth doing: the roadmap had
it as "breaks widely", but the framework held only seven `isinstance` checks against
`BaseEntity` and pAstroCORE none at all, so the split cost far less than the estimate.

What remains is the operation layer. The base layer is now the best covered and best
understood part of the framework, while `Super` and `Mega` -- the part that has no
equivalent in pydantic or attrs, and therefore the actual reason to choose MSB -- have had
only point fixes.
