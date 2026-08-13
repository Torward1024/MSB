# results.py
"""Result types of the operation protocol.

Kept out of both `Super` and `Manipulator`: a Super produces these, a Manipulator passes
them on, and neither owns them. Having them here also keeps the two modules from importing
each other.
"""
from typing import Any, Dict

__all__ = ["MethodResults", "Response", "unwrap"]


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

    A `dict` with the protocol's own keys -- `status`, `object`, `method`, `result`, and
    `error` and `error_type` when something went wrong -- so it logs, journals and serialises
    exactly as it always did. The properties below are what stop every caller writing the same
    unwrapping by hand.

    | | |
    | --- | --- |
    | `ok` | Whether it succeeded |
    | `value` | What it produced, unwrapped as a facade unwraps it |
    | `error` | The message, or None |
    | `error_type` | The name of the exception class, or None |

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
