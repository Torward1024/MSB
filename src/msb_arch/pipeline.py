# pipeline.py
"""A tree of requests: a batch whose steps may feed each other.

`process_request` runs one request. `batch` runs several and reports each. A pipeline is the next
one along and nothing more exotic: several requests where a step may take what an earlier step
produced, so an order exists and the framework works it out rather than the caller.

It follows the same convention as the other two -- **the whole thing is one call, and what it
takes is data**::

    manipulator.pipeline({
        "loaded":  {"operation": "load",    "obj": thing,     "path": "in.json"},
        "checked": {"operation": "inspect", "obj": "@loaded", "get": "value"},
        "written": {"operation": "save",    "obj": "@loaded", "path": "out.json"},
    })

A step is a request, spelled as `process_request` spells one, with three additions:

- `"@name"` anywhere in a step means *what the step called `name` produced*. That is an edge, and
  the edges together are the graph.
- `"after": [...]` waits for a step without taking anything from it, for the edges that are only
  about order -- writing a file and reading it back.
- Anything that is not `operation`, `obj`, `method` or `after` is an attribute, so the common
  case needs no nested `attributes` mapping. Spelling it out still works.

What a pipeline adds over a batch is exactly three things: the order the edges imply, the
substitution of what one step produced into the next, and skipping the branch below a failure
rather than running it against nothing. Everything else is `process_request`, once per step, so
each step meets the interceptors, the journal and the metrics like any other request.

Three decisions worth not re-deciding:

- **A step names its input.** A chain is the one-edge case of a graph rather than a rival syntax.
- **Adaptation between steps is itself a step.** There is deliberately nowhere to put a callable:
  a function is not data, and a plan holding one could not be stored, sent or replayed.
- **Substitution happens before the interceptors**, so an interceptor sees a concrete request and
  a recorded session stays replayable.

What is deliberately not here: recomputing only what changed. That needs to know whether an input
is the same input as last time, which needs identity for mutable objects.
"""
import asyncio
from typing import Any, Dict, List, Optional, Sequence, Set, Union

from .errors import AttributeNotFoundError, DispatchError, NotFoundError, RequestError
from .utils.logging_setup import logger

__all__ = ["PipelineRun"]

#: The keys of a step that are not attributes.
_STRUCTURE = ("operation", "obj", "method", "after", "attributes", "name")

#: Distinguishes "the caller said nothing" from "the caller said None", which mean opposite
#: things: follow the previous step, against operate on the managing object.
_UNSAID = object()


class PipelineRun(dict):
    """What a pipeline produced: the response of every step, by name.

    A `dict` of responses, keyed as the plan keyed its steps -- the shape `batch` already answers
    with -- and with the two things a caller usually wants named rather than dug out.

    Examples:
        >>> outcome = manipulator.pipeline(plan)
        >>> outcome["written"]["status"]
        True
        >>> outcome.output
        {'path': 'out.json'}
    """

    def __init__(self, responses: Dict[str, Any], produced: Dict[str, Any], last: Optional[str]):
        super().__init__(responses)
        self._produced = produced
        self._last = last

    @property
    def output(self) -> Any:
        """What the last step of the plan produced, unwrapped as a facade would unwrap it."""
        return self._produced.get(self._last)

    def of(self, name: str) -> Any:
        """Return what one step produced.

        Args:
            name (str): The step's name.

        Returns:
            Any: Its value, unwrapped as a facade would unwrap it.

        Raises:
            NotFoundError: If no step of that name produced anything.
        """
        if name not in self._produced:
            raise NotFoundError(f"No step named '{name}' produced anything")
        return self._produced[name]

    @property
    def failed(self) -> List[str]:
        """The names of the steps that did not succeed, in the order of the plan."""
        return [name for name, response in self.items() if not response.get("status")]


class _Step:
    """One step of a plan, read out of the data it was written as."""

    def __init__(self, name: str, entry: Dict[str, Any], previous: Optional[str]):
        if not isinstance(entry, dict):
            raise RequestError(f"Step '{name}' is not a request: {entry!r}")
        operation = entry.get("operation")
        if not operation:
            raise RequestError(f"Step '{name}' names no operation")

        self.name = name
        self.operation = operation
        self.method = entry.get("method")
        self.after = [str(waited).lstrip("@") for waited in entry.get("after") or []]
        self.obj = entry["obj"] if "obj" in entry else (f"@{previous}" if previous else None)

        attributes = dict(entry.get("attributes") or {})
        attributes.update({key: value for key, value in entry.items() if key not in _STRUCTURE})
        self.attributes = attributes

    def __repr__(self) -> str:
        return f"_Step('{self.name}', {self.operation})"


