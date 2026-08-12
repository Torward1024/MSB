# catalogue.py
"""Derive what a `Manipulator` offers, from what was registered with it.

An application otherwise states what it can do twice: in the handlers, and again in the menu or
table that offers them. The second copy goes stale. It does not need writing: operations are
registered, handlers name themselves after the operation they serve, and handlers call each other
by name, so the registry, the labels and the edges are already in the code.

Reached through `manipulator.describe_operations()`.

Limits:

- Nothing here knows what an application is about. `calls` reports the names as written; the
  `interpret` callback is where a caller says what they mean.
- Edges between handlers are exact. What a handler touches outside the operation is an upper
  bound, because a shared helper is followed for every handler that calls it. Measured on a
  fourteen-handler application: every handler-to-handler edge correct, six of the fourteen
  reporting more outside calls than they depend on. Use it to check a declaration, not as one.
- The derivation reads source, so a handler attached to a class after import is invisible.
"""
import ast
import inspect
import re
import textwrap
import weakref
from typing import Any, Callable, Dict, List, Optional, Set

from .utils.logging_setup import logger

#: The derivation only. Callers go through `manipulator.describe_operations()`.
__all__ = ["derive", "label_for", "order", "requirements_of"]


def label_for(name: str, acronyms: Optional[Dict[str, str]] = None) -> str:
    """Turn a handler's name into something a person can be shown.

    Args:
        name (str): A handler's name without its operation prefix, such as `unit_price`.
        acronyms (Optional[Dict[str, str]]): Words that keep their own capitals, lower-cased
            keys to the spelling wanted -- `{"id": "ID"}`. An application's vocabulary cannot be
            derived, so it is passed in.

    Returns:
        str: `Unit Price`. Derived, so adding a handler does not mean naming it elsewhere.
    """
    known = acronyms or {}
    return " ".join(known.get(word, word.capitalize()) for word in name.split("_"))


def _source_of(target: Any) -> Optional[str]:
    """Return the source of one class, dedented, or None if it cannot be read."""
    try:
        return textwrap.dedent(inspect.getsource(target))
    except (OSError, TypeError) as e:
        logger.debug("Cannot read the source of %s: %s", getattr(target, "__name__", target), str(e))
        return None


#: Parsed method bodies, by class. Source does not change while a process runs, and parsing a
#: hierarchy costs milliseconds. Weakly held, so a class defined in a function is collected
#: with it.
_PARSED: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()

#: Derived handler tables, by class and operation. Same reasoning, one level up.
_DERIVED: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _methods(owner: Any) -> Dict[str, ast.FunctionDef]:
    """Return every method a class has, by name, as syntax.

    Notes:
        - Walks the inheritance chain, so a subclass reports the handlers it inherited. A method
          defined nearer wins, matching what Python calls.
        - Cached per class: reading and parsing source took 118 ms for six operations and is
          asked for whenever a menu is drawn.
    """
    target = owner if isinstance(owner, type) else type(owner)
    cached = _PARSED.get(target)
    if cached is not None:
        return cached

    methods: Dict[str, ast.FunctionDef] = {}

    for ancestor in reversed(target.__mro__):
        if ancestor is object:
            continue
        source = _source_of(ancestor)
        if source is None:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.debug("Cannot parse the source of %s: %s", ancestor.__name__, str(e))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                methods[node.name] = node          # nearer classes come later and win

    try:
        _PARSED[target] = methods
    except TypeError:                              # a class that cannot be weakly referenced
        pass
    return methods


def _called_names(node: ast.FunctionDef) -> List[str]:
    """Return the attribute names called inside one method, in source order."""
    return [child.func.attr for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)]


def _reached(name: str, methods: Dict[str, ast.FunctionDef], seen: Set[str]) -> Set[str]:
    """Return every name called by a method, following the methods of the same class.

    Notes:
        - Follows any method the class defines, rather than names with an agreed prefix, so it
          depends on no naming convention and misses no helper.
    """
    if name in seen or name not in methods:
        return set()
    seen.add(name)

    found: Set[str] = set()
    for called in _called_names(methods[name]):
        found.add(called)
        if called in methods:
            found |= _reached(called, methods, seen)
    return found


