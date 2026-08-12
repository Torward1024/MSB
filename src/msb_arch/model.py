# model.py
"""What holds what, read back from the annotations that already say so.

A model is a graph whether anybody drew it or not: a container declares what it holds, an entity
declares the types of its fields, and between them those two statements are the whole edge set.
The question people actually ask of it is the reverse one -- *what depends on this type* -- and
that is the one nothing in the code answers, because every declaration points the other way.

This walks the declarations and turns them round. Nothing is written down twice: a field added to
a class changes the graph, and a diagram derived from this cannot go stale the way a drawn one
does.

**Nothing here knows what an application is about.** Types are reported by name, in the shape the
code declares them, and what any of them mean is the caller's business.

The one limit worth stating up front: this is a graph over **types**, not over objects. It says
that changing `Wheel` may affect a `Car`, because a `Car` has wheels. It cannot say *which* car,
because that is a fact about a particular object rather than about the class -- `_parents` on a
live object answers that, and answers it exactly.
"""
from typing import Any, Dict, List, Optional, Set, get_args

from .utils.logging_setup import logger

#: The derivation only. Callers ask the manipulator -- `manipulator.describe_model()` --
#: rather than running these over one from outside.
__all__ = ["derive_model", "dependents_of", "holdings_of"]


def _serializable_types(hint: Any, owner: Optional[type] = None) -> List[type]:
    """Return every modelled type mentioned by one annotation.

    Args:
        hint (Any): An annotation, as simple as `Wheel` or as involved as
            `Optional[Dict[str, List[Wheel]]]`.
        owner (Optional[type]): The class the annotation was written on, used to make sense of
            a name that referred forward to a class that did not exist yet.

    Returns:
        List[type]: The `Serializable` subclasses inside it, in the order they appear. Plain
            types are not modelled types and are left out: a graph of everything that mentions
            `str` is a graph of everything.

    Notes:
        - Recursive over the type arguments rather than matching particular containers, so a
          shape nobody anticipated still gives up what it holds.
        - A forward reference is looked up where it was written. A type that holds its own kind
          -- a tree, a chain, anything recursive -- can only be annotated by name, so a graph
          that gave up at a name would miss exactly the models whose shape is worth asking
          about. One that names a class defined somewhere unreachable is skipped rather than
          guessed at.
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
        Dict[str, List[type]]: Field name mapped to the modelled types that field can hold. A
            container's items appear under `items`, since that is what the annotation is called
            everywhere it is serialised.
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
            declares; `held_by` is the same edges reversed, which is the direction nothing in
            the code answers and every caller asks in.

    Notes:
        - A type is reached through any annotation, however deeply nested, so a model does not
          have to be a tree and a cycle -- a type that can hold its own kind -- is fine.
        - Unmodelled types are left out. A class that has a `str` and an `int` and holds nothing
          appears with empty edges rather than not at all, because "this depends on nothing" is
          an answer.
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
        List[str]: Sorted, transitive, and excluding the type itself. Empty for a type nothing
            holds.

    Notes:
        - Transitive, unlike the edges themselves, because the question is "what breaks" and a
          change reaches as far as the holding does. A cycle is followed once and left.
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
        List[str]: Sorted, transitive, and excluding the type itself.

    Notes:
        - The other direction of the same walk. What a type reaches is what serialising it will
          touch, which is the question asked when a model is written, sent or copied.
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
