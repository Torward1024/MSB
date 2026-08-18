"""The operations a `Manipulator` registers for you.

| Operation | What it does |
| --- | --- |
| `inspect` | Applies every method a request names and reports each outcome |
| `configure` | The same, stopping at the first failure |
| `catalogue` | Reports what is registered, and the shape of the model |
| `save` | Writes an object to a file |
| `load` | Reads one back |

`inspect` and `configure` follow from the request model rather than from any domain: an attribute
names a method, and the method either reads or writes. Operations like `calculate` are domain work
and stay yours to write.

All are registered unless a `Manipulator` is built with `builtins=False`. Registering an operation
of the same name replaces one silently: it is a default being overridden, not a collision.

Each is thin -- usually one call to `_apply_methods` -- so overriding the handler for one type
leaves the rest working.
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
        Optional[Any]: What the operation produced for the item, or None when the request names
            no item, which means the methods apply to `obj` itself.

    Raises:
        DispatchError: If the request names an item the collection does not hold.

    Notes:
        - A request against a collection means one of two things and only the request says
          which: `inspect(box, get_all=None)` asks the collection, `inspect(box, name="bolt",
          get="length")` asks one member. The key is removed before descending, so the item
          sees only the methods meant for it.
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
        manipulator.inspect(part, get="price", has_attribute="price")
        ```

    Notes:
        - `strict=False`: a request naming several methods reports every outcome rather than
          stopping at the first failure, since a reader usually wants the whole picture.
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
            - The hook for descent, which is not uniform: a container answers `get(name)`, a
              `Project` answers something else. Override it and both built-ins descend into
              your type correctly.
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
        manipulator.configure(part, set={"params": {"price": 4.5}})
        ```

    Notes:
        - `strict=True`: the first failure stops the rest, since a half-applied configuration is
          worse than a rejected one.
        - Returns `MethodResults`, uniformly, which is what makes a request history replayable.
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
        - An operation rather than a function over a manipulator, so a dialog, a command line
          and a server all ask the same way.
        - Replaceable like any built-in: register an operation named `catalogue`.

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
            - The manipulator assembles the answer, since the registry is its own state. This
              makes it reachable as a request.
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
            - `_catalogue` says what can be done; this says what it can be done to. Both are
              derived rather than declared.
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
    """Shared by `Persistence` and `Loader`: the attribute check both need."""

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
            RequestError: If it was not given. There is no sensible default for a path.
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
        - The format is a default, not a law: JSON over `to_dict`. An application wanting
          otherwise registers its own `save`.
        - The write is atomic -- a temporary file beside the target, then a rename -- so an
          interrupted write leaves the previous file rather than a truncated one.

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
            - Written beside the target and renamed: a rename within one directory is atomic on
              every supported platform.
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

    Separate from `Persistence` because a `Super` binds to one operation name.

    Examples:
        >>> manipulator.load(entity, path="entity.json")
        Entity(name='entity', ...)
    """

    OPERATION = "load"

    def _load(self, obj: Any, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Read a file back into an object of the same kind as the one asked.

        Args:
            obj (Serializable): An object of the type to rebuild. A request runs on something,
                and here that something says what to build.
            attributes (Dict[str, Any]): `path`, the file to read; optionally `kind`, the class
                to build or its name, for reading something no instance exists of.

        Returns:
            Any: The object itself, not a mapping holding it, so a pipeline step reading a file
                hands the object straight to the next step.

        Raises:
            RequestError: If no path was given or the type cannot rebuild itself.
            NotFoundError: If there is no such file.
            SerializationError: If the file is not JSON the type can read.
        """
        path = Path(self._required(attributes, "path", "load"))
        kind = attributes.get("kind") or type(obj)
        if isinstance(kind, str):
            from ..model import named_type
            kind = named_type(kind)          # a plan or a wire carries a name
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

        # The type comes from the caller, not from the file. Data written by something else may
        # still restore -- field for field, silently -- so say when that is what is happening.
        written_by = data.get("type") if isinstance(data, dict) else None
        if written_by and written_by not in {ancestor.__name__ for ancestor in kind.__mro__}:
            logger.warning("'%s' was written by %s; reading it as %s", path, written_by,
                           kind.__name__)

        restored = kind.from_dict(data)
        logger.info("Read %s from '%s'", kind.__name__, path)
        return restored
