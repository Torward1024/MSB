# pipeline.py
"""Several requests that feed each other, written as if they were one.

A pipeline is a tree of requests. Nothing here runs anything: every step is an ordinary request,
handed to `process_request` exactly as a single call would be, and what this adds is the three
things a batch cannot say -- which step needs which, what one step takes from another, and what
to do with the rest when one fails.

It is reached through the manipulator like everything else. `manipulator.pipeline()` gives an
empty one to build; `manipulator.pipeline(plan=...)` runs one that arrived as data.

The sugar and the graph are the same object. Writing

    pipe = manipulator.pipeline()
    loaded = pipe.load(thing, path="in.json")
    pipe.configure(loaded, set_value=7)
    pipe.save(path="out.json")

reads like three ordinary facade calls, because it is three ordinary facade calls -- the same
names, the same arguments, on the pipeline instead of the manipulator. What it produces is an
explicit graph: each step records what it was given, a step passed as an argument is an edge, and
a step given nothing follows the one before it. Convenience at the front, no ambiguity behind it.

Three decisions worth not re-deciding, and the reasons:

- **A step names its input.** The chain above is the one-edge case of a graph rather than a rival
  syntax to it, so ordering, branching and running two branches at once all fall out of the same
  record.
- **Adaptation between steps is itself a step.** There is deliberately no way to drop a callable
  between two steps: a function is not data, and a pipeline holding one could not be stored,
  sent, journalled or replayed. A conversion is an ordinary `Super` like anything else.
- **Substitution happens before the interceptors.** By the time a request reaches the chain it is
  concrete, so an interceptor never sees a placeholder and a recorded session stays replayable.

What is deliberately *not* here yet: recomputing only what changed. That needs to know whether an
input is the same input as last time, which needs identity for mutable objects -- and guessing at
that is how a cache starts returning yesterday's answer.
"""
import asyncio
from typing import Any, Dict, List, Optional, Set

from .errors import (AttributeNotFoundError, DispatchError, NotFoundError,
                     RequestError, SerializationError)
from .utils.logging_setup import logger

__all__ = ["Pipeline", "PipelineRun", "Step"]

#: Distinguishes "the caller passed nothing" from "the caller passed None", which mean opposite
#: things here: follow the previous step, against operate on the managing object.
_UNSAID = object()


class Step:
    """One recorded request, and a reference to what it will produce.

    A step is returned by every pipeline facade and is worth keeping in a variable: passing it to
    a later step is how an edge is written.

    Args:
        name (str): What this step is called within its pipeline.
        operation (str): The operation to request.
        obj (Any): What to run it on -- another `Step`, an object, or None for the manipulator's
            managing object.
        attributes (Dict[str, Any]): The rest of the request, which may itself contain steps.

    Examples:
        >>> loaded = pipe.load(path="in.json")
        >>> pipe.inspect(loaded, get_all=None)
        Step('inspect', on 'load')
    """

    def __init__(self, name: str, operation: str, obj: Any, attributes: Dict[str, Any]):
        self.name = name
        self.operation = operation
        self.obj = obj
        self.attributes = attributes
        self.key: Optional[str] = None
        self.after: List["Step"] = []

    def once(self, *steps: "Step") -> "Step":
        """Wait for these steps without taking anything from them.

        Args:
            *steps (Step): The steps that must have run first.

        Returns:
            Step: This step.

        Notes:
            - Most edges are written by passing a step where a value goes, which says both *when*
              and *what*. Some are only about when: writing a file and then reading it back needs
              an order and takes nothing across. Without a way to say that, the two would look
              independent and could run at the same time -- which is the sort of bug that passes
              a hundred times and fails on a busy machine.

        Examples:
            >>> written = pipe.save(path="out.json")
            >>> pipe.load(thing, path="out.json").once(written)
            Step('load', on 'Thing')
        """
        self.after.extend(steps)
        return self

    def named(self, name: str) -> "Step":
        """Rename this step, and return it so a call can be renamed where it is written.

        Args:
            name (str): The new name. Names are how steps are referred to in a stored plan and
                in a report, so a meaningful one is worth the four characters.

        Returns:
            Step: This step.

        Examples:
            >>> pipe.inspect(get_all=None).named("before")
            Step('before', on 'load')
        """
        self.name = name
        return self

    def __getitem__(self, key: str) -> "Step":
        """Refer to one method's result rather than to the whole of what a step produced.

        Args:
            key (str): The method name whose result is wanted.

        Returns:
            Step: A reference to this step, narrowed. The step itself is unchanged, so one step
                can be read in several ways.

        Notes:
            - A step that ran exactly one method produces that method's value, which is what a
              facade returns and is right almost always. This is for the rest: a step that ran
              four methods produces all four, and the next step wants one of them.
        """
        narrowed = Step(self.name, self.operation, self.obj, self.attributes)
        narrowed.key = key
        narrowed.after = self.after
        return narrowed

    def __repr__(self) -> str:
        on = f"'{self.obj.name}'" if isinstance(self.obj, Step) else type(self.obj).__name__
        return f"Step('{self.name}', on {on})"


