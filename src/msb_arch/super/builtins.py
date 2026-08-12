"""The two operations that fall out of the request model itself.

A request names methods to apply, and `_apply_methods` applies them. For reading an object and
for changing it, that is the entire handler: measured on the project this framework was written
for, 20 of its 21 handlers held no domain logic at all, and six were literally a type check and
one call -- with the type check redundant, since dispatch had already selected the handler by
type.

`inspect` and `configure` are the two that generalise, because they follow from the request
model rather than from any domain: an attribute names a method, and the method either reads or
writes. Operations like `calculate` or `visualize` are domain work and stay yours to write.

Both are registered by a `Manipulator` unless it is told not to, so an application that only
reads and writes its model needs no `Super` of its own. Registering an operation of the same
name replaces the built-in silently -- it is a default being overridden, not a collision -- so
nothing written before these existed behaves differently.

They are deliberately thin. Each is one call to `_apply_methods`, which is what makes them
worth subclassing: override the handler for a type that needs domain logic and the rest keeps
working.
"""
from typing import Any, Callable, Dict, List, Optional

from ..base.basecontainer import BaseContainer
import json
from pathlib import Path

from ..errors import (DispatchError, NotFoundError, RequestError,
                      SerializationError)
from ..utils.logging_setup import logger
from .super import Super

__all__ = ["Configurator", "Inspector"]


def _descend(operation: Super, obj: Any, attributes: Dict[str, Any]) -> Optional[Any]:
    """Run the operation against one named item of a collection, if the request names one.

    Args:
        operation (Super): The operation asking, which supplies the two hooks below.
        obj (Any): The object the request arrived for.
        attributes (Dict[str, Any]): The request's attributes.

    Returns:
        Optional[Any]: What the operation produced for the item, or None when the request
            names no item -- which is the signal to apply the methods to `obj` itself.

    Raises:
        DispatchError: If the request names an item the collection does not hold.

    Notes:
        - A request against a collection means one of two things, and only the request can
          say which: `inspect(frequencies, get_all=None)` asks the collection, while
          `inspect(frequencies, name="IF1", get_frequency=None)` asks one member of it. The
          key is removed before descending, so the item sees only the methods meant for it.
    """
    key = operation.NESTED_KEY
    if key not in attributes:
        return None

    getter = operation._nested_getter(obj)
    if getter is None:
        return None

    handler = getattr(operation, f"_{operation._operation}")
    outcome = operation._do_nested(obj, attributes, key, getter, handler)
    if outcome["status"]:
        return outcome["result"]
    raise DispatchError(outcome.get("error", f"Could not reach {attributes[key]!r} in "
                                             f"{type(obj).__name__}"))



class Inspector(Super):
    """Reads an object: applies every method a request names and reports each outcome.

    Example:
        ```python
        manipulator.inspect(telescope, get_diameter=None, get=["name", "isactive"])
        ```

    Notes:
        - Registered automatically, so `inspect` is available without writing anything.
        - `strict=False`, so a request naming several methods reports every outcome rather
          than stopping at the first failure. Reading is the case where a caller most often
          wants the whole picture.
    """

    OPERATION = "inspect"

    # The attribute a request uses to name one member of a collection. Change it in a
    # subclass whose model spells it differently.
    NESTED_KEY = "name"

    def _nested_getter(self, obj: Any) -> Optional[Callable]:
        """Return how to fetch a member of `obj` by name, or None if it holds no members.

        Args:
            obj (Any): The object a request arrived for.

        Returns:
            Optional[Callable]: A callable taking a name and returning the member.

        Notes:
            - **This is the hook, and it exists because the descent is not uniform.** A
              container answers `get(name)`; a `Project` answers `get_observation(name)`;
              something else will answer differently again. Override this and both built-ins
              descend correctly into it.
        """
        return obj.get if isinstance(obj, BaseContainer) else None

    def _inspect(self, obj: Any, attributes: Dict[str, Any]) -> Any:
        """Apply every method the request names to any object.

        Args:
            obj (Any): The object to read.
            attributes (Dict[str, Any]): Method names mapped to their arguments.

        Returns:
            MethodResults: Every method that ran, mapped to its outcome.
        """
        descended = _descend(self, obj, attributes)
        if descended is not None:
            return descended
        return self._apply_methods(obj, attributes, strict=False)


