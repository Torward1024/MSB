"""What the layers of MSB require of each other, as interfaces.

A `Super` needs one method from whatever drives it, not the whole orchestrator, so the contract
names an interface. That keeps a `Super` testable without the layer above it, and keeps the
operation layer from importing the entry-point layer.

These are `typing.Protocol`: nothing declares that it implements one, and `isinstance` works
where a check is wanted.
"""
from typing import Any, Callable, Dict, Protocol, Type, runtime_checkable

__all__ = ["Interceptor", "MethodProvider"]


@runtime_checkable
class MethodProvider(Protocol):
    """Answers which methods may be applied to an object of a given type.

    The whole of what a `Super` needs from whatever drives it: it resolves handlers and applies
    methods itself, but which methods a request may name for a type is registered with the
    orchestrator.

    `Manipulator` implements this, and so does a three-line test stub.
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


@runtime_checkable
class Interceptor(Protocol):
    """Sees a request before it runs and its response after, and decides what happens between.

    Metrics, auditing, rate limiting and authorisation are four users of this one hook, which is
    why MSB provides the hook and none of the four.

    An interceptor is called with the request and with `call_next`, and returns a response. It
    may:

    - **observe**, by calling `call_next` and returning what it gives back;
    - **time or count**, by doing something either side of that call;
    - **refuse**, by returning a failed response without calling `call_next` at all, which is
      what rate limiting and authorisation need;
    - **rewrite**, by changing the request before passing it on -- the seam a pipeline would
      later use to substitute a step's result into the request that depends on it.

    They wrap a single request, not a batch: a batch is a container of requests rather than a
    request, and each of its entries is separately answerable and separately replayable. Ten
    requests in a batch mean ten interceptions.

    Example:
        ```python
        def timing(request, call_next):
            started = time.perf_counter()
            response = call_next(request)
            print(request["operation"], time.perf_counter() - started)
            return response

        manipulator.add_interceptor(timing)
        ```

    Notes:
        - The first added is the outermost: it sees the request first and the response last.
        - The request is passed as it is, not copied, so an interceptor can rewrite it and a
          recorded request is the one that ran.
        - The asynchronous surface wraps the same way, since `call_next` is only a callable.
    """

    def __call__(self, request: Dict[str, Any], call_next: Callable[[Dict[str, Any]], Any]) -> Any:
        """Handle a request, usually by passing it on.

        Args:
            request (Dict[str, Any]): The request about to run.
            call_next (Callable[[Dict[str, Any]], Any]): The rest of the chain, ending in the
                orchestrator itself. Call it with a request to get a response.

        Returns:
            Any: The response, whether it came from `call_next` or was made up instead.
        """
        ...