class _Plan:
    """The steps of one plan, the graph they imply, and the running of them.

    Notes:
        - Internal. A plan is data and the manipulator is what runs it; this exists so the
          reading, the ordering and the running are one thing rather than three loose functions
          passing a dictionary between them.
    """

    def __init__(self, manipulator: Any, plan: Union[Dict[str, Any], Sequence[Dict[str, Any]]]):
        self._manipulator = manipulator
        self._steps: Dict[str, _Step] = {}

        for name, entry in _entries(plan):
            if name in self._steps:
                raise RequestError(f"Two steps of one plan are called '{name}'")
            previous = next(reversed(self._steps), None) if self._steps else None
            step = _Step(name, entry, previous)
            if step.operation not in manipulator.get_supported_operations():
                raise DispatchError(
                    f"Step '{name}' asks for operation '{step.operation}', which is not "
                    "registered")
            self._steps[name] = step

        if not self._steps:
            raise RequestError("A plan with no steps has nothing to run")
        self._check_references()

    # --- the graph ------------------------------------------------------------------------

    def _check_references(self) -> None:
        """Refuse a plan that refers to a step it does not contain.

        Notes:
            - Checked before anything runs, so a typo in the last step does not surface after the
              first three have already written files.
        """
        for name in self._steps:
            for referred in self.requires(name):
                if referred not in self._steps:
                    raise RequestError(
                        f"Step '{name}' refers to '{referred}', which is not in the plan")

    def requires(self, name: str) -> List[str]:
        """Return the steps one step waits for, directly."""
        step = self._steps[name]
        found = _referenced(step.obj) | _referenced(step.attributes) | set(step.after)
        return sorted(found - {name})

    def order(self) -> List[List[str]]:
        """Return the steps grouped into the stages they can run in.

        Returns:
            List[List[str]]: Each list holds steps that wait for nothing outside the stages
                before it, so everything in one stage may run at the same time. A plain chain
                comes back as one step per stage, which is correct rather than a special case.

        Raises:
            RequestError: If the steps depend on each other in a circle.
        """
        waiting = {name: set(self.requires(name)) for name in self._steps}
        stages: List[List[str]] = []
        done: Set[str] = set()

        while waiting:
            ready = [name for name in self._steps if name in waiting and waiting[name] <= done]
            if not ready:
                raise RequestError(
                    f"Steps {sorted(waiting)} depend on each other in a circle and cannot be "
                    "ordered")
            stages.append(ready)
            done.update(ready)
            for name in ready:
                del waiting[name]
        return stages

    # --- running --------------------------------------------------------------------------

    def run(self, raise_on_error: bool = True) -> PipelineRun:
        """Run every step, each after the ones it waits for."""
        produced: Dict[str, Any] = {}
        responses: Dict[str, Any] = {}
        skipped: Set[str] = set()

        for stage in self.order():
            for name in stage:
                request = self._prepare(name, produced, responses, skipped, raise_on_error)
                if request is None:
                    continue
                responses[name] = self._manipulator.process_request(request)
                self._accept(name, responses[name], produced, skipped, raise_on_error)
        logger.debug("Ran a plan of %s step(s)", len(responses))
        return self._outcome(responses, produced)

    async def arun(self, raise_on_error: bool = True) -> PipelineRun:
        """Run the plan with the independent steps of each stage running at the same time.

        Notes:
            - A stage is what `order` grouped, so everything in one goes onto the executor
              together: a plan of two independent branches costs its slower branch rather than
              both. Stages still follow one another, since a stage exists because its steps need
              the one before.
        """
        produced: Dict[str, Any] = {}
        responses: Dict[str, Any] = {}
        skipped: Set[str] = set()

        for stage in self.order():
            requests = {}
            for name in stage:
                request = self._prepare(name, produced, responses, skipped, raise_on_error)
                if request is not None:
                    requests[name] = request

            gathered = await asyncio.gather(*[self._manipulator.aprocess_request(request)
                                              for request in requests.values()])
            for name, response in zip(requests, gathered):
                responses[name] = response
                self._accept(name, response, produced, skipped, raise_on_error)
        logger.debug("Ran a plan of %s step(s) concurrently", len(responses))
        return self._outcome(responses, produced)

    def _outcome(self, responses: Dict[str, Any], produced: Dict[str, Any]) -> PipelineRun:
        """Put the responses back in the order of the plan, whatever order they ran in."""
        ordered = {name: responses[name] for name in self._steps if name in responses}
        return PipelineRun(ordered, produced, next(reversed(self._steps), None))

    def _prepare(self, name: str, produced: Dict[str, Any], responses: Dict[str, Any],
                 skipped: Set[str], raise_on_error: bool) -> Optional[Dict[str, Any]]:
        """Return the concrete request for a step, or None if it cannot be attempted.

        Notes:
            - Every reference is replaced here, **before** the request is handed over, so the
              interceptor chain only ever sees concrete requests and a journal records something
              that can be replayed.
        """
        blocking = [waited for waited in self.requires(name) if waited in skipped]
        if blocking:
            logger.debug("Skipped step '%s': %s produced nothing", name, blocking)
            responses[name] = {
                "status": False, "object": None, "method": None, "result": None, "skipped": True,
                "error": f"Skipped: {', '.join(blocking)} did not produce a value"}
            skipped.add(name)
            return None

        step = self._steps[name]
        try:
            obj = _substitute(step.obj, produced)
            if _is_reference(step.obj) and obj is None:
                raise RequestError(
                    f"Step '{name}' was to run on what '{step.obj[1:]}' produced, and it produced "
                    "nothing. An operation that applies methods to an object -- configure, "
                    "inspect -- reports what the methods returned rather than handing the object "
                    "on, so name the object this step runs on.")
            request = {"operation": step.operation, "obj": obj,
                       "attributes": _substitute(step.attributes, produced)}
            if step.method:
                request["method"] = step.method
            return request
        except RequestError as e:
            responses[name] = {"status": False, "object": None, "method": None, "result": None,
                               "error": str(e), "error_type": type(e).__name__}
            self._accept(name, responses[name], produced, skipped, raise_on_error)
            return None

    def _accept(self, name: str, response: Dict[str, Any], produced: Dict[str, Any],
                skipped: Set[str], raise_on_error: bool) -> None:
        """Record what a step produced, or deal with its failure.

        Raises:
            Exception: If it failed and the caller asked for failures to raise. The kind is the
                step's own, since that is what a caller would have caught calling the facade
                directly; only the message gains the step's name.
        """
        if response.get("status"):
            produced[name] = self._manipulator._unwrap_single(response["result"])
            return

        message = f"Step '{name}' failed: {response.get('error')}"
        if raise_on_error:
            raise self._manipulator._as_error(dict(response, error=message))
        logger.warning("%s", message)
        skipped.add(name)


