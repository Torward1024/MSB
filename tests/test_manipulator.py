import pytest
from unittest.mock import patch, MagicMock, Mock
from typing import Dict, Any, List, Type
from src.msb_arch.mega.manipulator import Manipulator
from src.msb_arch.super.super import Super


class MockSuper:
    def __init__(self, operation=None):
        self.OPERATION = operation

    def execute(self, obj, attributes=None, method=None):
        return {
            "status": True,
            "object": obj,
            "method": method,
            "result": f"executed {method or 'default'} on {obj}",
            "error": None
        }


class TestManipulator(Manipulator):
    pass


@pytest.fixture
def mock_super():
    return MockSuper()


@pytest.fixture
def manipulator():
    return TestManipulator()


@pytest.fixture
def manipulator_with_ops(mock_super):
    manip = TestManipulator()
    manip.register_operation(mock_super, operation="test_op")
    return manip


class TestManipulatorInit:
    @patch('src.msb_arch.mega.manipulator.logger')
    def test_init_basic(self, mock_logger):
        manip = TestManipulator()
        assert manip._managing_object is None
        assert manip._operations == {}
        mock_logger.debug.assert_called()

    def test_init_with_managing_object(self):
        obj = [1, 2, 3]
        manip = TestManipulator(managing_object=obj)
        assert manip._managing_object == obj
        assert list in manip._base_classes

    def test_init_with_operations(self, mock_super):
        ops = {"unique_operation": mock_super}
        manip = TestManipulator(operations=ops)
        assert "unique_operation" in manip._operations



class TestManipulatorSetGetManagingObject:
    @patch('src.msb_arch.mega.manipulator.logger')
    def test_set_managing_object(self, mock_logger, manipulator):
        obj = {"key": "value"}
        manipulator.set_managing_object(obj)
        assert manipulator._managing_object == obj
        mock_logger.info.assert_called()

    def test_get_managing_object(self, manipulator):
        obj = [1, 2]
        manipulator._managing_object = obj
        assert manipulator.get_managing_object() == obj


class TestManipulatorValidateObject:
    def test_validate_object_with_obj(self, manipulator):
        obj = "test"
        assert manipulator._validate_object(obj, "test") == obj

    def test_validate_object_with_managing(self, manipulator):
        manipulator._managing_object = "managing"
        assert manipulator._validate_object(None, "test") == "managing"

    def test_validate_object_none(self, manipulator):
        with pytest.raises(ValueError):
            manipulator._validate_object(None, "test")

    def test_validate_object_strict_unsupported(self, manipulator):
        manipulator._strict_type_check = True
        with pytest.raises(ValueError):
            manipulator._validate_object("unsupported", "test")


class TestManipulatorGetMethodsForType:
    def test_get_methods_for_type_existing(self, manipulator_with_ops, mock_super):
        methods = manipulator_with_ops.get_methods_for_type(type(mock_super))
        assert "execute" in methods

    def test_get_methods_for_type_nonexistent(self, manipulator):
        with pytest.raises(ValueError):
            manipulator.get_methods_for_type(str)


class TestManipulatorUpdateRegistry:
    @patch('src.msb_arch.mega.manipulator.logger')
    def test_update_registry(self, mock_logger, manipulator):
        manipulator.update_registry(additional_classes=[list])
        assert list in manipulator._base_classes
        mock_logger.info.assert_called()