class PipelineRun(dict):
    """What a pipeline produced: the response of every step, by name.

    A `dict` of responses, so nothing new has to be learned to read one, with the two things a
    caller usually wants named rather than dug out.

    Examples:
        >>> outcome = pipe.run()
        >>> outcome.output
        {'path': 'out.json'}
        >>> outcome["load"]["status"]
        True
    """

    def __init__(self, responses: Dict[str, Any], produced: Dict[str, Any], last: Optional[str]):
        super().__init__(responses)
        self._produced = produced
        self._last = last

    @property
    def output(self) -> Any:
        """What the last step produced, unwrapped as a facade would unwrap it."""
        return self._produced.get(self._last)

    def of(self, name: str) -> Any:
        """Return what one step produced.

        Args:
            name (str): The step's name.

        Returns:
            Any: Its value, unwrapped as a facade would unwrap it.

        Raises:
            NotFoundError: If no step of that name ran.
        """
        if name not in self._produced:
            raise NotFoundError(f"No step named '{name}' produced anything")
        return self._produced[name]

    @property
    def failed(self) -> List[str]:
        """The names of the steps that did not succeed, in the order they were attempted."""
        return [name for name, response in self.items() if not response.get("status")]


class Pipeline:
    """Several requests that feed each other, built by calling the operations by name.

    Args:
        manipulator (Manipulator): The orchestrator whose operations may be requested, and which
            runs every step. Built through `manipulator.pipeline()` rather than directly: the
            manipulator is the way in to everything, and a pipeline is no exception.
        name (Optional[str]): What to call this pipeline in a log or a stored plan.

    Notes:
        - **Every registered operation is a method here**, with the same signature as the
          manipulator's facade for it. The difference is that it records a step rather than
          running one, so the way to write a pipeline is to write the calls you would have made.
        - A step given no object follows the one before it. A step given a `Step` follows that
          one, wherever it was. A step given `None` explicitly operates on the managing object,
          which is why "given nothing" and "given None" have to mean different things.
        - Names on this class -- `run`, `add`, `order` and the rest -- win over an operation of
          the same name. An operation called `run` is still reachable through `add`.

    Examples:
        >>> pipe = manipulator.pipeline()
        >>> loaded = pipe.load(thing, path="in.json")
        >>> pipe.configure(loaded, set_value=7)
        Step('configure', on 'load')
        >>> pipe.save(path="out.json")
        Step('save', on 'configure')
        >>> pipe.run().output
        {'path': 'out.json'}
    """

    def __init__(self, manipulator: Any, name: Optional[str] = None):
        self._manipulator = manipulator
        self.name = name or "pipeline"
        self._steps: List[Step] = []

    # --- building -------------------------------------------------------------------------

    def __getattr__(self, operation: str):
        """Return a recorder for a registered operation, so facades read the same here.

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

        def record(obj: Any = _UNSAID, method: Optional[str] = None, **attributes) -> Step:
            return self.add(operation, obj, method=method, **attributes)

        record.__name__ = operation
        record.__doc__ = (f"Record a '{operation}' step. Same arguments as the manipulator's "
                          f"facade; returns the Step rather than running it.")
        return record

    def add(self, operation: str, obj: Any = _UNSAID, method: Optional[str] = None,
            **attributes) -> Step:
        """Record a step explicitly, for an operation whose name this class already uses.

        Args:
            operation (str): The operation to request.
            obj (Any): What to run it on. Omitted means the previous step; `None` means the
                manipulator's managing object; a `Step` means that step's output.
            method (Optional[str]): A specific handler, as for any facade.
            **attributes: The rest of the request. A `Step` anywhere in here is an edge too.

        Returns:
            Step: The recorded step.

        Raises:
            DispatchError: If no such operation is registered. Refused here rather than at run
                time, because a plan that cannot run should not be buildable.
        """
        if operation not in self._manipulator.get_supported_operations():
            raise DispatchError(f"No operation named '{operation}' is registered")
        if obj is _UNSAID:
            obj = self._steps[-1] if self._steps else None
        if method:
            attributes = dict(attributes, method=method)

        step = Step(self._unique(operation), operation, obj, attributes)
        self._steps.append(step)
        logger.debug("Recorded step '%s' in pipeline '%s'", step.name, self.name)
        return step

    def _unique(self, operation: str) -> str:
        """Return a step name not yet used, numbering repeats of one operation."""
        taken = {step.name for step in self._steps}
        if operation not in taken:
            return operation
        count = 2
        while f"{operation}_{count}" in taken:
            count += 1
        return f"{operation}_{count}"

    def __getitem__(self, name: str) -> Step:
        """Return a recorded step by name, for referring to one built earlier."""
        for step in self._steps:
            if step.name == name:
                return step
        raise NotFoundError(f"No step named '{name}' in pipeline '{self.name}'")

    def __len__(self) -> int:
        return len(self._steps)

    def __repr__(self) -> str:
        return f"Pipeline('{self.name}', {len(self._steps)} step(s))"

    def steps(self) -> List[Step]:
        """Return the steps in the order they were written."""
        return list(self._steps)

    # --- the graph ------------------------------------------------------------------------

    def requires(self, name: str) -> List[str]:
        """Return the steps one step waits for, directly.

        Args:
            name (str): The step to ask about.

        Returns:
            List[str]: Sorted names. Empty for a step that starts a branch.
        """
        step = self[name]
        found = _references(step.obj) | _references(step.attributes) | set(step.after)
        return sorted({referred.name for referred in found})

    def order(self) -> List[List[str]]:
        """Return the steps grouped into the stages they can run in.

        Returns:
            List[List[str]]: Each list holds steps that depend on nothing outside the stages
                before it, so everything in one stage may run at the same time. A plain sequence
                comes back as one step per stage, which is correct rather than a special case.

        Raises:
            RequestError: If the steps cannot be ordered because they depend on each other in a
                circle. Unreachable while building -- a step can only refer to an earlier one --
                and reachable through a plan that was written or edited by hand.
        """
        waiting = {step.name: set(self.requires(step.name)) for step in self._steps}
        stages: List[List[str]] = []
        done: Set[str] = set()

        while waiting:
            ready = sorted(name for name, needs in waiting.items() if needs <= done)
            if not ready:
                raise RequestError(
                    f"Steps {sorted(waiting)} of pipeline '{self.name}' depend on each other in "
                    "a circle and cannot be ordered")
            stages.append(ready)
            done.update(ready)
            for name in ready:
                del waiting[name]
        return stages

    # --- running --------------------------------------------------------------------------

    def run(self, raise_on_error: bool = True) -> PipelineRun:
        """Run every step, each after the ones it waits for.

        Args:
            raise_on_error (bool): If True, the first failure raises. If False, the failure is
                recorded, every step that depended on it is skipped, and independent branches
                are still run.

        Returns:
            PipelineRun: The response of every step, by name.

        Raises:
            Exception: If `raise_on_error` and a step fails, of whatever kind the step's failure
                was, with the step named in the message.
        """
        produced: Dict[str, Any] = {}
        responses: Dict[str, Any] = {}
        skipped: Set[str] = set()

        for stage in self.order():
            for name in stage:
                step = self[name]
                if self._blocked(step, skipped):
                    responses[name] = self._skip(step, skipped)
                    skipped.add(name)
                    continue
                try:
                    request = self._request(step, produced)
                except RequestError as e:
                    responses[name] = self._refused(step, e)
                    self._accept(step, responses[name], produced, skipped, raise_on_error)
                    continue
                response = self._manipulator.process_request(request)
                responses[name] = response
                self._accept(step, response, produced, skipped, raise_on_error)
        logger.debug("Pipeline '%s' ran %s step(s)", self.name, len(responses))
        return PipelineRun(responses, produced, self._steps[-1].name if self._steps else None)

    async def arun(self, raise_on_error: bool = True) -> PipelineRun:
        """Run the pipeline with the independent steps of each stage running at the same time.

        Args:
            raise_on_error (bool): As for `run`.

        Returns:
            PipelineRun: The response of every step, by name.

        Notes:
            - A stage is what `order` grouped: steps that wait for nothing outside the stages
              before them. Everything in a stage goes onto the executor together, so a pipeline
              of two independent branches takes as long as its slower branch rather than as long
              as both.
            - Stages still run one after another, because a stage exists precisely because its
              steps need the previous one.
        """
        produced: Dict[str, Any] = {}
        responses: Dict[str, Any] = {}
        skipped: Set[str] = set()

        for stage in self.order():
            runnable = [name for name in stage if not self._blocked(self[name], skipped)]
            for name in stage:
                if name not in runnable:
                    responses[name] = self._skip(self[name], skipped)
                    skipped.add(name)

            requests, attempted = {}, []
            for name in runnable:
                try:
                    requests[name] = self._request(self[name], produced)
                    attempted.append(name)
                except RequestError as e:
                    responses[name] = self._refused(self[name], e)
                    self._accept(self[name], responses[name], produced, skipped, raise_on_error)

            gathered = await asyncio.gather(*[
                self._manipulator.aprocess_request(requests[name]) for name in attempted])

            for name, response in zip(attempted, gathered):
                responses[name] = response
                self._accept(self[name], response, produced, skipped, raise_on_error)
        logger.debug("Pipeline '%s' ran %s step(s) asynchronously", self.name, len(responses))
        return PipelineRun(responses, produced, self._steps[-1].name if self._steps else None)

    @staticmethod
    def _refused(step: Step, why: Exception) -> Dict[str, Any]:
        """Return the response for a step that could not even be turned into a request.

        Notes:
            - A step whose references cannot be resolved has failed as surely as one whose
              handler raised, and a caller who asked for failures to be reported rather than
              raised meant that one too.
        """
        return {"status": False, "object": None, "method": None, "result": None,
                "error": str(why), "error_type": type(why).__name__}

    def _blocked(self, step: Step, skipped: Set[str]) -> bool:
        """Report whether anything this step waits for did not produce a value."""
        return any(name in skipped for name in self.requires(step.name))

    def _skip(self, step: Step, skipped: Set[str]) -> Dict[str, Any]:
        """Return the response recorded for a step that could not be attempted."""
        blocking = sorted(name for name in self.requires(step.name) if name in skipped)
        logger.debug("Skipped step '%s': %s did not produce a value", step.name, blocking)
        return {"status": False, "object": None, "method": None, "result": None, "skipped": True,
                "error": f"Skipped: {', '.join(blocking)} did not produce a value"}

    def _accept(self, step: Step, response: Dict[str, Any], produced: Dict[str, Any],
                skipped: Set[str], raise_on_error: bool) -> bool:
        """Record what a step produced, or deal with its failure.

        Returns:
            bool: True if the step succeeded.

        Raises:
            Exception: If it failed and the caller asked for failures to raise. The kind is the
                step's own, since that is what a caller would have caught calling the facade
                directly; only the message gains the step's name.
        """
        if response.get("status"):
            produced[step.name] = self._manipulator._unwrap_single(response["result"])
            return True

        message = f"Step '{step.name}' of pipeline '{self.name}' failed: {response.get('error')}"
        if raise_on_error:
            raise self._manipulator._as_error(dict(response, error=message))
        logger.warning("%s", message)
        skipped.add(step.name)
        return False

    def _request(self, step: Step, produced: Dict[str, Any]) -> Dict[str, Any]:
        """Turn a recorded step into a concrete request.

        Notes:
            - Every reference is replaced here, **before** the request is handed over, so the
              interceptor chain only ever sees concrete requests and a journal records something
              that can be replayed.
        """
        obj = _substitute(step.obj, produced)
        if isinstance(step.obj, Step) and obj is None:
            raise RequestError(
                f"Step '{step.name}' was to run on what '{step.obj.name}' produced, and it "
                "produced nothing. An operation that applies methods to an object -- configure, "
                "inspect -- reports what the methods returned rather than handing the object on, "
                "so name the object this step runs on.")
        return {"operation": step.operation,
                "obj": obj,
                "attributes": _substitute(step.attributes, produced)}

    # --- as data --------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return the plan as data, so it can be stored, sent or replayed.

        Returns:
            Dict[str, Any]: `{"name": str, "steps": [{"name", "operation", "obj", "attributes"}]}`,
                where a reference to another step appears as `{"$step": name}`.

        Raises:
            SerializationError: If a step holds something that is not data -- a live object, a
                callable. A pipeline that cannot be written down is one that cannot be replayed,
                and finding that out at the moment of saving is better than at the moment of
                reading.
        """
        import json

        plan = {"name": self.name,
                "steps": [{"name": step.name,
                           "operation": step.operation,
                           "obj": _as_data(step.obj),
                           "attributes": _as_data(step.attributes),
                           "after": [waited.name for waited in step.after]}
                          for step in self._steps]}
        try:
            json.dumps(plan)
        except (TypeError, ValueError) as e:
            raise SerializationError(
                f"Pipeline '{self.name}' holds something that is not data: {e}") from e
        return plan

    @classmethod
    def from_dict(cls, manipulator: Any, plan: Dict[str, Any]) -> "Pipeline":
        """Rebuild a pipeline from a stored plan.

        Args:
            manipulator (Manipulator): The orchestrator to run against. A plan is a plan, not a
                binding: the same one can be replayed against a different model.
            plan (Dict[str, Any]): What `to_dict` produced.

        Returns:
            Pipeline: The rebuilt pipeline.

        Raises:
            RequestError: If the plan is not the shape `to_dict` produces, or refers to a step
                that is not in it.
        """
        if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list):
            raise RequestError("A pipeline plan needs a 'steps' list")

        pipeline = cls(manipulator, plan.get("name"))
        by_name: Dict[str, Step] = {}
        for entry in plan["steps"]:
            if not isinstance(entry, dict) or "operation" not in entry:
                raise RequestError(f"Step {entry!r} has no operation")
            step = Step(entry.get("name") or entry["operation"], entry["operation"],
                        _from_data(entry.get("obj"), by_name, pipeline),
                        _from_data(entry.get("attributes") or {}, by_name, pipeline))
            for waited in entry.get("after") or []:
                if waited not in by_name:
                    raise RequestError(f"Step '{step.name}' waits for '{waited}', "
                                       "which is not in the plan")
                step.after.append(by_name[waited])
            pipeline._steps.append(step)
            by_name[step.name] = step
        return pipeline