# --- reading the data ---------------------------------------------------------------------------

def _entries(plan: Union[Dict[str, Any], Sequence[Dict[str, Any]]]):
    """Yield `(name, step)` from either shape a plan may be written in.

    Notes:
        - A mapping keyed by name, or a sequence whose steps may carry their own `name` -- the two
          shapes `batch` already accepts, for the same reason: one reads better when the names
          matter and the other when the order does.
    """
    if isinstance(plan, dict):
        yield from plan.items()
        return
    if isinstance(plan, (list, tuple)):
        for position, entry in enumerate(plan):
            name = entry.get("name") if isinstance(entry, dict) else None
            yield name or f"step_{position + 1}", entry
        return
    raise RequestError(
        f"A plan is a mapping of steps or a sequence of them, not {type(plan).__name__}")


def _is_reference(value: Any) -> bool:
    """Report whether a value refers to another step."""
    return isinstance(value, str) and value.startswith("@") and not value.startswith("@@")


def _referenced(value: Any) -> Set[str]:
    """Return the names of every step referred to anywhere inside a value."""
    if _is_reference(value):
        return {value[1:].split(".", 1)[0]}
    if isinstance(value, dict):
        return set().union(*(_referenced(item) for item in value.values())) if value else set()
    if isinstance(value, (list, tuple, set)):
        return set().union(*(_referenced(item) for item in value)) if value else set()
    return set()


def _substitute(value: Any, produced: Dict[str, Any]) -> Any:
    """Replace every reference with what the step it names produced.

    Notes:
        - Recursive, so a reference reaches wherever a request can hold one -- an argument, an
          item of a list, a value in a mapping.
        - `"@@literal"` is how a string that really does begin with `@` is written. Without an
          escape, a framework convention would quietly eat a caller's data.
        - `"@step.method"` names one of several method results. A step that ran exactly one method
          produces that method's value, which is what a facade returns and is right almost always;
          this is for the rest.
    """
    if isinstance(value, str):
        if value.startswith("@@"):
            return value[1:]
        if not value.startswith("@"):
            return value
        name, _, key = value[1:].partition(".")
        found = produced.get(name)
        if not key:
            return found
        try:
            narrowed = found[key]
        except (KeyError, IndexError, TypeError) as e:
            raise RequestError(f"Step '{name}' produced nothing under '{key}'") from e
        return narrowed.get("result") if isinstance(narrowed, dict) and "result" in narrowed \
            else narrowed
    if isinstance(value, dict):
        return {key: _substitute(item, produced) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, produced) for item in value]
    if isinstance(value, tuple):
        return tuple(_substitute(item, produced) for item in value)
    return value


