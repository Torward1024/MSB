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
from typing import Any, Callable, Dict, Optional

from ..base.basecontainer import BaseContainer
from ..errors import DispatchError
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
