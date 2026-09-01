import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any, Type
from msb_arch import BaseContainer, BaseEntity, errors
from msb_arch.super.super import Super
from msb_arch.mega.manipulator import Manipulator


class TestSuper(Super):

    OPERATION = "test_op"

    def _test_op(self, obj, attributes):
        return f"executed default on {obj}"

    def _test_op_list(self, obj, attributes):
        return f"executed list on {obj}"

    def _test_op_specific(self, obj, attributes):
        return f"executed specific on {obj}"


@pytest.fixture
def mock_manipulator():
    manip = MagicMock(spec=Manipulator)
    manip.get_methods_for_type.return_value = {"append": list.append}
    return manip


@pytest.fixture
def test_super(mock_manipulator):
    return TestSuper(manipulator=mock_manipulator)


class TestSuperInit:
    def test_init_basic(self):
        super_inst = TestSuper()
        assert super_inst._manipulator is None
        assert super_inst._methods == {}

    def test_init_with_manipulator(self, mock_manipulator):
        super_inst = TestSuper(manipulator=mock_manipulator)
        assert super_inst._manipulator == mock_manipulator


class TestSuperBuildResponse:
    def test_build_response_success(self, test_super):
        response = test_super._build_response("obj", True, "method", "result")
        assert response == {
            "status": True,
            "object": "obj",
            "method": "method",
            "result": "result"
        }

    def test_build_response_error(self, test_super):
        response = test_super._build_response("obj", False, None, None, "error")
        assert response["status"] is False
        assert response["error"] == "error"


class TestSuperGetMethods:
    def test_get_methods_from_methods(self, test_super):
        test_super._methods[str] = {"test": lambda: None}
        methods = test_super._get_methods(str)
        assert "test" in methods

    def test_get_methods_from_manipulator(self, test_super, mock_manipulator):
        methods = test_super._get_methods(list)
        mock_manipulator.get_methods_for_type.assert_called_once_with(list)
        assert methods == {"append": list.append}

    def test_get_methods_no_methods(self, test_super):
        test_super._manipulator = None
        with pytest.raises(ValueError):
            test_super._get_methods(str)


class TestSuperGetNestedObject:
    def test_get_nested_object_success(self, test_super):
        container = {"key": "value"}
        getter = lambda k: container.get(k)
        result = test_super._get_nested_object(container, "key", getter)
        assert result == "value"

    def test_get_nested_object_not_found(self, test_super):
        container = {}
        getter = lambda k: container.get(k)
        result = test_super._get_nested_object(container, "missing", getter)
        assert result is None


class TestSuperDoNested:
    def test_do_nested_success(self, test_super):
        obj = {"nested": "value"}
        attributes = {"index": "nested"}
        getter = lambda k: obj.get(k)
        handler = lambda nested, attrs: f"handled {nested}"
        result = test_super._do_nested(obj, attributes, "index", getter, handler)
        assert result["status"] is True
        assert result["result"] == "handled value"

    def test_do_nested_no_index(self, test_super):
        obj = {}
        attributes = {}
        getter = lambda k: None
        handler = lambda nested, attrs: None
        result = test_super._do_nested(obj, attributes, "index", getter, handler)
        assert result["status"] is False


class TestSuperValidateAndApplyMethod:
    def test_validate_and_apply_method_valid(self, test_super):
        valid_methods = {"test_method": lambda obj: "result"}
        result = test_super._validate_and_apply_method("obj", "test_method", None, valid_methods)
        assert result["status"] is True
        assert result["result"] == "result"

    def test_validate_and_apply_method_invalid(self, test_super):
        valid_methods = {}
        result = test_super._validate_and_apply_method("obj", "invalid", None, valid_methods)
        assert result["status"] is False


class TestSuperRegisterMethod:
    @patch('msb_arch.super.super.logger')
    def test_register_method(self, mock_logger, test_super):
        test_super.register_method(str, "test", lambda: None)
        assert str in test_super._methods
        assert "test" in test_super._methods[str]
        mock_logger.debug.assert_called()


