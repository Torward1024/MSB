# Compatibility

What 1.0.0 promises, what it does not, and how anything here is allowed to change.

The short form: **anything documented as public will not break outside a major version.** The
rest of this page says exactly what that covers, because a promise nobody can check is not one.

## Versioning

[Semantic versioning](https://semver.org/spec/v2.0.0.html). Given `MAJOR.MINOR.PATCH`:

| Change | Version |
| --- | --- |
| A break in anything on the public surface below | MAJOR |
| Something new, that nothing existing has to notice | MINOR |
| A fix that changes no documented behaviour | PATCH |

A bug fix that changes documented behaviour is a MAJOR change, not a fix. If the documentation
was wrong, the documentation is corrected in a PATCH and the behaviour stays.

## The public surface

Everything importable from `msb_arch` itself. That is the whole list, and it is deliberately
short:

| | |
| --- | --- |
| **Data** | `Serializable`, `BaseEntity`, `BaseContainer`, `Project` |
| **Operations** | `Super`, `Inspector`, `Configurator`, `MethodResults` |
| **Entry point** | `Manipulator` |
| **Protocols** | `MethodProvider`, `Interceptor` |
| **Interceptors** | `RequestMetrics`, `RequestJournal` |
| **Constraints** | `Constraint`, `Positive`, `NonNegative`, `NonZero`, `NonEmpty`, `Range`, `Predicate` |
| **Exceptions** | `MSBError` and everything beneath it |
| **Utilities** | `logger`, `setup_logging`, `cache_statistics` |

Their public methods, the request and response protocol, and the meaning of an annotation are
all covered.

## Protected, and also promised

A single underscore in Python means *protected*, and MSB uses it in that sense rather than as a
synonym for private. These are called by the handlers you write, never by the framework, and
they are part of the contract:

| Member | On |
| --- | --- |
| `_apply_methods(obj, attributes, valid_methods, extra_args, strict)` | `Super` |
| `_build_response(obj, status, method, result, error)` | `Super` |
| `_get_methods(obj_type)` | `Super` |
| `_validate_and_apply_method(obj, name, args, valid_methods, extra_args)` | `Super` |
| `_do_nested(obj, attributes, key, getter, handler)` | `Super` |
| `_check_type(key, value, expected_type, subject)` | `Serializable` |
| `_resolve_type(hint, field_path)` | `Serializable` |
| `_serialize_value(value, seen)`, `_deserialize_value(value, hint, ...)` | `Serializable` |
| `_item_type_hint()` | `BaseContainer` |

Their signatures will not change outside a major version.

## Private

Everything else with a leading underscore, and every module not reachable from `msb_arch`.
Notably `_fields`, `_type_cache`, `_entity_registry`, `_parents`, `_cached_to_dict`,
`_compiled_validators`, `_operations`, `_registry`, `_interceptors`, `_chain`, `_executor`,
`_dispatch_request` and `_process_single_request`.

These are readable, and reading one in a debugger is fine. Depending on one in code is not
covered, and several have already changed shape more than once.

## Serialized data

A mapping written by 1.0 will be readable by every 1.x. Concretely:

- `type` and the field names a model declares are the contract.
- `schema_version` appears only when a class sets `SCHEMA_VERSION` to something other than 1.
  A class that has never versioned itself writes exactly what it wrote before versioning
  existed, and a mapping with no version reads as version 1.
- If MSB ever needs to change the shape it writes, it will write a version of its own and
  migrate, rather than expecting you to.

## Deprecation

Nothing on the public surface is removed without warning first.

1. **Announced** in the changelog of a MINOR release, with what replaces it and how to move.
2. **Warned** at runtime with a `DeprecationWarning` naming the replacement, from that release
   onward.
3. **Removed** in the next MAJOR release, and no earlier.

So a name deprecated in 1.4 still works in 1.9 and disappears in 2.0. A deprecated name keeps
working exactly as it did while it is deprecated; the warning is the only change.

## What is deliberately not promised

- **Thread safety of a single object.** What MSB shares between objects is guarded; one object
  is no safer than any plain Python object, and two threads writing the same entity must be
  serialized by the caller. See the base module guide.
- **Performance numbers.** Defended by benchmarks in CI so a regression fails a build, but the
  numbers themselves are not a contract.
- **Log message wording.** The logger name `msb_arch` is stable; what it says is not.
- **Exception messages.** The *types* are contractual, and are what to catch. The strings are
  written for people and are free to improve.
- **Ordering of a mapping**, except where documented: a set serializes in a stable order
  precisely because that one is promised.

## Reporting a break

If something covered here breaks, that is a bug and not a matter of opinion. Open an issue with
the version you moved from and to, and the smallest thing that shows it.
