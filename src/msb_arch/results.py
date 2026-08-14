# results.py
"""Result types of the operation protocol.

Kept out of both `Super` and `Manipulator`: a Super produces these, a Manipulator passes
them on, and neither owns them. Having them here also keeps the two modules from importing
each other.
"""
from typing import Any, Dict, NotRequired, TypedDict

__all__ = ["MethodOutcome", "MethodResults", "Response", "ResponseData", "unwrap"]


class MethodOutcome(TypedDict):
    """What one named method of a request produced.

    Keys:
        status (bool): Whether that method worked.
        result (Any): What it returned. None when it failed.
        error (str): The message, present only on a failure.
    """

    status: bool
    result: Any
    error: NotRequired[str]


class ResponseData(TypedDict):
    """The shape of a response, as data.

    Every request produces this: a `Response` in the process that ran it, and exactly this
    mapping once it has been through JSON, a log, a journal or a wire. A framework about
    validating types owed its own protocol a type.

    Keys:
        status (bool): Whether the request succeeded.
        object (str): The `name` of the object it ran on, or the value itself when the request
            was made on plain data.
        method (str): The handler that ran, or None when the operation dispatched by type.
        result (Any): What the handler produced -- for the usual handler, a mapping of method
            name to `MethodOutcome`.
        error (str): The message, present only on a failure.
        error_type (str): The name of the exception class, present only on a failure.

    Notes:
        - `Response` is this shape plus the four properties that save a caller unwrapping it by
          hand. Annotate what crosses a boundary as `ResponseData`; annotate what a call returns
          as `Response`.
        - `error` and `error_type` are absent rather than None on a success, which is why they
          are `NotRequired`. Read them with `.get`, or through `Response.error`.

    Example:
        ```python
        def render(response: ResponseData) -> str:
            return "ok" if response["status"] else f"failed: {response['error']}"
        ```
    """

    status: bool
    object: Any
    method: NotRequired[Any]
    result: NotRequired[Any]
    error: NotRequired[Any]
    error_type: NotRequired[Any]


class MethodResults(dict):
    """Outcome of applying several named methods to one object.

    Maps a method name to its outcome, `{"status": bool, "result": Any}` plus `"error"`
    when it failed. A plain dict subclass, so it serializes and replays like any mapping
    while still being recognisable: the facade unwraps a single entry to its value, and a
    request history can read every method that ran and what each returned.

    Notes:
        - The shape does not depend on how many methods a request named. That is what makes
          a history replayable; a handler returning only the last result made the outcome
          depend on the order of the keys in the request.
    """

    def values_only(self) -> Dict[str, Any]:
        """Return just the results, dropping the per-method status.

        Returns:
            Dict[str, Any]: Method name mapped to the value it produced. A method that failed
                maps to None, since it produced nothing -- check `status` in the entry itself
                to tell that apart from a method that returned None.
        """
        return {name: outcome.get("result") for name, outcome in self.items()}


def unwrap(result: Any) -> Any:
    """Reduce a one-method result mapping to the value it holds.

    Args:
        result (Any): Whatever a handler returned.

    Returns:
        Any: The single value if `result` reports exactly one method, `result` otherwise.

    Notes:
        - Only `MethodResults` is unwrapped, never a plain dictionary a handler happens to
          return, so a handler producing real data of its own is left alone.
        - The one place the rule lives: a facade and `Response.value` both call it, so the two
          cannot answer differently.
    """
    if isinstance(result, MethodResults) and len(result) == 1:
        return next(iter(result.values()))["result"]
    return result


class Response(dict):
    """What a request produced.

    A `dict` in the shape of `ResponseData` -- `status`, `object`, `method`, `result`, and
    `error` and `error_type` when something went wrong -- so it logs, journals and serialises
    exactly as it always did. The properties below are what stop every caller writing the same
    unwrapping by hand.

    | | |
    | --- | --- |
    | `ok` | Whether it succeeded |
    | `value` | What it produced, unwrapped as a facade unwraps it |
    | `error` | The message, or None |
    | `error_type` | The name of the exception class, or None |

    Notes:
        - The keys are typed by `ResponseData`, which is the same shape once it has been through
          JSON or a wire and is no longer this class.

    Examples:
        >>> answer = manipulator.inspect(part, get="price", raise_on_error=False)
        >>> answer.ok
        True
        >>> answer.value
        4.5
    """

    @property
    def ok(self) -> bool:
        """Whether the request succeeded."""
        return bool(self.get("status"))

    @property
    def value(self) -> Any:
        """What the request produced, unwrapped as a facade unwraps it.

        Returns:
            Any: The value of the one method named, or whatever the handler returned. None for
                a failed request, which produced nothing.
        """
        return unwrap(self.get("result")) if self.get("status") else None

    @property
    def error(self) -> Any:
        """The message, or None if it succeeded."""
        return self.get("error")

    @property
    def error_type(self) -> Any:
        """The name of the exception class that caused it, or None."""
        return self.get("error_type")

    def raise_if_failed(self) -> "Response":
        """Raise the kind of failure that happened, or return this response.

        Returns:
            Response: This response, so it can be chained.

        Raises:
            MSBError: The kind named by `error_type`, or `HandlerError` for anything else.
        """
        if self.ok:
            return self
        from .errors import HandlerError, MSBError
        from . import errors as taxonomy

        named = getattr(taxonomy, self.get("error_type") or "", None)
        message = self.get("error", "Unknown error")
        if isinstance(named, type) and issubclass(named, MSBError):
            raise named(message)
        raise HandlerError(message)
