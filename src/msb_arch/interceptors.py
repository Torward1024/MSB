"""Two interceptors the framework ships: metrics and a request journal.

Both are ordinary `Interceptor` implementations with no privileged access, so reading them is
also the shortest explanation of the hook.

Neither is registered by default. An orchestrator with no interceptors pays one check per
request, so they cost nothing until asked for.

    manipulator.add_interceptor(RequestMetrics())
    manipulator.metrics()["inspect"]["calls"]
"""
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Iterator, List, Optional

from .utils.logging_setup import logger

__all__ = ["RequestJournal", "RequestMetrics"]


class RequestMetrics:
    """Counts and times requests, per operation.

    Holds the numbers and no opinion about where they go: read `snapshot()` and export it
    wherever you like. `manipulator.metrics()` returns the same thing.

    Example:
        ```python
        manipulator.add_interceptor(RequestMetrics())
        manipulator.metrics()["inspect"]["calls"]
        ```

    Notes:
        - A failed request counts as a call and as a failure, and its time still counts.
        - An exception propagates and is counted; swallowing it would change what the
          orchestrator does.
    """

    def __init__(self):
        self._calls = defaultdict(int)
        self._failures = defaultdict(int)
        self._seconds = defaultdict(float)
        self._slowest = defaultdict(float)

    def __call__(self, request: Dict[str, Any], call_next: Callable) -> Any:
        operation = request.get("operation", "<none>")
        started = time.perf_counter()
        try:
            response = call_next(request)
        except Exception:
            self._record(operation, time.perf_counter() - started, failed=True)
            raise
        elapsed = time.perf_counter() - started
        failed = isinstance(response, dict) and response.get("status") is False
        self._record(operation, elapsed, failed=failed)
        return response

    def _record(self, operation: str, elapsed: float, failed: bool) -> None:
        self._calls[operation] += 1
        self._seconds[operation] += elapsed
        self._slowest[operation] = max(self._slowest[operation], elapsed)
        if failed:
            self._failures[operation] += 1

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Return what has been measured so far, per operation.

        Returns:
            Dict[str, Dict[str, Any]]: Operation name mapped to `calls`, `failures`,
                `total_seconds`, `slowest_seconds` and `mean_seconds`.
        """
        return {
            operation: {
                "calls": self._calls[operation],
                "failures": self._failures[operation],
                "total_seconds": self._seconds[operation],
                "slowest_seconds": self._slowest[operation],
                "mean_seconds": self._seconds[operation] / self._calls[operation],
            }
            for operation in self._calls
        }

    def reset(self) -> None:
        """Forget everything measured so far."""
        self._calls.clear()
        self._failures.clear()
        self._seconds.clear()
        self._slowest.clear()


class RequestJournal:
    """Records what each request was and what it produced.

    An audit trail, and the basis of provenance. Read backwards it answers what produced a
    result; replayed forwards it runs the session again.

    Example:
        ```python
        manipulator.add_interceptor(RequestJournal())
        ...
        manipulator.history("part")          # what happened to one object
        manipulator.replay()                 # run the session again
        ```

    Notes:
        - Entries hold the request as it ran, including the live object it named. That makes
          in-process replay exact and means a journal cannot be written to a file as it stands.
        - `limit` keeps the most recent entries. Unlimited by default.
        - `fingerprints=True` records a hash of the object either side of each request, so
          `changed()` can say which requests altered anything. It costs a serialisation each
          way, so it is off by default.
        - Replay assumes deterministic handlers. One that reads the clock, a file or a random
          seed cannot be reconstructed from its request.
    """

    def __init__(self, limit: Optional[int] = None, fingerprints: bool = False):
        """Initialize an empty journal.

        Args:
            limit (Optional[int]): Keep at most this many entries, dropping the oldest.
                Defaults to None, meaning keep everything.
            fingerprints (bool): Record a hash of the object either side of each request, so
                `changed()` can report which requests altered anything. Off by default: it costs
                one serialisation of the object each way.
        """
        self._entries: List[Dict[str, Any]] = []
        self._limit = limit
        self._fingerprints = fingerprints

    def __call__(self, request: Dict[str, Any], call_next: Callable) -> Any:
        started = time.perf_counter()
        obj = request.get("obj")
        entry = {
            "operation": request.get("operation"),
            "object": getattr(obj, "name", obj),
            "attributes": dict(request.get("attributes") or {}),
            "request": request,
        }
        if self._fingerprints:
            entry["before"] = self._fingerprint(obj)
        try:
            response = call_next(request)
        except Exception as error:
            entry.update(seconds=time.perf_counter() - started, status=False,
                         error=f"{type(error).__name__}: {error}", response=None)
            self._append(entry)
            raise
        entry.update(seconds=time.perf_counter() - started,
                     status=response.get("status") if isinstance(response, dict) else True,
                     response=response)
        if self._fingerprints:
            entry["after"] = self._fingerprint(obj)
        self._append(entry)
        return response

    @staticmethod
    def _fingerprint(obj: Any) -> Optional[str]:
        """Return a hash of an object's contents, or None for something that has none."""
        try:
            return obj.fingerprint()
        except AttributeError:
            return None

    def _append(self, entry: Dict[str, Any]) -> None:
        self._entries.append(entry)
        if self._limit is not None and len(self._entries) > self._limit:
            del self._entries[:-self._limit]

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        return iter(self._entries)

    def __getitem__(self, index):
        return self._entries[index]

    @property
    def entries(self) -> List[Dict[str, Any]]:
        """Every recorded request, oldest first."""
        return list(self._entries)

    def failures(self) -> List[Dict[str, Any]]:
        """Only the entries whose request did not succeed."""
        return [entry for entry in self._entries if not entry.get("status")]

    def touching(self, name: str) -> List[Dict[str, Any]]:
        """Every request that named a given object, in order.

        Args:
            name (str): The `name` of the object to trace.

        Returns:
            List[Dict[str, Any]]: The entries naming it, which is its history.
        """
        return [entry for entry in self._entries if entry.get("object") == name]

    def changed(self) -> List[Dict[str, Any]]:
        """Only the entries whose request left the object different from how it found it.

        Returns:
            List[Dict[str, Any]]: The entries whose recorded fingerprints differ. Empty without
                `fingerprints=True`.
        """
        return [entry for entry in self._entries
                if entry.get("before") is not None and entry.get("before") != entry.get("after")]

    def as_plan(self, skip_failures: bool = True) -> Dict[str, Dict[str, Any]]:
        """Return the recorded session as a pipeline plan.

        Args:
            skip_failures (bool): Leave out requests that failed the first time. Defaults to
                True, since replaying a known failure rarely says anything new.

        Returns:
            Dict[str, Dict[str, Any]]: Steps keyed by name, each waiting for the one before, so
                the order it ran in is the order it runs in again.

        Notes:
            - A session is a plan whose steps have no edges except order, so replaying it is
              running a plan. `Manipulator.replay` does that.
        """
        plan: Dict[str, Dict[str, Any]] = {}
        previous = None
        for position, entry in enumerate(self._entries, start=1):
            if skip_failures and not entry.get("status"):
                continue
            request = entry["request"]
            name = f"{request.get('operation')}_{position}"
            step = {"operation": request.get("operation"),
                    "obj": request.get("obj"),
                    "attributes": dict(request.get("attributes") or {})}
            if request.get("method"):
                step["method"] = request["method"]
            if previous:
                step["after"] = [previous]
            plan[name] = step
            previous = name
        return plan

    def replay(self, manipulator, skip_failures: bool = True) -> List[Any]:
        """Deprecated. Use `manipulator.replay(journal)`.

        Args:
            manipulator (Manipulator): The orchestrator to replay against.
            skip_failures (bool): Leave out requests that failed the first time.

        Returns:
            List[Any]: The responses, in order.

        Notes:
            - Deprecated in 1.3.0, removed in 2.0. The orchestrator runs requests, so replaying
              belongs on it rather than on a record of them.
        """
        import warnings

        warnings.warn("RequestJournal.replay is deprecated; use manipulator.replay(journal)",
                      DeprecationWarning, stacklevel=2)
        return list(manipulator.replay(self, skip_failures=skip_failures).values())

    def clear(self) -> None:
        """Discard every entry."""
        self._entries.clear()