class Configurator(Super):
    """Changes an object: applies every setter a request names and reports each outcome.

    Example:
        ```python
        manipulator.configure(telescope, set_diameter=64.0)
        ```

    Notes:
        - Registered automatically, so `configure` is available without writing anything.
        - `strict=True`, so the first failure stops the rest. A half-applied configuration is
          worse than a rejected one, which is the opposite of what reading wants.
        - Returns `MethodResults` rather than the bespoke value a hand-written configure
          handler tends to invent. A configure result is rarely read, and a uniform one is
          what makes a request history replayable.
    """

    OPERATION = "configure"

    NESTED_KEY = "name"

    def _nested_getter(self, obj: Any) -> Optional[Callable]:
        """Return how to fetch a member of `obj` by name, or None if it holds no members.

        See `Inspector._nested_getter`; the two share the hook and the reason for it.
        """
        return obj.get if isinstance(obj, BaseContainer) else None

    def _configure(self, obj: Any, attributes: Dict[str, Any]) -> Any:
        """Apply every method the request names to any object, stopping at the first failure.

        Args:
            obj (Any): The object to change.
            attributes (Dict[str, Any]): Method names mapped to their arguments.

        Returns:
            MethodResults: Every method that ran, mapped to its outcome.
        """
        descended = _descend(self, obj, attributes)
        if descended is not None:
            return descended
        return self._apply_methods(obj, attributes, strict=True)

