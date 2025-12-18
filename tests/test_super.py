import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any, Type
from src.msb_arch.super.super import Super
from src.msb_arch.mega.manipulator import Manipulator


class TestSuper(Super):

    OPERATION = "test_op"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._operation = self.OPERATION or "test_op"

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
    @patch('src.msb_arch.super.super.logger')
    def test_register_method(self, mock_logger, test_super):
        test_super.register_method(str, "test", lambda: None)
        assert str in test_super._methods
        assert "test" in test_super._methods[str]
        mock_logger.info.assert_called()


class TestSuperMakeHashable:
    def test_make_hashable_dict(self, test_super):
        d = {"a": 1, "b": 2}
        result = test_super._make_hashable(d)
        assert isinstance(result, tuple)

    def test_make_hashable_list(self, test_super):
        l = [1, 2, 3]
        result = test_super._make_hashable(l)
        assert isinstance(result, tuple)


class TestSuperUpdateCache:
    @patch('src.msb_arch.super.super.logger')
    def test_update_cache(self, mock_logger, test_super):
        key = ("key",)
        value = {"result": "value"}
        test_super._update_cache(key, value)
        assert key in test_super._method_cache
        mock_logger.debug.assert_called()


class TestSuperExecute:
    def test_execute_explicit_method(self, test_super):
        # Add a method to the instance
        test_super.explicit_method = lambda obj, attrs: "explicit"
        result = test_super.execute("obj", {}, method="explicit_method")
        assert result["status"] is True
        assert result["result"] == "explicit"

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
    @patch('src.msb_arch.super.super.logger')
    def test_clear_cache(self, mock_logger, test_super):
        test_super._method_cache["key"] = "value"
        test_super.clear_cache()
        assert test_super._method_cache == {}
        mock_logger.debug.assert_called()


class TestSuperClear:
    @patch('src.msb_arch.super.super.logger')
    def test_clear(self, mock_logger, test_super):
        test_super._methods["type"] = {}
        test_super.clear()
        assert test_super._manipulator is None
        assert test_super._methods == {}
        mock_logger.debug.assert_called()


class TestSuperDefaultResults:
    def test_default_result(self, test_super):
        result = test_super._default_result("obj")
        assert result["status"] is False

    def test_default_nested_result(self, test_super):
        result = test_super._default_nested_result("obj")
        assert result["status"] is False


class TestSuperRepr:
    def test_repr(self, test_super):
        repr_str = repr(test_super)
        assert "TestSuper" in repr_str


class TestSuperDel:
    @patch('src.msb_arch.super.super.logger')
    def test_del(self, mock_logger, test_super):
        del test_super
        mock_logger.error.assert_not_called()