class TestSuperExecute:
    def test_execute_named_handler(self, test_super):
        result = test_super.execute("obj", {}, method="specific")
        assert result["status"] is True
        assert result["method"] == "_test_op_specific"

    def test_execute_handler_by_its_full_name(self, test_super):
        result = test_super.execute("obj", {}, method="_test_op_specific")
        assert result["status"] is True
        assert result["method"] == "_test_op_specific"

    def test_execute_ignores_an_attribute_that_is_not_a_handler(self, test_super):
        # A name arriving in a request must not reach an arbitrary attribute; resolution
        # falls through to the operation's own handlers instead.
        test_super.explicit_method = lambda obj, attrs: "explicit"
        result = test_super.execute("obj", {}, method="explicit_method")
        assert result["status"] is True
        assert result["method"] == "_test_op"

    @pytest.mark.parametrize("dangerous", ["clear", "clear_cache", "execute", "register_method",
                                           "_build_response", "__init__"])
    def test_execute_refuses_to_call_framework_methods(self, test_super, dangerous):
        result = test_super.execute("obj", {}, method=dangerous)
        assert result["method"] == "_test_op"
        assert test_super._methods == {}
        assert test_super._manipulator is None or result["status"] is True

    def test_execute_without_registration(self):
        # _operation used to be assigned only by Manipulator.register_operation, so an
        # unregistered Super raised AttributeError before the try block.
        standalone = TestSuper()
        result = standalone.execute("obj", {})
        assert result["status"] is True
        assert result["method"] == "_test_op"

    def test_execute_without_an_operation_name_reports_it(self):
        class Nameless(Super):
            pass

        result = Nameless().execute("obj", {})
        assert result["status"] is False
        assert "no operation name" in result["error"]


class TestSuperHandlerResolutionCache:
    """Only the lookup is cached, never the outcome of an operation."""

    def test_repeated_resolution_is_cached(self, test_super):
        test_super.execute("obj", {})
        assert (None, str) in test_super._method_cache
        assert test_super._method_cache[(None, str)] == "_test_op"

    def test_cache_distinguishes_object_types(self, test_super):
        test_super.execute("obj", {})
        test_super.execute([1, 2], {})
        assert test_super._method_cache[(None, str)] == "_test_op"
        assert test_super._method_cache[(None, list)] == "_test_op_list"

    def test_a_failed_lookup_is_remembered_too(self):
        class Empty(Super):
            OPERATION = "empty_op"

        empty = Empty()
        assert empty.execute("obj", {})["status"] is False
        assert empty._method_cache[(None, str)] is None

    def test_operations_are_never_replayed_from_the_cache(self, test_super):
        calls = []
        test_super._test_op_counted = lambda obj, attrs: calls.append(obj) or "done"
        for _ in range(3):
            test_super.execute("obj", {}, method="counted")
        assert len(calls) == 3

    def test_register_method_drops_the_cache(self, test_super):
        test_super.execute("obj", {})
        assert test_super._method_cache
        test_super.register_method(str, "anything", lambda: None)
        assert test_super._method_cache == {}

    def test_cache_respects_its_size_limit(self):
        class Sized(Super):
            OPERATION = "sized_op"

            def _sized_op(self, obj, attributes):
                return True

        sized = Sized(cache_size=2)
        for name in ("a", "b", "c"):
            sized.execute("obj", {}, method=name)
        assert len(sized._method_cache) == 2

    def test_execute_method_from_attributes(self, test_super):
        test_super.method_from_attrs = lambda obj, attrs: "from_attrs"
        result = test_super.execute("obj", {"method": "method_from_attrs"})
        assert result["status"] is True

    def test_execute_prefixed_method(self, test_super):
        result = test_super.execute("obj", {"method": "specific"})
        assert result["status"] is True
        assert "specific" in result["result"]

    def test_execute_auto_method(self, test_super):
        result = test_super.execute([], {})
        assert result["status"] is True
        assert "list" in result["result"]

    def test_execute_default_method(self, test_super):
        result = test_super.execute("string", {})
        assert result["status"] is True
        assert "default" in result["result"]

    def test_execute_no_method(self, test_super):
        # Remove default method
        test_super._test_op = None
        result = test_super.execute("obj", {})
        assert result["status"] is False


class TestSuperClearCache:
    @patch('msb_arch.super.super.logger')
    def test_clear_cache(self, mock_logger, test_super):
        test_super._method_cache["key"] = "value"
        test_super.clear_cache()
        assert test_super._method_cache == {}
        mock_logger.debug.assert_called()


class TestSuperClear:
    @patch('msb_arch.super.super.logger')
    def test_clear(self, mock_logger, test_super):
        test_super._methods["type"] = {}
        test_super.release()
        assert test_super._manipulator is None
        assert test_super._methods == {}
        mock_logger.debug.assert_called()