class TestManipulatorRegisterOperation:
    def test_register_operation_valid(self, manipulator, mock_super):
        manipulator.register_operation(mock_super, operation="test_op")
        assert "test_op" in manipulator._operations

    def test_register_operation_no_execute(self, manipulator):
        mock_super_no_exec = Mock(spec=Super)
        del mock_super_no_exec.execute
        with pytest.raises(ValueError):
            manipulator.register_operation(mock_super_no_exec, operation="unique_op")

    def test_register_operation_duplicate(self, manipulator, mock_super):
        manipulator.register_operation(mock_super, operation="test_op")
        with pytest.raises(ValueError):
            manipulator.register_operation(MockSuper(), operation="test_op")

    def test_register_operation_auto_operation(self, manipulator):
        mock_super_auto = MockSuper(operation="auto_op")
        manipulator.register_operation(mock_super_auto)
        assert "auto_op" in manipulator._operations

    def test_register_operation_invalid_name(self, manipulator, mock_super):
        with pytest.raises(ValueError):
            manipulator.register_operation(mock_super, operation="")

    @patch('src.msb_arch.mega.manipulator.logger')
    def test_register_operation_logs(self, mock_logger, manipulator, mock_super):
        manipulator.register_operation(mock_super, operation="test_op")
        mock_logger.debug.assert_called()


class TestManipulatorAddFacade:
    def test_add_facade(self, manipulator_with_ops):
        # Facade should be added
        assert hasattr(manipulator_with_ops, "test_op")


class TestManipulatorGetMethodRegistry:
    def test_get_method_registry(self, manipulator_with_ops):
        registry = manipulator_with_ops._get_method_registry()
        assert len(registry) > 0


class TestManipulatorProcessRequest:
    def test_process_request_single_valid(self, manipulator_with_ops):
        request = {"operation": "test_op", "obj": "test_obj", "attributes": {"key": "value"}}
        result = manipulator_with_ops.process_request(request)
        assert result["status"] is True
        assert result["result"] == "executed default on test_obj"

    def test_process_request_invalid_type(self, manipulator):
        with pytest.raises(TypeError):
            manipulator.process_request("invalid")

    def test_process_request_no_operation(self, manipulator):
        request = {"obj": "test"}
        result = manipulator.process_request(request)
        assert result["status"] is False

    def test_process_request_sequence(self, manipulator_with_ops):
        requests = {
            "req1": {"operation": "test_op", "obj": "obj1"},
            "req2": {"operation": "test_op", "obj": "obj2"}
        }
        results = manipulator_with_ops.process_request(requests)
        assert "req1" in results
        assert "req2" in results

    def test_process_request_sequence_invalid_sub(self, manipulator):
        requests = {"req1": "invalid"}
        result = manipulator.process_request(requests)
        assert result["status"] is False


class TestManipulatorProcessSingleRequest:
    def test_process_single_request_valid(self, manipulator_with_ops):
        request = {"operation": "test_op", "obj": "test_obj"}
        result = manipulator_with_ops._process_single_request(request)
        assert result["status"] is True

    def test_process_single_request_no_operation(self, manipulator):
        request = {}
        result = manipulator._process_single_request(request)
        assert result["status"] is False

    def test_process_single_request_unregistered_op(self, manipulator):
        request = {"operation": "unknown"}
        result = manipulator._process_single_request(request)
        assert result["status"] is False

    def test_process_single_request_invalid_obj(self, manipulator_with_ops):
        manipulator_with_ops._strict_type_check = True
        request = {"operation": "test_op", "obj": None}
        result = manipulator_with_ops._process_single_request(request)
        assert result["status"] is False


class TestManipulatorGetSupportedOperations:
    def test_get_supported_operations(self, manipulator_with_ops):
        ops = manipulator_with_ops.get_supported_operations()
        assert "test_op" in ops


class TestManipulatorClearMethods:
    def test_clear_cache(self, manipulator):
        manipulator.clear_cache()
        # Cache cleared

    def test_clear_base_classes(self, manipulator):
        manipulator._base_classes = [list]
        manipulator.clear_base_classes()
        assert manipulator._base_classes == []

    def test_clear_ops(self, manipulator_with_ops):
        manipulator_with_ops.clear_ops()
        assert manipulator_with_ops._operations == {}


class TestManipulatorRepr:
    def test_repr(self, manipulator):
        repr_str = repr(manipulator)
        assert "Manipulator" in repr_str


class TestManipulatorDel:
    @patch('src.msb_arch.mega.manipulator.logger')
    def test_del(self, mock_logger, manipulator):
        del manipulator