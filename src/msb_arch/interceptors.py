"""Interceptors the framework ships, because they are the ones everybody writes.

Both are ordinary `Interceptor` implementations with no privileged access: anything here could
have been written by an application, and reading them is the shortest explanation of what the
hook is for.

Neither is registered by default. An orchestrator with no interceptors pays one check per
request, so measurement and recording cost nothing until they are asked for -- which is the
only honest way to ship them in a framework whose other selling point is that it has no
dependencies.
"""
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Iterator, List, Optional

from .utils.logging_setup import logger

__all__ = ["RequestJournal", "RequestMetrics"]


class RequestMetrics:
    """Counts and times requests, per operation.

    What a metrics backend needs, without MSB choosing one. Read `snapshot()` and export it to
    Prometheus, statsd, a log line or a dictionary on a status page; the framework holds the
    numbers and no opinion about where they go.

    Example:
        ```python
        metrics = RequestMetrics()
        manipulator.add_interceptor(metrics)
        ...
        metrics.snapshot()["inspect"]["calls"]
        ```

    Notes:
        - A failed request is counted as a call and as a failure, and its time still counts:
          how long failures take is usually the interesting part.
        - An exception propagates, and is counted, because swallowing it here would change
          what the orchestrator does.
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

    This is the audit trail, and the beginning of provenance. It costs almost nothing to write
    because the framework was already built for it: a request is data rather than a call, and a
    response already reports every method that ran. In a scheduler whose steps are functions,
    an invocation cannot be recorded at all without inventing a parallel description of it.

    From a journal you can answer *what produced this* by reading backwards, and *do that
    again* by replaying forwards.

    Example:
        ```python
        journal = RequestJournal()
        manipulator.add_interceptor(journal)
        ...
        journal.replay(manipulator)          # run the same session again
        ```

    Notes:
        - **Entries hold the request as it ran**, including the live object it named. That is
          what makes in-process replay exact, and what stops a journal from being written to a
          file as it stands: serializing one is the persistence question, which 1.0 leaves to
          the application.
        - `limit` keeps the most recent entries and discards the rest, so a long-running
          process does not accumulate a session without end. Unlimited by default, because
          silently losing an audit trail is worse than growing one.
        - Replay assumes the handlers are deterministic. One that reads the clock, a file or a
          random seed cannot be reconstructed from its request alone.
    """

    def __init__(self, limit: Optional[int] = None):
        """Initialize an empty journal.

        Args:
            limit (Optional[int]): Keep at most this many entries, dropping the oldest.
                Defaults to None, meaning keep everything.
        """
        self._entries: List[Dict[str, Any]] = []
        self._limit = limit

    def __call__(self, request: Dict[str, Any], call_next: Callable) -> Any:
        started = time.perf_counter()
        entry = {
            "operation": request.get("operation"),
            "object": getattr(request.get("obj"), "name", request.get("obj")),
            "attributes": dict(request.get("attributes") or {}),
            "request": request,
        }
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
        self._append(entry)
        return response

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

    def replay(self, manipulator, skip_failures: bool = True) -> List[Any]:
        """Run every recorded request again, in order.

        Args:
            manipulator (Manipulator): The orchestrator to replay against. It may be the one
                that recorded the session or another configured the same way.
            skip_failures (bool): Leave out requests that failed the first time. Defaults to
                True, since replaying a known failure rarely says anything new.

        Returns:
            List[Any]: The responses, in order.

        Notes:
            - Replaying against the orchestrator that holds the journal would record the
              replay as it runs. Remove the journal first, or replay against another.
        """
        responses = []
        for entry in list(self._entries):
            if skip_failures and not entry.get("status"):
                continue
            responses.append(manipulator.process_request(entry["request"]))
        logger.info("Replayed %s request(s)", len(responses))
        return responses

    def clear(self) -> None:
        """Discard every entry."""
        self._entries.clear()