class TestSuperExtensionPoints:
    """The helpers a Super subclass builds its handlers from.

    They carry a single underscore, meaning protected rather than private: the framework
    never calls them, subclasses do. Downstream code relies on all three, so they are part
    of the contract even though they are not part of the public surface.
    """

    def test_get_methods_reaches_the_manipulator(self, test_super):
        assert "append" in test_super._get_methods(list)

    def test_apply_method_validates_the_name(self, test_super):
        valid = {"known": lambda obj: "done"}
        assert test_super._validate_and_apply_method("obj", "known", None, valid)["status"] is True
        rejected = test_super._validate_and_apply_method("obj", "unknown", None, valid)
        assert rejected["status"] is False
        assert "not found" in rejected["error"]

    def test_do_nested_dispatches_to_the_nested_object(self, test_super):
        store = {"child": "value"}
        result = test_super._do_nested(store, {"index": "child"}, "index",
                                       store.get, lambda obj, attrs: f"handled {obj}")
        assert result["status"] is True
        assert result["result"] == "handled value"

    def test_do_nested_reports_a_missing_key(self, test_super):
        result = test_super._do_nested({}, {"index": "absent"}, "index",
                                       {}.get, lambda obj, attrs: None)
        assert result["status"] is False

    def test_build_response_shape(self, test_super):
        ok = test_super._build_response("obj", True, "m", 1)
        assert set(ok) == {"status", "object", "method", "result"}
        failed = test_super._build_response("obj", False, "m", None, "boom")
        assert failed["error"] == "boom"


class TestSuperRepr:
    def test_repr(self, test_super):
        repr_str = repr(test_super)
        assert "TestSuper" in repr_str


class TestSuperDel:
    @patch('msb_arch.super.super.logger')
    def test_del(self, mock_logger, test_super):
        del test_super
        mock_logger.error.assert_not_called()

class Instrument(BaseEntity):
    """A base type, with a subclass below it: the shape any real model has."""

    reading: float = 0.0


class Spectrometer(Instrument):
    channels: int = 1


class Instruments(BaseContainer[Instrument]):
    pass


class Maintenance(Super):
    OPERATION = "service"

    def _service_instrument(self, obj, attributes):
        return "instrument"

    def _service_basecontainer(self, obj, attributes):
        return "container"


class Bench(Manipulator):
    pass


@pytest.fixture
def bench():
    orchestrator = Bench(base_classes=[Instrument, Spectrometer, Instruments])
    orchestrator.register_operation(Maintenance(orchestrator))
    return orchestrator


def test_a_handler_written_for_a_base_class_serves_its_subclasses(bench):
    """Resolution walks the type's ancestors, so a hierarchy needs one handler, not one per leaf.

    Before this, `_service_instrument` did not answer for a `Spectrometer(Instrument)` and the
    request failed with `DispatchError` -- while containers had had exactly this fallback all
    along, spelled `_<operation>_basecontainer`.
    """
    assert bench.service(Spectrometer(name="s", channels=4)) == "instrument"
    assert bench.service(Instrument(name="i")) == "instrument"


def test_the_type_s_own_handler_still_wins(bench):
    class Precise(Super):
        OPERATION = "calibrate"

        def _calibrate_instrument(self, obj, attributes):
            return "generic"

        def _calibrate_spectrometer(self, obj, attributes):
            return "specific"

    bench.register_operation(Precise(bench))

    assert bench.calibrate(Spectrometer(name="s")) == "specific"
    assert bench.calibrate(Instrument(name="i")) == "generic"


def test_a_container_still_reaches_the_container_fallback(bench):
    """`basecontainer` is now a step of the same walk rather than a special case."""
    assert bench.service(Instruments(name="rack")) == "container"


def test_an_unrelated_type_reaches_the_operation_s_own_default():
    class Loose(BaseEntity):
        size: int = 0

    class Anything(Super):
        OPERATION = "handle"

        def _handle_instrument(self, obj, attributes):
            return "instrument"

        def _handle(self, obj, attributes):
            return "default"

    orchestrator = Bench(base_classes=[Instrument, Loose])
    orchestrator.register_operation(Anything(orchestrator))

    assert orchestrator.handle(Loose(name="l")) == "default"


def test_a_type_with_no_handler_anywhere_still_fails_to_dispatch():
    class Loose(BaseEntity):
        size: int = 0

    class Narrow(Super):
        OPERATION = "narrow"

        def _narrow_instrument(self, obj, attributes):
            return "instrument"

    orchestrator = Bench(base_classes=[Instrument, Loose])
    orchestrator.register_operation(Narrow(orchestrator))

    with pytest.raises(errors.DispatchError):
        orchestrator.narrow(Loose(name="l"))


def test_a_method_a_type_does_not_have_is_not_an_error_in_the_log(caplog):
    """It is already reported in the result, and asking is how a caller discovers what a type has.

    Logging it at ERROR made an application that reads several methods across mixed types print
    pages of them, and cost 13 us per call to build the record's stack frame.
    """
    import logging

    class Reader(Super):
        OPERATION = "read"

    orchestrator = Bench(base_classes=[Instrument])
    orchestrator.register_operation(Reader(orchestrator))
    instrument = Instrument(name="i")

    with caplog.at_level(logging.WARNING):
        answer = orchestrator.inspect(instrument, no_such_method=None, raise_on_error=False)

    assert answer["result"]["no_such_method"]["status"] is False
    assert caplog.records == []
