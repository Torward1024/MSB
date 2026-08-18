# model.py
"""Derive which type holds which, from the annotations.

A container declares what it holds and an entity declares the types of its fields. Those two
statements are the whole edge set of the model, so the graph needs no separate description and
cannot go stale: adding a field changes the answer.

The useful direction is the reverse one, `held_by` -- what depends on this type -- because every
declaration points the other way and nothing in the code answers it.

Reached through `manipulator.describe_model()`.

Limits:

- A graph over types, not objects. Changing `Wheel` may affect a `Car`; which car is a fact about
  an object, which is what `path_of` reads out of `_parents` on a live one.
- Types are reported by name. What they mean is the caller's business.
"""
import logging
from typing import Any, Dict, List, Optional, Set, get_args

from .base.serializable import Serializable
from .utils.logging_setup import logger

#: The derivation only. Callers go through `manipulator.describe_model()`.
__all__ = ["derive_model", "dependents_of", "holdings_of", "named_type", "path_of"]

#: Stands in for the `__dict__` of something that has none, so the walk in
#: `path_of` needs no branch for it.
_NOTHING: Dict[str, Any] = {}


def _serializable_types(hint: Any, owner: Optional[type] = None) -> List[type]:
    """Return every modelled type mentioned by one annotation.

    Args:
        hint (Any): An annotation, from `Wheel` to `Optional[Dict[str, List[Wheel]]]`.
        owner (Optional[type]): The class the annotation was written on, used to resolve a
            forward reference.

    Returns:
        List[type]: The `Serializable` subclasses inside it, in the order they appear. Plain
            types are left out, since a graph of everything mentioning `str` is a graph of
            everything.

    Notes:
        - Recursive over type arguments rather than matching particular containers, so an
          unanticipated shape still gives up what it holds.
        - A forward reference is looked up in the module the annotation was written in, since a
          recursive type can only be annotated by name. One that names an unreachable class is
          skipped.
    """
    import sys
    import typing

    from .base.serializable import Serializable

    if isinstance(hint, type):
        return [hint] if issubclass(hint, Serializable) else []

    if isinstance(hint, (str, typing.ForwardRef)):
        name = hint if isinstance(hint, str) else hint.__forward_arg__
        where = getattr(sys.modules.get(getattr(owner, "__module__", ""), None), "__dict__", {})
        referent = where.get(name)
        if isinstance(referent, type) and issubclass(referent, Serializable):
            return [referent]
        logger.debug("Cannot make sense of the reference to '%s' on %s", name,
                     getattr(owner, "__name__", owner))
        return []

    found: List[type] = []
    for argument in get_args(hint):
        found.extend(_serializable_types(argument, owner))
    return found


def _held_by(owner: type) -> Dict[str, List[type]]:
    """Return what one class holds, by the two ways a class can say it.

    Args:
        owner (type): A `Serializable` subclass.

    Returns:
        Dict[str, List[type]]: Field name mapped to the modelled types it can hold. A
            container's items appear under `items`, matching what serialisation calls them.
    """
    from .base.basecontainer import BaseContainer

    holdings: Dict[str, List[type]] = {}
    for field, hint in getattr(owner, "_fields", {}).items():
        if field == "_items":
            continue                                    # reported below, under its public name
        try:
            resolved = owner._resolve_type(hint, field)
        except Exception as e:                          # an annotation nothing can reduce
            logger.debug("Cannot resolve '%s.%s': %s", owner.__name__, field, str(e))
            continue
        held = _serializable_types(resolved, owner)
        if held:
            holdings[field.lstrip("_")] = held

    if issubclass(owner, BaseContainer):
        try:
            item_type = owner._resolve_type(owner._item_type_hint())
        except Exception as e:
            logger.debug("Cannot resolve what %s holds: %s", owner.__name__, str(e))
        else:
            held = _serializable_types(item_type, owner)
            if held:
                holdings["items"] = held
    return holdings


