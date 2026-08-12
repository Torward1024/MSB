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
  an object, and `_parents` on a live one answers that.
- Types are reported by name. What they mean is the caller's business.
"""
from typing import Any, Dict, List, Optional, Set, get_args

from .utils.logging_setup import logger

#: The derivation only. Callers go through `manipulator.describe_model()`.
__all__ = ["derive_model", "dependents_of", "holdings_of", "named_type"]


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
