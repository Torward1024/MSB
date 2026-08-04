"""What the layers of MSB require of each other, stated as interfaces.

A contract that names a class says more than it means. `Super` took a `Manipulator`, which
reads as though an operation needs the orchestrator -- registry, facades, batching and all --
when it needs one method from it. That is worth stating precisely for three reasons: an
extension contract should name an interface rather than an implementation, a `Super` should be
testable without building the layer above it, and the operation layer should not import from
the entry-point layer above it to say what it accepts.

These are `typing.Protocol`, so nothing has to declare that it implements one: `Manipulator`
satisfies `MethodProvider` by having the method, and so does a stub of three lines. They are
runtime-checkable, so `isinstance` works where a check is genuinely wanted.
"""
from typing import Callable, Dict, Protocol, Type, runtime_checkable

__all__ = ["MethodProvider"]


@runtime_checkable
class MethodProvider(Protocol):
    """Answers which methods may be applied to an object of a given type.

    The whole of what a `Super` needs from whatever drives it. A `Super` resolves a handler
    itself and applies methods itself; what it cannot know alone is which methods a request is
    permitted to name for a given type, because that is registered with the orchestrator.

    `Manipulator` implements this. So does anything else that answers the question, which is
    the point: an operation can be driven by a test stub, by a narrower registry, or by
    something that has not been written yet.
    """

    def get_methods_for_type(self, obj_type: Type) -> Dict[str, Callable]:
        """Return the methods registered for a type.

        Args:
            obj_type (Type): The type of the object an operation is about to act on.

        Returns:
            Dict[str, Callable]: Method names mapped to their implementations.

        Raises:
            DispatchError: If nothing is registered for the type.
        """
        ...
