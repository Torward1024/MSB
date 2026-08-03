"""Tests for the loop the framework now owns, and for the batch facade.

`_apply_methods` is the loop every downstream handler used to write by hand: look up the
allowed methods, apply each requested one, decide what a failure means. Owning it here is
what makes the protocol uniform -- a response reports every method that ran, whatever the
request looked like -- which in turn is what makes a request history replayable.
"""
import pytest

from msb_arch import BaseEntity, Manipulator, MethodResults, Super


class Instrument(BaseEntity):
    diameter: float

    def get_code(self):
        return self.name

    def get_diameter(self):
        return self.diameter

    def set_diameter(self, value):
        self.diameter = value
        return True

    def explode(self):
        raise RuntimeError("boom")


class Inspector(Super):
    OPERATION = "inspect"

    def _inspect_instrument(self, obj, attributes):
        return self._apply_methods(obj, attributes)


class LenientInspector(Super):
    OPERATION = "survey"

    def _survey_instrument(self, obj, attributes):
        return self._apply_methods(obj, attributes, strict=False)


class Manip(Manipulator):
    pass


@pytest.fixture
def manipulator():
    manip = Manip(base_classes=[Instrument])
    manip.register_operation(Inspector(manip), operation="inspect")
    manip.register_operation(LenientInspector(manip), operation="survey")
    return manip


@pytest.fixture
def instrument():
    return Instrument(name="T1", diameter=25.0)


class TestApplyMethods:
    def test_every_named_method_is_reported(self, manipulator, instrument):
        response = manipulator.process_request({
            "operation": "inspect", "obj": instrument,
            "attributes": {"get_code": None, "get_diameter": None},
        })
        assert response["result"] == {
            "get_code": {"status": True, "result": "T1"},
            "get_diameter": {"status": True, "result": 25.0},
        }

    def test_the_shape_does_not_depend_on_how_many_were_named(self, manipulator, instrument):
        one = manipulator.process_request({
            "operation": "inspect", "obj": instrument, "attributes": {"get_code": None}})
        two = manipulator.process_request({
            "operation": "inspect", "obj": instrument,
            "attributes": {"get_code": None, "get_diameter": None}})
        assert isinstance(one["result"], MethodResults)
        assert isinstance(two["result"], MethodResults)

    def test_the_order_of_the_request_does_not_change_the_outcome(self, manipulator, instrument):
        forwards = manipulator.inspect(instrument, get_code=None, get_diameter=None)
        backwards = manipulator.inspect(instrument, get_diameter=None, get_code=None)
        assert forwards == backwards

    def test_arguments_reach_the_method(self, manipulator, instrument):
        manipulator.process_request({
            "operation": "inspect", "obj": instrument, "attributes": {"set_diameter": 30.0}})
        assert instrument.diameter == 30.0

    def test_values_only_drops_the_status(self, manipulator, instrument):
        response = manipulator.process_request({
            "operation": "inspect", "obj": instrument,
            "attributes": {"get_code": None, "get_diameter": None}})
        assert response["result"].values_only() == {"get_code": "T1", "get_diameter": 25.0}

    def test_an_empty_request_is_refused(self, manipulator, instrument):
        response = manipulator.process_request({
            "operation": "inspect", "obj": instrument, "attributes": {}})
        assert response["status"] is False
        assert "No methods requested" in response["error"]


class TestFailurePolicy:
    def test_strict_stops_at_the_first_failure(self, manipulator, instrument):
        response = manipulator.process_request({
            "operation": "inspect", "obj": instrument,
            "attributes": {"missing_method": None, "get_code": None}})
        assert response["status"] is False
        assert "missing_method" in response["error"]

    def test_lenient_records_every_outcome(self, manipulator, instrument):
        response = manipulator.process_request({
            "operation": "survey", "obj": instrument,
            "attributes": {"missing_method": None, "get_code": None}})
        assert response["status"] is True
        assert response["result"]["missing_method"]["status"] is False
        assert response["result"]["get_code"]["result"] == "T1"

    def test_an_exception_inside_a_method_is_reported(self, manipulator, instrument):
        response = manipulator.process_request({
            "operation": "survey", "obj": instrument, "attributes": {"explode": None}})
        assert response["result"]["explode"]["status"] is False
        assert "boom" in response["result"]["explode"]["error"]


class TestFacadeUnwrapping:
    def test_a_single_method_yields_its_value(self, manipulator, instrument):
        assert manipulator.inspect(instrument, get_code=None) == "T1"

    def test_several_methods_yield_the_mapping(self, manipulator, instrument):
        result = manipulator.inspect(instrument, get_code=None, get_diameter=None)
        assert result["get_code"]["result"] == "T1"
        assert result["get_diameter"]["result"] == 25.0

    def test_the_full_response_is_available(self, manipulator, instrument):
        response = manipulator.inspect(instrument, get_code=None, raise_on_error=False)
        assert response["status"] is True
        assert isinstance(response["result"], MethodResults)

    def test_a_plain_mapping_from_a_handler_is_left_alone(self):
        class Raw(Super):
            OPERATION = "raw"

            def _raw(self, obj, attributes):
                return {"only": "a plain dict"}

        manip = Manip()
        manip.register_operation(Raw(manip), operation="raw")
        assert manip.raw("obj", anything=None) == {"only": "a plain dict"}


class TestBatch:
    def test_a_sequence_is_numbered(self, manipulator, instrument):
        results = manipulator.batch([
            {"operation": "inspect", "obj": instrument, "attributes": {"get_code": None}},
            {"operation": "inspect", "obj": instrument, "attributes": {"get_diameter": None}},
        ])
        assert set(results) == {"0", "1"}
        assert results["0"]["result"]["get_code"]["result"] == "T1"
        assert results["1"]["result"]["get_diameter"]["result"] == 25.0

    def test_a_mapping_keeps_its_identifiers(self, manipulator, instrument):
        results = manipulator.batch({
            "read_code": {"operation": "inspect", "obj": instrument, "attributes": {"get_code": None}},
        })
        assert set(results) == {"read_code"}

    def test_requests_run_in_order(self, manipulator, instrument):
        results = manipulator.batch([
            {"operation": "inspect", "obj": instrument, "attributes": {"set_diameter": 40.0}},
            {"operation": "inspect", "obj": instrument, "attributes": {"get_diameter": None}},
        ])
        assert results["1"]["result"]["get_diameter"]["result"] == 40.0

    def test_a_failure_is_reported_without_stopping(self, manipulator, instrument):
        results = manipulator.batch([
            {"operation": "inspect", "obj": instrument, "attributes": {"missing": None}},
            {"operation": "inspect", "obj": instrument, "attributes": {"get_code": None}},
        ])
        assert results["0"]["status"] is False
        assert results["1"]["status"] is True

    def test_raise_on_error_stops_the_caller(self, manipulator, instrument):
        with pytest.raises(Exception, match="Request '0' failed"):
            manipulator.batch(
                [{"operation": "inspect", "obj": instrument, "attributes": {"missing": None}}],
                raise_on_error=True,
            )

    def test_an_empty_batch_is_empty(self, manipulator):
        assert manipulator.batch([]) == {}

    @pytest.mark.parametrize("bad", ["a string", 42, None])
    def test_a_non_batch_is_refused(self, manipulator, bad):
        with pytest.raises(TypeError):
            manipulator.batch(bad)

    def test_a_request_that_is_not_a_dictionary_is_refused(self, manipulator):
        with pytest.raises(TypeError, match="not dictionaries"):
            manipulator.batch(["not a request"])
