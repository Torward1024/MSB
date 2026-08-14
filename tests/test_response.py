"""One response type, so a caller never unwraps two shapes.

Reported from downstream: a facade answered with a value when `raise_on_error` was left alone
and with the whole response when it was not, so every call site that wanted the second grew

    result = response["result"] if isinstance(response, dict) and "status" in response else response

That line is the symptom. `Response.value` is the fix: the same unwrapping the facade does,
available on the response itself.
"""
import json

import pytest

from msb_arch import BaseEntity, Manipulator, Response, Super, errors


class Part(BaseEntity):
    price: float

    def get_price(self) -> float:
        return self.price

    def set_price(self, value: float) -> bool:
        self.price = value
        return True


class Bench(Manipulator):
    pass


@pytest.fixture
def part():
    return Part(name="bolt", price=4.5)


@pytest.fixture
def bench(part):
    return Bench(base_classes=[Part])


# --- one shape ---------------------------------------------------------------------------

def test_a_response_carries_its_own_value(bench, part):
    answer = bench.inspect(part, get_price=None, raise_on_error=False)

    assert answer.ok is True
    assert answer.value == 4.5


def test_the_value_is_what_the_facade_would_have_returned(bench, part):
    """The two must not be able to disagree: they call the same function."""
    raised = bench.inspect(part, get_price=None)
    reported = bench.inspect(part, get_price=None, raise_on_error=False)

    assert raised == reported.value


def test_several_methods_come_back_whole(bench, part):
    """Unwrapping is for the one-method case; more than one is a mapping either way."""
    answer = bench.inspect(part, get_price=None, get="name", raise_on_error=False)

    assert set(answer.value) == {"get_price", "get"}
    assert answer.value["get_price"]["result"] == 4.5


def test_a_failure_says_so_without_raising(bench, part):
    answer = bench.configure(part, no_such_method=None, raise_on_error=False)

    assert answer.ok is False
    assert answer.value is None
    assert answer.error_type == "HandlerError"
    assert "no_such_method" in answer.error


def test_it_is_still_a_dictionary(bench, part):
    """A response is data: it is logged, journalled and sent over a wire."""
    answer = bench.inspect(part, get_price=None, raise_on_error=False)

    assert isinstance(answer, dict)
    assert answer["status"] is True
    assert json.loads(json.dumps({k: v for k, v in answer.items() if k != "result"}))


def test_raise_if_failed_raises_the_kind_that_failed(bench, part, tmp_path):
    answer = bench.load(part, path=str(tmp_path / "absent.json"), raise_on_error=False)

    with pytest.raises(errors.NotFoundError):
        answer.raise_if_failed()


def test_raise_if_failed_returns_a_good_one_for_chaining(bench, part):
    answer = bench.inspect(part, get_price=None, raise_on_error=False)

    assert answer.raise_if_failed().value == 4.5


# --- everywhere, not only the facade ------------------------------------------------------

def test_process_request_answers_with_one(bench, part):
    answer = bench.process_request({"operation": "inspect", "obj": part,
                                    "attributes": {"get_price": None}})

    assert isinstance(answer, Response)
    assert answer.value == 4.5


def test_every_batch_entry_does(bench, part):
    responses = bench.batch([{"operation": "inspect", "obj": part,
                              "attributes": {"get_price": None}}])

    assert all(isinstance(entry, Response) for entry in responses.values())
    assert responses["0"].value == 4.5


def test_every_pipeline_step_does(bench, part):
    outcome = bench.pipeline({"read": {"operation": "inspect", "obj": part, "get_price": None}})

    assert isinstance(outcome["read"], Response)
    assert outcome["read"].value == 4.5


def test_a_skipped_step_does_too(bench, part, tmp_path):
    """The one that was still a bare dict, so a caller reading .ok on it crashed."""
    outcome = bench.pipeline({
        "missing": {"operation": "load", "obj": part, "path": str(tmp_path / "absent.json")},
        "below": {"operation": "inspect", "obj": "@missing", "get_price": None},
    }, raise_on_error=False)

    assert isinstance(outcome["below"], Response)
    assert outcome["below"].ok is False
    assert outcome["below"]["skipped"] is True


def test_a_response_from_a_refused_request_does(bench, part):
    """An interceptor may answer instead of the handler; what it returns is still read as a
    response by whoever called."""
    def refuse(request, call_next):
        return Response({"status": False, "object": None, "method": None, "result": None,
                         "error": "not allowed", "error_type": "RequestError"})

    bench.add_interceptor(refuse)
    answer = bench.inspect(part, get_price=None, raise_on_error=False)

    assert answer.ok is False and answer.value is None
    assert answer.error == "not allowed"


def test_reading_it_by_hand_is_not_the_same_answer(bench, part):
    """Why `.value` exists rather than a note in the documentation.

    The line every caller downstream had written -- take `result` if this looks like a
    response -- gives the raw mapping, not the value the facade would have returned. The two
    were only the same for a request naming several methods, which is the uncommon case.
    """
    answer = bench.inspect(part, get_price=None, raise_on_error=False)
    by_hand = answer["result"] if isinstance(answer, dict) and "status" in answer else answer

    assert by_hand == {"get_price": {"status": True, "result": 4.5}}
    assert answer.value == 4.5
    assert by_hand != answer.value


def test_the_declared_shape_is_the_shape_that_ships(bench, part):
    """`ResponseData` is a claim about the protocol, so it is checked against a real response.

    A TypedDict is not enforced at runtime; nothing would notice it drifting from what a request
    actually produces. This is what notices.
    """
    from msb_arch import ResponseData

    declared = ResponseData.__required_keys__ | ResponseData.__optional_keys__

    good = bench.inspect(part, get_price=None, raise_on_error=False)
    assert set(good) <= declared, f"keys nothing declares: {set(good) - declared}"
    assert ResponseData.__required_keys__ <= set(good)

    failed = bench.configure(part, no_such_method=None, raise_on_error=False)
    assert set(failed) <= declared, f"keys nothing declares: {set(failed) - declared}"
    assert ResponseData.__required_keys__ <= set(failed)
    assert "error" in failed and "error_type" in failed


def test_a_method_outcome_is_the_declared_shape_too(bench, part):
    from msb_arch import MethodOutcome

    declared = MethodOutcome.__required_keys__ | MethodOutcome.__optional_keys__
    outcome = bench.inspect(part, get_price=None, raise_on_error=False)["result"]["get_price"]

    assert set(outcome) <= declared
    assert MethodOutcome.__required_keys__ <= set(outcome)