def derive_model(roots: List[type]) -> Dict[str, Dict[str, Any]]:
    """Work out the graph of a model from the types it is built of.

    Args:
        roots (List[type]): Where to start. Types reached from these are included whether they
            were named or not, so passing the top of a model is enough.

    Returns:
        Dict[str, Dict[str, Any]]: `{type name: {"holds": {field: [type name]},
            "held_by": {type name: [field]}, "container": bool}}`. `holds` is what the class
            declares; `held_by` is those edges reversed.

    Notes:
        - A type is reached through any annotation, however deeply nested, so the model need not
          be a tree and a type may hold its own kind.
        - A type that holds nothing appears with empty edges rather than being left out.
    """
    from .base.basecontainer import BaseContainer
    from .base.serializable import Serializable

    graph: Dict[str, Dict[str, Any]] = {}
    pending = [root for root in roots
               if isinstance(root, type) and issubclass(root, Serializable)]
    seen: Set[type] = set()

    while pending:
        owner = pending.pop()
        if owner in seen:
            continue
        seen.add(owner)

        holds = _held_by(owner)
        graph[owner.__name__] = {
            "holds": {field: sorted(held.__name__ for held in types)
                      for field, types in holds.items()},
            "held_by": {},
            "container": issubclass(owner, BaseContainer),
        }
        pending.extend(held for types in holds.values() for held in types)

    for name, entry in graph.items():
        for field, held in entry["holds"].items():
            for target in held:
                if target in graph:
                    graph[target]["held_by"].setdefault(name, []).append(field)
    return graph


def dependents_of(graph: Dict[str, Dict[str, Any]], name: str) -> List[str]:
    """Return every type that would feel a change to this one.

    Args:
        graph (Dict): What `derive_model` produced.
        name (str): The type to ask about.

    Returns:
        List[str]: Sorted, transitive, excluding the type itself. Empty for a type nothing holds.

    Notes:
        - Transitive, unlike the stored edges: a change reaches as far as the holding does. A
          cycle is followed once.
    """
    found: Set[str] = set()
    pending = list(graph.get(name, {}).get("held_by", {}))
    while pending:
        holder = pending.pop()
        if holder in found or holder == name:
            continue
        found.add(holder)
        pending.extend(graph.get(holder, {}).get("held_by", {}))
    return sorted(found)


def holdings_of(graph: Dict[str, Dict[str, Any]], name: str) -> List[str]:
    """Return every type this one reaches, directly or through what it holds.

    Args:
        graph (Dict): What `derive_model` produced.
        name (str): The type to ask about.

    Returns:
        List[str]: Sorted, transitive, excluding the type itself.

    Notes:
        - The same walk in the other direction: what a type reaches is what serialising it
          touches.
    """
    found: Set[str] = set()
    pending = [held for names in graph.get(name, {}).get("holds", {}).values()
               for held in names]
    while pending:
        target = pending.pop()
        if target in found or target == name:
            continue
        found.add(target)
        pending.extend(held for names in graph.get(target, {}).get("holds", {}).values()
                       for held in names)
    return sorted(found)


def named_type(name: str) -> type:
    """Return the modelled type of that name, refusing to guess between two.

    Args:
        name (str): A class name, as it arrives in a plan, a request or a file.

    Returns:
        type: The `Serializable` subclass called that.

    Raises:
        RequestError: If nothing of that name has been imported, or more than one thing has.

    Notes:
        - Only `Serializable` subclasses are searched, so a name that crossed a boundary can
          only select among the model's own types.
    """
    from .base.serializable import Serializable
    from .errors import RequestError

    found, pending = [], [Serializable]
    while pending:
        candidate = pending.pop()
        if candidate.__name__ == name and candidate not in found:
            found.append(candidate)
        pending.extend(candidate.__subclasses__())

    if not found:
        raise RequestError(f"No imported type is called '{name}'")
    if len(found) > 1:
        raise RequestError(
            f"{len(found)} imported types are called '{name}': "
            f"{', '.join(sorted(one.__module__ for one in found))}")
    return found[0]



