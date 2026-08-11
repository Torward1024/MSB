"""What a `Super` offers, and how its handlers depend on each other, worked out from the code.

An application built on MSB knows what it can do twice: once in the handlers that do the work,
and again in whatever menu, list or table offers them. The second copy is written by hand, goes
out of date, and makes adding a feature cost edits in places that have no business knowing
about it.

Almost none of it needs writing down. A `Super`'s handlers name themselves, so the list and its
labels come free. The edges between them are in the code -- handlers call each other directly
-- and walking the syntax tree recovers them exactly: measured on a 2 700-line calculator
downstream, all fourteen result-to-result edges, with nothing declared.

What does **not** derive is which parts of a *model* a handler reads. The same walk
over-approximates, because a shared helper fetches everything whether its caller uses it or
not: six of fourteen came out wider than the truth. Handing back the wide answer would restore
exactly the coarseness that declaring it exists to remove. So `reads` is offered as a **check
on a declaration**, never as a replacement for one.
"""
import ast
import inspect
import re
from typing import Any, Dict, List, Optional, Set

from msb_arch.utils.logging_setup import logger

#: Accessors that reach a part of the model, and the part each reaches.
MODEL_ACCESSORS = {"get_telescopes": "telescopes", "get_sources": "sources",
                   "get_scans": "scans", "get_frequencies": "frequencies"}

#: Prefixes of helpers worth following. A handler rarely touches the model itself; it hands
#: the work to one of these.
HELPER_PREFIXES = ("_process_", "_get_", "_compute_", "_calculate_")

def label_for(key: str, acronyms: Optional[Dict[str, str]] = None) -> str:
    """Turn a handler's name into something to put in a menu.

    Args:
        key (str): A handler's name without its prefix, such as `uv_coverage`.
        acronyms (Optional[Dict[str, str]]): Words that keep their own capitals, lower-cased
            keys to the spelling wanted -- `{"uv": "UV"}`. An application's vocabulary is the
            one thing here that cannot be derived, so it is passed in rather than guessed.

    Returns:
        str: `UV Coverage`. Derived rather than listed, so adding a handler does not mean
            remembering to name it somewhere else.
    """
    known = acronyms or {}
    return " ".join(known.get(word, word.capitalize()) for word in key.split("_"))


def _functions(owner: Any) -> Dict[str, ast.FunctionDef]:
    """Return every method of a class, by name, as syntax."""
    try:
        source = inspect.getsource(type(owner) if not isinstance(owner, type) else owner)
    except (OSError, TypeError) as e:
        logger.debug("Cannot read the source of %s: %s", owner, str(e))
        return {}
    tree = ast.parse(re.sub(r"^\s{4}", "", source, flags=re.M) if source.startswith("    ") else source)
    return {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def _reads(name: str, functions: Dict[str, ast.FunctionDef], seen: Optional[Set[str]] = None) -> Set[str]:
    """Return the model parts a method touches, following the helpers it delegates to."""
    seen = seen if seen is not None else set()
    if name in seen or name not in functions:
        return set()
    seen.add(name)

    found: Set[str] = set()
    for node in ast.walk(functions[name]):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        called = node.func.attr
        if called in MODEL_ACCESSORS:
            found.add(MODEL_ACCESSORS[called])
        elif called.startswith(HELPER_PREFIXES):
            found |= _reads(called, functions, seen)
    return found


def derive(owner: Any, prefix: str) -> Dict[str, Dict[str, List[str]]]:
    """Work out what an operation offers, and how its handlers depend on each other.

    Args:
        owner (Super): The instance to read, such as a `ScheduleCalculator`.
        prefix (str): The handler prefix, such as `_calculate_`.

    Returns:
        Dict[str, Dict[str, List[str]]]: `{key: {"requires": [...], "reads": [...]}}`, where
            `requires` names other handlers of the same operation and `reads` names parts of
            the model. Both sorted, so the answer does not depend on iteration order.

    Notes:
        - `requires` is exact: handlers call each other by name, and a call is a call. This is
          the edge set a scheduler needs -- what may run at once, and what a change invalidates.
        - `reads` is an **upper bound**, not the truth. It is offered for checking a
          declaration, never for replacing one.
    """
    functions = _functions(owner)
    handlers = [name for name in functions if name.startswith(prefix)]

    catalogue = {}
    for handler in handlers:
        requires = set()
        for node in ast.walk(functions[handler]):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr.startswith(prefix) and node.func.attr != handler):
                requires.add(node.func.attr[len(prefix):])
        catalogue[handler[len(prefix):]] = {
            "requires": sorted(requires),
            "reads": sorted(_reads(handler, functions)),
        }
    return catalogue


def order(catalogue: Dict[str, Dict[str, List[str]]], wanted: List[str]) -> List[str]:
    """Return the wanted calculations in an order that satisfies their prerequisites.

    Args:
        catalogue (Dict): What `derive` produced.
        wanted (List[str]): The keys asked for, in any order.

    Returns:
        List[str]: The same keys, each after everything it needs. A key whose prerequisite was
            not asked for is left where it falls -- the calculator computes what it needs on
            its own, so a missing prerequisite is not an error here.

    Notes:
        - A cycle would be a defect in the calculations rather than in this function, so it is
          logged and the remaining keys are appended rather than raising: refusing to order
          them is not a reason to refuse to run them.
    """
    remaining = list(dict.fromkeys(wanted))
    placed, result = set(), []

    while remaining:
        ready = [key for key in remaining
                 if all(need in placed or need not in remaining
                        for need in catalogue.get(key, {}).get("requires", []))]
        if not ready:
            logger.warning("Cannot order %s by their prerequisites; leaving them as given",
                           remaining)
            result.extend(remaining)
            break
        for key in ready:
            result.append(key)
            placed.add(key)
            remaining.remove(key)
    return result