# --- references, resolved and recorded ------------------------------------------------------

def _references(value: Any) -> Set[Step]:
    """Return every step referred to anywhere inside a value."""
    if isinstance(value, Step):
        return {value}
    if isinstance(value, dict):
        return set().union(*(_references(item) for item in value.values())) if value else set()
    if isinstance(value, (list, tuple, set)):
        return set().union(*(_references(item) for item in value)) if value else set()
    return set()


def _substitute(value: Any, produced: Dict[str, Any]) -> Any:
    """Replace every step reference with what that step produced.

    Notes:
        - Recursive through dictionaries and sequences, so a reference reaches wherever a
          request can hold one -- an argument, an item of a list, a value in a mapping.
    """
    if isinstance(value, Step):
        found = produced.get(value.name)
        if value.key is not None:
            try:
                narrowed = found[value.key]
            except (KeyError, IndexError, TypeError) as e:
                raise RequestError(
                    f"Step '{value.name}' produced nothing under '{value.key}'") from e
            return narrowed.get("result") if isinstance(narrowed, dict) and "result" in narrowed \
                else narrowed
        return found
    if isinstance(value, dict):
        return {key: _substitute(item, produced) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, produced) for item in value]
    if isinstance(value, tuple):
        return tuple(_substitute(item, produced) for item in value)
    return value