def member_called(name: str, owner: Any) -> Optional[Any]:
    """Return the model object called `name` that `owner` holds, or None.

    Args:
        name (str): One segment of a path -- the *name* of the object being looked for.
        owner (Serializable): The object to look inside.

    Returns:
        Optional[Any]: What it holds under that name.

    Notes:
        - Three ways, because a model holds its parts in three shapes and a path is built from
          names rather than from how they are held:

          | Shape | Reached by |
          | --- | --- |
          | An item of a container | `get(name)` |
          | An item of a project | `get_item(name)`, which is what a `Project` calls it |
          | A container in a field of an entity | the field whose value is named `name` |

        - The third is why `address` and `locate` were not inverses. An entity naming its parts
          -- `bolts: Bolts` -- holds a container whose own name is `bolts_of_press`, and a path
          carries the name while the field is called something else. Matching on the *value's*
          name is what closes that, and it is the shape every application has.
        - A field is only followed when it holds a model object, so a path still addresses the
          model rather than reading an attribute off it.
    """
    # Asked before taken, so a miss costs nothing and says nothing. Calling the accessors blind
    # and catching what came back logged a complaint per miss -- and three ways are tried, so an
    # ordinary lookup complained twice on its way to succeeding.
    found = None
    if getattr(owner, "has_item", None) is not None:            # a container
        if owner.has_item(name):
            found = owner.get(name)
    elif getattr(owner, "get_items", None) is not None:         # a project
        try:
            items = owner.get_items()
        except Exception:                                       # noqa: BLE001 - not a mapping
            items = None
        if isinstance(items, dict) and name in items:
            found = items[name]
    if isinstance(found, Serializable):
        return found

    held = getattr(owner, name, None)
    if isinstance(held, Serializable):
        return held

    # A container held in a field carries its own name, which is the one a path records.
    for field in getattr(type(owner), "__annotations__", {}):
        value = getattr(owner, field, None)
        if isinstance(value, Serializable) and getattr(value, "name", None) == name:
            return value
    return None


def path_of(obj: Any) -> List[str]:
    """Return where an object sits in the model, as names from the top down.

    Args:
        obj (Serializable): The object to locate.

    Returns:
        List[str]: `["store", "right", "bolt"]` -- every owner's name, ending with this
            object's own. A single name for something nothing owns. Empty for anything with no
            name at all.

    Notes:
        - Read from `_parents`, the ownership graph invalidation already walks, so nothing has
          to be recorded for this to work.
        - **A name is not unique; a path is what makes it addressable.** Two containers may
          each hold a `bolt`, and a session that recorded only the name cannot say which one it
          meant.
        - An object with several owners -- one added to two containers with `copy_items=False`
          -- has several paths. The first owner found is used and the rest are logged, since a
          caller wanting a particular one can address it directly.
        - A cycle in ownership stops the walk rather than looping.
    """
    name = getattr(obj, "name", None)
    if not name:
        return []

    # Built bottom-up and reversed once: a path is a handful of segments, and every request a
    # journal records pays for this walk.
    upwards = [name]
    seen = {id(obj)}
    current = obj
    while True:
        owners = getattr(current, "__dict__", _NOTHING).get("_parents")
        if not owners:
            break
        owner = None
        for reference in owners.values():
            candidate = reference()
            if candidate is not None and id(candidate) not in seen:
                if owner is None:
                    owner = candidate
                elif logger.isEnabledFor(logging.DEBUG):
                    logger.debug("%s has another owner, '%s'; addressing it through '%s'",
                                 name, getattr(candidate, "name", "?"),
                                 getattr(owner, "name", "?"))
                else:
                    break
        if owner is None:
            break
        owner_name = getattr(owner, "name", None)
        if not owner_name:
            break
        seen.add(id(owner))
        upwards.append(owner_name)
        current = owner
    upwards.reverse()
    return upwards
