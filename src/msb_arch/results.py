# results.py
"""Result types of the operation protocol.

Kept out of both `Super` and `Manipulator`: a Super produces these, a Manipulator passes
them on, and neither owns them. Having them here also keeps the two modules from importing
each other.
"""
from typing import Any, Dict

__all__ = ["MethodResults"]


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
            Dict[str, Any]: Method name mapped to the value it produced.
        """
        return {name: outcome.get("result") for name, outcome in self.items()}
