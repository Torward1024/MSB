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
from typing import Any, Callable, Dict, Protocol, Type, runtime_checkable

__all__ = ["Interceptor", "MethodProvider"]


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


@runtime_checkable
class Interceptor(Protocol):
    """Sees a request before it runs and its response after, and decides what happens between.

    Metrics, auditing, rate limiting and authorisation are not four features; they are four
    users of this one hook, which is why MSB provides the hook and none of the four. A library
    that chose a metrics backend would end the promise of no dependencies, and a library that
    chose an authorisation model would be wrong about somebody's.

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
        - The first added is the outermost, so it sees the request first and the response last.
        - The request is passed as it is, not copied. That is deliberate: an interceptor is
          meant to be able to rewrite it, and a recorded request has to be the one that ran or
          a session cannot be replayed from the record.
        - An asynchronous surface wraps the same way, since `call_next` is only a callable.
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
