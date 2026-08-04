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
from typing import Any, Dict

from .super import Super

__all__ = ["Configurator", "Inspector"]


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

    def _inspect(self, obj: Any, attributes: Dict[str, Any]) -> Any:
        """Apply every method the request names to any object.

        Args:
            obj (Any): The object to read.
            attributes (Dict[str, Any]): Method names mapped to their arguments.

        Returns:
            MethodResults: Every method that ran, mapped to its outcome.
        """
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

    def _configure(self, obj: Any, attributes: Dict[str, Any]) -> Any:
        """Apply every method the request names to any object, stopping at the first failure.

        Args:
            obj (Any): The object to change.
            attributes (Dict[str, Any]): Method names mapped to their arguments.

        Returns:
            MethodResults: Every method that ran, mapped to its outcome.
        """
        return self._apply_methods(obj, attributes, strict=True)