# --- sugar, and nothing but ----------------------------------------------------------------------

class _Draft:
    """Writes a plan by calling the operations, for a caller who would rather not type a mapping.

    Obtained from `manipulator.pipeline()` with no plan. It is **purely a way of producing the
    mapping above**: `plan()` hands back exactly what could have been written by hand, and `run()`
    passes it to `manipulator.pipeline(plan)` like any other caller. There is one execution path
    and this is not it -- which is what keeps the convention the thing and this a convenience.

    Examples:
        >>> draft = manipulator.pipeline()
        >>> loaded = draft.load(thing, path="in.json")
        >>> draft.save(loaded, path="out.json")
        '@save'
        >>> draft.plan()["save"]["obj"]
        '@load'
    """

    def __init__(self, manipulator: Any, name: Optional[str] = None):
        self._manipulator = manipulator
        self._name = name or "plan"
        self._plan: Dict[str, Dict[str, Any]] = {}

    def __getattr__(self, operation: str):
        """Return a recorder for a registered operation, so a draft reads like the facades.

        Raises:
            AttributeNotFoundError: If nothing of that name is registered. It derives from
                `AttributeError`, which `__getattr__` has to raise or `hasattr`, copying and
                pickling all misread a missing operation as something worse.
        """
        if operation.startswith("_"):
            raise AttributeNotFoundError(operation)
        manipulator = self.__dict__.get("_manipulator")
        if manipulator is None or operation not in manipulator.get_supported_operations():
            raise AttributeNotFoundError(
                f"No operation named '{operation}' is registered with this manipulator")

        def record(obj: Any = _UNSAID, method: Optional[str] = None,
                   after: Optional[List[str]] = None, step: Optional[str] = None,
                   **attributes) -> str:
            return self.add(operation, obj, method=method, after=after, step=step, **attributes)

        record.__name__ = operation
        record.__doc__ = (f"Write a '{operation}' step into the plan and return a reference to "
                          f"it. Same arguments as the manipulator's facade for it.")
        return record

    def add(self, operation: str, obj: Any = _UNSAID, method: Optional[str] = None,
            after: Optional[List[str]] = None, step: Optional[str] = None, **attributes) -> str:
        """Write one step, and for an operation whose name this class already uses, the only way.

        Args:
            operation (str): The operation to request.
            obj (Any): What to run it on. Omitted leaves it out of the plan, which means the step
                before; `None` means the managing object; a reference means that step's value.
            method (Optional[str]): A specific handler, as for any facade.
            after (Optional[List[str]]): References to wait for without taking anything from.
            step (Optional[str]): What to call this step. Defaults to the operation, numbered if
                that name is taken.
            **attributes: The rest of the request.

        Returns:
            str: A reference to the step -- `"@load"` -- to pass wherever its value is wanted.

        Raises:
            DispatchError: If no such operation is registered. Refused while drafting, because a
                plan that cannot run should not be writable.
        """
        if operation not in self._manipulator.get_supported_operations():
            raise DispatchError(f"No operation named '{operation}' is registered")

        name = step or self._unique(operation)
        if name in self._plan:
            raise RequestError(f"Two steps of one plan are called '{name}'")

        entry: Dict[str, Any] = {"operation": operation}
        if obj is not _UNSAID:
            entry["obj"] = obj
        if method:
            entry["method"] = method
        if after:
            entry["after"] = [str(reference).lstrip("@") for reference in after]
        entry.update(attributes)

        self._plan[name] = entry
        return f"@{name}"

    def _unique(self, operation: str) -> str:
        """Return a step name not yet used, numbering repeats of one operation."""
        if operation not in self._plan:
            return operation
        count = 2
        while f"{operation}_{count}" in self._plan:
            count += 1
        return f"{operation}_{count}"

    def plan(self) -> Dict[str, Dict[str, Any]]:
        """Return the plan this drafted: exactly what could have been written by hand."""
        return dict(self._plan)

    def run(self, raise_on_error: bool = True, concurrent: bool = False) -> PipelineRun:
        """Hand the drafted plan to the manipulator, like any other caller."""
        return self._manipulator.pipeline(self.plan(), raise_on_error=raise_on_error,
                                          concurrent=concurrent)

    def __len__(self) -> int:
        return len(self._plan)

    def __repr__(self) -> str:
        return (f"<draft plan '{self._name}', {len(self._plan)} step(s), "
                f"for {type(self._manipulator).__name__}>")
