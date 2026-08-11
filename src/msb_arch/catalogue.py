# catalogue.py
"""What a `Manipulator` offers, assembled from what was registered with it.

An application built on MSB knows what it can do twice: once in the handlers that do the work,
and again in whatever menu, list or table offers them. The second copy is written by hand, goes
out of date, and makes adding a feature cost edits in places with no business knowing about it.

Almost none of it needs writing down. Operations are registered, handlers name themselves
against the operation they serve, and handlers call each other by name -- so the registry, the
labels and the edges between handlers are all statements the code already makes. This reads
them back.

**Nothing here knows what an application is about.** A handler's calls are reported as the names
in the code, not as concepts: `calls` says `get_widgets` because that is what is written, and
only the application knows what a widget is to it. Interpreting them is the caller's job, and
`interpret` is where a caller says how.

One limit, stated here rather than discovered later. Edges **between handlers** are exact: a
call is a call. What a handler touches *outside* the operation is an **upper bound**, because a
helper shared by several handlers is followed for all of them whether each uses what it fetches
or not. Measured downstream: fourteen handlers, every handler-to-handler edge correct, and six
of the fourteen reporting more outside calls than the handler actually depends on. Use it to
**check a declaration**, not to replace one -- an over-wide answer used as truth restores
exactly the coarseness that declaring a dependency exists to remove.
"""
import ast
import inspect
import re
import textwrap
from typing import Any, Callable, Dict, List, Optional, Set

from .utils.logging_setup import logger

#: The derivation only. Callers ask the manipulator -- `manipulator.catalogue()` --
#: rather than running these over one from outside, which is what the request model
#: exists to avoid.
__all__ = ["derive", "label_for", "order", "requirements_of"]


def label_for(name: str, acronyms: Optional[Dict[str, str]] = None) -> str:
    """Turn a handler's name into something a person can be shown.

    Args:
        name (str): A handler's name without its operation prefix, such as `uv_coverage`.
        acronyms (Optional[Dict[str, str]]): Words that keep their own capitals, lower-cased
            keys to the spelling wanted -- `{"uv": "UV"}`. An application's vocabulary is one
            of the two things here that cannot be derived, so it is passed in.

    Returns:
        str: `UV Coverage`. Derived rather than listed, so adding a handler does not mean
            remembering to name it somewhere else.
    """
    known = acronyms or {}
    return " ".join(known.get(word, word.capitalize()) for word in name.split("_"))


def _source_of(owner: Any) -> Optional[str]:
    """Return the source of a class, dedented, or None if it cannot be read."""
    target = owner if isinstance(owner, type) else type(owner)
    try:
        return textwrap.dedent(inspect.getsource(target))
    except (OSError, TypeError) as e:
        logger.debug("Cannot read the source of %s: %s", getattr(target, "__name__", target), str(e))
        return None


def _methods(owner: Any) -> Dict[str, ast.FunctionDef]:
    """Return every method a class defines, by name, as syntax."""
    source = _source_of(owner)
    if source is None:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        logger.debug("Cannot parse the source of %s: %s", owner, str(e))
        return {}
    return {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def _called_names(node: ast.FunctionDef) -> List[str]:
    """Return the attribute names called inside one method, in source order."""
    return [child.func.attr for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)]


def _reached(name: str, methods: Dict[str, ast.FunctionDef], seen: Set[str]) -> Set[str]:
    """Return every name called by a method, following the methods of the same class.

    Notes:
        - Following anything the class itself defines, rather than names beginning with some
          agreed prefix, is what keeps this free of an application's conventions -- and it is
          also more complete, since a helper is a helper whatever it is called.
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
            instance when not given, so a registered `Super` needs no argument.
        interpret (Optional[Callable]): Given a called name, return what it means to the
            application, or None to ignore it. Without it, `touches` is left empty rather than
            filled with names only the application can read.

    Returns:
        Dict[str, Dict[str, List[str]]]: `{name: {"requires": [...], "calls": [...],
            "touches": [...]}}`. `requires` names other handlers of the same operation;
            `calls` is every name reached, raw; `touches` is what `interpret` made of them.

    Notes:
        - `requires` is exact and **direct**: the handlers this one names, not everything they
          in turn reach. That is the edge set a scheduler needs, and the transitive closure
          follows from it while the reverse does not.
        - `calls` and `touches` are an **upper bound**. A helper shared between handlers is
          followed for each of them, so a handler is credited with everything its helpers can
          reach rather than with what it uses. Good for checking a declaration; wrong as one.
    """
    operation = operation or getattr(owner, "_operation", None) or getattr(owner, "OPERATION", None)
    if not operation:
        logger.debug("%s has no operation name; nothing to derive", owner)
        return {}

    prefix = f"_{operation}_"
    methods = _methods(owner)
    handlers = [name for name in methods if name.startswith(prefix)]

    catalogue: Dict[str, Dict[str, List[str]]] = {}
    for handler in handlers:
        # Direct, not transitive. A scheduler wants the edges that were written; the closure
        # follows from them, and reporting the closure instead loses which is which -- and
        # says a handler needs something it never mentions.
        requires = {name[len(prefix):] for name in _called_names(methods[handler])
                    if name.startswith(prefix) and name != handler}
        reached = _reached(handler, methods, set())
        touches = set()
        if interpret is not None:
            touches = {meaning for meaning in (interpret(name) for name in reached) if meaning}
        catalogue[handler[len(prefix):]] = {
            "requires": sorted(requires),
            "calls": sorted(reached),
            "touches": sorted(touches),
        }
    return catalogue


def requirements_of(catalogue: Dict[str, Dict[str, List[str]]], name: str) -> List[str]:
    """Return everything a handler needs, directly or through what it needs.

    Args:
        catalogue (Dict): What `derive` produced for one operation.
        name (str): The handler to ask about.

    Returns:
        List[str]: Sorted, and excluding the handler itself. Empty for one that needs nothing.

    Notes:
        - The edges are stored **direct** because that is the more informative of the two: the
          full set follows from them by walking, and walking backwards -- recovering which
          edges were written from a closure -- is not possible. So this is a walk offered on
          demand rather than a second thing to keep in step with the first.
        - A cycle is followed once and left, since a handler cannot sensibly require itself.
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
            prerequisite nobody asked for is not invented: a caller asking for two things gets
            two things.

    Notes:
        - A cycle is a defect in somebody's handlers rather than in this function, so it is
          logged and the remainder appended. Refusing to order them is not a reason to refuse
          to run them.
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