def derive(owner: Any, operation: Optional[str] = None,
           interpret: Optional[Callable[[str], Optional[str]]] = None) -> Dict[str, Dict[str, List[str]]]:
    """Work out what one `Super` offers and how its handlers depend on each other.

    Args:
        owner (Super): The instance to read.
        operation (Optional[str]): The operation whose handlers to look for. Taken from the
            instance when not given.
        interpret (Optional[Callable]): Given a called name, return what it means to the
            application, or None to ignore it. Without it, `touches` is empty.

    Returns:
        Dict[str, Dict[str, List[str]]]: `{name: {"requires": [...], "calls": [...],
            "touches": [...]}}`. `requires` names other handlers of the same operation; `calls`
            is every name reached; `touches` is what `interpret` made of them.

    Notes:
        - `requires` is exact and direct: the handlers this one names, not what they reach in
          turn. The closure follows from it, and the reverse does not.
        - `calls` and `touches` are an upper bound, since a shared helper is followed for every
          handler that calls it.
    """
    operation = operation or getattr(owner, "_operation", None) or getattr(owner, "OPERATION", None)
    if not operation:
        logger.debug("%s has no operation name; nothing to derive", owner)
        return {}

    derived = _edges(owner if isinstance(owner, type) else type(owner), operation)

    catalogue: Dict[str, Dict[str, List[str]]] = {}
    for handler, (requires, reached) in derived.items():
        touches = []
        if interpret is not None:
            touches = sorted({meaning for meaning in (interpret(name) for name in reached)
                              if meaning})
        catalogue[handler] = {"requires": list(requires), "calls": list(reached),
                              "touches": touches}
    return catalogue


def _edges(target: type, operation: str) -> Dict[str, tuple]:
    """Return each handler's direct prerequisites and everything it reaches, cached per class.

    Args:
        target (type): The class whose handlers to read.
        operation (str): The operation they serve.

    Returns:
        Dict[str, tuple]: `{handler: (requires, calls)}`, both sorted.

    Notes:
        - Cached: source does not change while a process runs. The interpretation of the names
          is not cached, since only the caller supplies it.
    """
    per_operation = _DERIVED.setdefault(target, {}) if _weakly(target) else {}
    if operation in per_operation:
        return per_operation[operation]

    prefix = f"_{operation}_"
    methods = _methods(target)
    edges = {}
    for handler in [name for name in methods if name.startswith(prefix)]:
        requires = sorted({name[len(prefix):] for name in _called_names(methods[handler])
                           if name.startswith(prefix) and name != handler})
        edges[handler[len(prefix):]] = (requires, sorted(_reached(handler, methods, set())))

    per_operation[operation] = edges
    return edges


def _weakly(target: type) -> bool:
    """Report whether a class can be a key in a weak mapping."""
    try:
        weakref.ref(target)
        return True
    except TypeError:
        return False


def requirements_of(catalogue: Dict[str, Dict[str, List[str]]], name: str) -> List[str]:
    """Return everything a handler needs, directly or through what it needs.

    Args:
        catalogue (Dict): What `derive` produced for one operation.
        name (str): The handler to ask about.

    Returns:
        List[str]: Sorted, and excluding the handler itself. Empty for one that needs nothing.

    Notes:
        - The stored edges are direct, so this walk is offered on demand rather than kept as a
          second table. A cycle is followed once.
    """
    found: Set[str] = set()
    pending = list(catalogue.get(name, {}).get("requires", []))
    while pending:
        need = pending.pop()
        if need in found or need == name:
            continue
        found.add(need)
        pending.extend(catalogue.get(need, {}).get("requires", []))
    return sorted(found)


def order(catalogue: Dict[str, Dict[str, List[str]]], wanted: List[str]) -> List[str]:
    """Return the wanted handlers in an order that satisfies their prerequisites.

    Args:
        catalogue (Dict): What `derive` produced for one operation.
        wanted (List[str]): The handler names asked for, in any order.

    Returns:
        List[str]: The same names, each after everything it needs that was also asked for. A
            prerequisite nobody asked for is not added.

    Notes:
        - A cycle is logged and the remainder appended in the order given, rather than raising:
          handlers that cannot be ordered can still be run.
    """
    remaining = list(dict.fromkeys(wanted))
    placed: Set[str] = set()
    result: List[str] = []

    while remaining:
        ready = [name for name in remaining
                 if all(need in placed or need not in remaining
                        for need in catalogue.get(name, {}).get("requires", []))]
        if not ready:
            logger.warning("Cannot order %s by their prerequisites; leaving them as given",
                           remaining)
            result.extend(remaining)
            break
        for name in ready:
            result.append(name)
            placed.add(name)
            remaining.remove(name)
    return result