def _as_data(value: Any) -> Any:
    """Turn recorded arguments into something storable, references and objects included.

    Notes:
        - A modelled object is written as its own data under its type's name. A plan naming a
          live object is the ordinary case -- the first step of most pipelines runs on something
          -- so a plan that refused to hold one would be a plan that could rarely be stored.
    """
    from .base.serializable import Serializable

    if isinstance(value, Step):
        return {"$step": value.name} if value.key is None else {"$step": value.name,
                                                                "$key": value.key}
    if isinstance(value, Serializable):
        return {"$type": type(value).__name__, "$data": value.to_dict()}
    if isinstance(value, dict):
        return {key: _as_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_data(item) for item in value]
    return value


def _named_type(name: str) -> type:
    """Return the modelled type of that name, refusing to guess between two.

    Raises:
        RequestError: If nothing of that name has been imported, or more than one thing has.
            Only `Serializable` subclasses are searched -- a name that crossed a boundary
            selects among the model's own types and nothing else.
    """
    from .base.serializable import Serializable

    found, pending = [], [Serializable]
    while pending:
        candidate = pending.pop()
        if candidate.__name__ == name and candidate not in found:
            found.append(candidate)
        pending.extend(candidate.__subclasses__())

    if not found:
        raise RequestError(f"A plan names the type '{name}', which is not imported here")
    if len(found) > 1:
        raise RequestError(
            f"A plan names the type '{name}', and {len(found)} imported types are called that: "
            f"{', '.join(sorted(found_type.__module__ for found_type in found))}")
    return found[0]


def _from_data(value: Any, by_name: Dict[str, Step], pipeline: Pipeline) -> Any:
    """Turn stored arguments back into recorded ones, references and objects included."""
    if isinstance(value, dict) and "$step" in value:
        referred = by_name.get(value["$step"])
        if referred is None:
            raise RequestError(f"A step refers to '{value['$step']}', which is not in the plan")
        return referred[value["$key"]] if "$key" in value else referred
    if isinstance(value, dict) and "$type" in value:
        return _named_type(value["$type"]).from_dict(value.get("$data") or {})
    if isinstance(value, dict):
        return {key: _from_data(item, by_name, pipeline) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_data(item, by_name, pipeline) for item in value]
    return value
