# scaffold.py
"""Generate the handler stubs a model implies, so the boilerplate is written once.

Adding an operation over a model means one handler per type it applies to, each named
`_<operation>_<type>` so dispatch finds it. The names, the signatures and the descent into
containers all follow from the model graph, which is already derived. What does not follow is
what the handlers *do*, and that is the only part left to write.

This emits text rather than classes. A generated stub is meant to be read, edited and committed;
a class conjured at runtime would be neither.

Reached through the manipulator, like everything else: `manipulator.scaffold("measure")`.
"""
from typing import Any, Dict, List, Optional

__all__ = ["stubs"]

_HEADER = '''"""Handlers for the `{operation}` operation.

Generated from the model, then edited: the names and the descent are derived, the bodies are not.
"""
from typing import Any, Dict

from msb_arch import Super


class {classname}(Super):
    """Applies `{operation}` to {counted}."""

    OPERATION = "{operation}"
'''

_ENTITY = '''
    def _{operation}_{lowered}(self, obj: Any, attributes: Dict[str, Any]) -> Any:
        """{verb} one {name}.

        Args:
            obj ({name}): The object to work on.
            attributes (Dict[str, Any]): What the request carried.{fields}
        """
        raise NotImplementedError("_{operation}_{lowered}")
'''

_CONTAINER = '''
    def _{operation}_{lowered}(self, obj: Any, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """{verb} every {held} in a {name}.

        Args:
            obj ({name}): The container to work through.
            attributes (Dict[str, Any]): What the request carried, passed to each item.

        Returns:
            Dict[str, Any]: What each item produced, by name.
        """
        return {{name: self._{operation}_{held_lowered}(item, attributes)
                for name, item in obj.get_all().items()}}
'''


def stubs(graph: Dict[str, Dict[str, Any]], operation: str,
          only: Optional[List[str]] = None) -> str:
    """Return the source of a `Super` with one handler per type in the model.

    Args:
        graph (Dict[str, Dict[str, Any]]): What `derive_model` produced.
        operation (str): The operation the handlers serve.
        only (Optional[List[str]]): Limit it to these type names. Defaults to every type.

    Returns:
        str: Python source, ready to be written to a file and edited.

    Notes:
        - A container gets a handler that walks its items and calls the handler for what it
          holds, since that descent is the same every time and is what the graph knows.
        - An entity gets a stub that raises `NotImplementedError`, listing what it holds in the
          docstring. A stub that returned None would be a handler that silently did nothing.
          Through a facade the failure arrives as `HandlerError` naming the handler, as any
          exception the framework did not define does.
        - Types are emitted deepest first, so a container's handler appears after the one it
          calls and the file reads in the order the work happens.

    Examples:
        >>> print(stubs(graph, "measure"))
        \"\"\"Handlers for the `measure` operation....
    """
    if not operation.isidentifier():
        from .errors import RequestError
        raise RequestError(
            f"'{operation}' cannot be an operation name, so nothing valid can be generated for "
            "it: a handler is a method and a method needs an identifier")

    wanted = [name for name in _deepest_first(graph) if only is None or name in only]
    if not wanted:
        return ""

    verb = operation.capitalize()
    text = _HEADER.format(operation=operation,
                          classname=f"{verb}Handlers",
                          counted=_counted(wanted))

    for name in wanted:
        entry = graph[name]
        if entry.get("container") and entry.get("holds", {}).get("items"):
            held = entry["holds"]["items"][0]
            text += _CONTAINER.format(operation=operation, lowered=name.lower(), name=name,
                                      verb=verb, held=held, held_lowered=held.lower())
        else:
            text += _ENTITY.format(operation=operation, lowered=name.lower(), name=name,
                                   verb=verb, fields=_fields_note(entry))
    return text


def _deepest_first(graph: Dict[str, Dict[str, Any]]) -> List[str]:
    """Return the type names with the ones nothing holds last.

    Notes:
        - So a container's handler is emitted after the handler it calls. A cycle stops the
          ordering rather than the generation: the remainder is appended in the order it came.
    """
    remaining = list(graph)
    placed: List[str] = []
    while remaining:
        ready = [name for name in remaining
                 if all(held not in remaining or held == name
                        for names in graph[name].get("holds", {}).values() for held in names)]
        if not ready:
            placed.extend(remaining)
            break
        placed.extend(ready)
        remaining = [name for name in remaining if name not in ready]
    return placed


def _counted(names: List[str]) -> str:
    """Describe how many types the generated class covers."""
    if len(names) == 1:
        return f"a {names[0]}"
    return f"{len(names)} types: {', '.join(names)}"


def _fields_note(entry: Dict[str, Any]) -> str:
    """List the modelled types a type holds, as a line in the generated docstring."""
    holds = entry.get("holds") or {}
    if not holds:
        return ""
    listed = ", ".join(f"{field} ({', '.join(types)})" for field, types in sorted(holds.items()))
    return f"\n\n        Holds: {listed}."