class Catalogue(Super):
    """Answers what this manipulator offers, worked out from what was registered with it.

    Args:
        manipulator (Manipulator): The orchestrator whose registry is being reported.

    Notes:
        - A built-in operation rather than a function a caller may run over a manipulator,
          because reaching into an orchestrator from outside to read its registry is exactly
          what the request model exists to avoid. A dialog, a command line and a server each
          ask the same question the same way: `manipulator.catalogue()`.
        - Replaceable like any other built-in: register an operation named `catalogue` and it
          takes over.

    Examples:
        >>> manipulator.catalogue()
        {'inspect': {...}, 'configure': {...}}
    """

    OPERATION = "catalogue"

    def _catalogue(self, obj: Any, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Report every operation registered, its handlers, and how they depend on each other.

        Args:
            obj (Any): Ignored. The catalogue describes the manipulator, not an object, and a
                request has to be made about something -- which is the one place this question
                sits awkwardly in the request model rather than naturally.
            attributes (Dict[str, Any]): `operation` to narrow the answer to one; `interpret`,
                a callable turning a called name into what it means to the application;
                `acronyms`, words that keep their own capitals in a label.

        Returns:
            Dict[str, Any]: `{operation: {handler: {"requires": [...], "calls": [...],
                "touches": [...], "label": str}}}`.

        Notes:
            - The registry is the manipulator's own state, so it assembles the answer; this
              only makes it reachable as a request, the way `Inspector` makes an object's own
              attributes reachable as one.
        """
        assembled = self._manipulator.describe_operations(
            operation=attributes.get("operation"),
            interpret=attributes.get("interpret"),
            acronyms=attributes.get("acronyms"))

        logger.debug("Catalogued %s operation(s)", len(assembled))
        return assembled

    def _catalogue_order(self, obj: Any, attributes: Dict[str, Any]) -> List[str]:
        """Return handlers in an order that satisfies their prerequisites.

        Args:
            obj (Any): Ignored.
            attributes (Dict[str, Any]): `operation`, whose handlers are being ordered, and
                `names`, the handlers asked for in any order.

        Returns:
            List[str]: The same names, each after everything it needs that was also asked for.
        """
        operation = attributes.get("operation")
        if not operation:
            raise RequestError("An 'operation' is needed to order its handlers")
        return self._manipulator.order_handlers(operation, attributes.get("names") or [])

    def _catalogue_model(self, obj: Any, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Report the shape of the model: which type holds which, and the reverse.

        Args:
            obj (Any): Ignored, as for `_catalogue`.
            attributes (Dict[str, Any]): `roots`, the types to start walking from, defaulting
                to the ones the manipulator knows; `of`, one type name to ask about instead of
                the whole graph.

        Returns:
            Dict[str, Any]: The graph, or `{"dependents": [...], "holds": [...]}` when `of`
                named one type.

        Notes:
            - The other half of what a catalogue is for. `_catalogue` says what can be done;
              this says what it can be done to, and both are read back rather than declared.
        """
        graph = self._manipulator.describe_model(attributes.get("roots"))
        wanted = attributes.get("of")
        if not wanted:
            logger.debug("Described %s type(s)", len(graph))
            return graph

        if wanted not in graph:
            raise NotFoundError(f"No type named '{wanted}' is in the model")
        from ..model import dependents_of, holdings_of
        return {"dependents": dependents_of(graph, wanted), "holds": holdings_of(graph, wanted)}


class _FileOperation(Super):
    """Shared by the two halves of persistence: the attribute check they both need."""

    @staticmethod
    def _required(attributes: Dict[str, Any], name: str, verb: str) -> Any:
        """Return an attribute a request cannot do without, refusing to guess one.

        Args:
            attributes (Dict[str, Any]): What the request carried.
            name (str): The attribute wanted.
            verb (str): What the caller was trying to do, for the message.

        Returns:
            Any: The value.

        Raises:
            RequestError: If it was not given. There is no sensible default for where a
                caller's files live.
        """
        value = attributes.get(name)
        if not value:
            raise RequestError(f"No '{name}' given; there is nowhere to {verb}")
        return value


class Persistence(_FileOperation):
    """Writes any serialisable object to a file.

    Args:
        manipulator (Manipulator): The orchestrator this is reached through.

    Notes:
        - **The format is a default, not a law.** JSON over `to_dict` suits most models and
          none perfectly; an application wanting otherwise registers its own `save`, and this
          steps aside as any built-in does.
        - **The write is atomic**: a temporary file beside the target, then a rename. An
          interrupted write leaves the previous file intact rather than a truncated one, and a
          truncated file is worse than an old one because it still looks like data. A framework
          taking on file I/O owes its callers at least this much, or they were better off
          writing it themselves.

    Examples:
        >>> manipulator.save(entity, path="entity.json")
        {'path': 'entity.json'}
    """

    OPERATION = "save"

    def _save(self, obj: Any, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Write an object to a file.

        Args:
            obj (Serializable): Anything that can turn itself into a dictionary.
            attributes (Dict[str, Any]): `path`, the file to write; optionally `indent`
                (4) and `overwrite` (True).

        Returns:
            Dict[str, Any]: `{"path": str}`.

        Raises:
            RequestError: If no path was given, the object cannot serialise itself, or a file
                is already there and `overwrite` is off.
            SerializationError: If what the object produced cannot be written as JSON.
        """
        path = Path(self._required(attributes, "path", "save"))
        if not hasattr(obj, "to_dict"):
            raise RequestError(
                f"{type(obj).__name__} cannot be written to a file: it has no to_dict")
        if path.is_dir():
            raise RequestError(f"'{path}' is a directory, so nothing can be written to it")
        if path.exists() and not attributes.get("overwrite", True):
            raise RequestError(f"'{path}' already exists and overwrite is off")

        try:
            text = json.dumps(obj.to_dict(), indent=attributes.get("indent", 4),
                              ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as e:
            raise SerializationError(
                f"{type(obj).__name__} produced something that is not JSON: {e}") from e

        self._write_atomically(path, text)
        logger.info("Wrote %s to '%s'", type(obj).__name__, path)
        return {"path": str(path)}

    @staticmethod
    def _write_atomically(path: Path, text: str) -> None:
        """Write a file so that an interruption leaves the previous one intact.

        Args:
            path (Path): Where the content belongs.
            text (str): What to write.

        Notes:
            - Written beside the target and renamed, because a rename within one directory is
              atomic on every platform this runs on.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        staging = path.with_name(path.name + ".writing")
        try:
            staging.write_text(text, encoding="utf-8")
            staging.replace(path)
        finally:
            if staging.exists():
                staging.unlink(missing_ok=True)


class Loader(_FileOperation):
    """Reads a file back into an object.

    Notes:
        - Separate from `Persistence` only because a `Super` binds to one operation name.

    Examples:
        >>> manipulator.load(entity, path="entity.json")
        Entity(name='entity', ...)
    """

    OPERATION = "load"

    def _load(self, obj: Any, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Read a file back into an object of the same kind as the one asked.

        Args:
            obj (Serializable): An object of the type to rebuild. A request runs on something,
                and here that something says what to build -- the one place this fits the
                request model awkwardly rather than naturally.
            attributes (Dict[str, Any]): `path`, the file to read; optionally `kind`, the class
                to build, for reading something that does not exist yet.

        Returns:
            Any: The object, rather than a mapping holding it. What a step produces is what the
                next step is given, so a `load` that answered `{"object": ...}` would make every
                chain through it start by unpacking a dictionary of one.

        Raises:
            RequestError: If no path was given or the type cannot rebuild itself.
            NotFoundError: If there is no such file.
            SerializationError: If the file is not JSON the type can read.
        """
        path = Path(self._required(attributes, "path", "load"))
        kind = attributes.get("kind") or type(obj)
        if isinstance(kind, str):
            from ..model import named_type
            kind = named_type(kind)          # a plan or a wire carries a name, not a class
        if not isinstance(kind, type) or not hasattr(kind, "from_dict"):
            raise RequestError(
                f"{getattr(kind, '__name__', kind)!r} cannot be read from a file: it is not a "
                "type with from_dict")
        if not path.is_file():
            raise NotFoundError(f"No file at '{path}'")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            raise SerializationError(f"'{path}' is not valid JSON: {e}") from e

        restored = kind.from_dict(data)
        logger.info("Read %s from '%s'", kind.__name__, path)
        return restored
