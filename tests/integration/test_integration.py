import pytest
from unittest.mock import patch, MagicMock, Mock
from typing import Dict, Any, List
from src.msb_arch.mega.manipulator import Manipulator
from src.msb_arch.super.super import Super
from src.msb_arch.super.project import Project
from src.msb_arch.base.basecontainer import BaseContainer
from src.msb_arch.base.baseentity import BaseEntity


class TestEntity(BaseEntity):
    value: int
    nested: 'TestEntity' = None
    child: 'TestEntity' = None
    self_ref: 'TestEntity' = None


class TestContainer(BaseContainer[TestEntity]):
    pass


class TestProject(Project):
    _item_type = TestEntity

    def create_item(self, item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None:
        item = TestEntity(name=item_code, value=42, isactive=isactive)
        self.add_item(item)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestProject':
        return super().from_dict(data)


class TestSuper(Super):
    OPERATION = "test_op"

    def _test_op(self, obj, attributes):
        return f"executed test_op on {obj}"

    def _test_op_entity(self, obj, attributes):
        if isinstance(obj, TestEntity):
            return f"processed entity {obj.name}"
        return "not an entity"


class TestManipulator(Manipulator):
    pass


@pytest.fixture
def test_entity():
    return TestEntity(name="test_entity", value=10)


@pytest.fixture
def test_container():
    return TestContainer(name="test_container")


@pytest.fixture
def test_project():
    return TestProject(name="test_project")


@pytest.fixture
def test_super():
    return TestSuper()


@pytest.fixture
def test_manipulator():
    return TestManipulator()


@pytest.fixture
def manipulator_with_super(test_manipulator, test_super):
    test_manipulator.register_operation(test_super)
    return test_manipulator


@pytest.fixture
def populated_container(test_container, test_entity):
    test_container.add(test_entity)
    return test_container


@pytest.fixture
def populated_project(test_project, test_entity):
    test_project.add_item(test_entity)
    return test_project


class TestManipulatorSuperIntegration:
    """Integration tests for Manipulator and Super interaction."""

    def test_manipulator_registers_super_operation(self, test_manipulator, test_super):
        test_manipulator.register_operation(test_super)
        assert "test_op" in test_manipulator._operations
        assert hasattr(test_manipulator, "test_op")

    def test_manipulator_executes_super_operation(self, manipulator_with_super, test_entity):
        result = manipulator_with_super.test_op(obj=test_entity, raise_on_error=False)
        assert result["status"] is True
        assert "executed test_op on" in result["result"]

    def test_manipulator_processes_request_via_super(self, manipulator_with_super, test_entity):
        request = {"operation": "test_op", "obj": test_entity}
        result = manipulator_with_super.process_request(request)
        assert result["status"] is True
        assert result["method"] == "_test_op"

    def test_manipulator_super_with_invalid_object(self, manipulator_with_super):
        request = {"operation": "test_op", "obj": "invalid"}
        result = manipulator_with_super.process_request(request)
        assert result["status"] is True  # Super handles it gracefully
        assert "executed test_op" in result["result"]

    def test_manipulator_super_edge_case_no_operation(self, test_manipulator, test_entity):
        request = {"obj": test_entity}
        result = test_manipulator.process_request(request)
        assert result["status"] is False
        assert "Invalid sub-request type" in result["error"]

    def test_manipulator_super_error_unregistered_operation(self, test_manipulator, test_entity):
        request = {"operation": "unknown_op", "obj": test_entity}
        result = test_manipulator.process_request(request)
        assert result["status"] is False
        assert "not registered" in result["error"]


class TestProjectBaseContainerIntegration:
    """Integration tests for Project and BaseContainer interaction."""

    def test_project_adds_item_to_container(self, test_project, test_entity):
        test_project.add_item(test_entity)
        assert test_project._items.has_item("test_entity")
        assert test_project.get_item("test_entity") == test_entity

    def test_project_creates_item_via_container(self, test_project):
        test_project.create_item("new_item")
        assert test_project._items.has_item("new_item")
        item = test_project.get_item("new_item")
        assert item.value == 42

    def test_project_removes_item_from_container(self, populated_project):
        populated_project.remove_item("test_entity")
        assert not populated_project._items.has_item("test_entity")

    def test_project_activates_item_in_container(self, populated_project):
        populated_project.deactivate_item("test_entity")
        populated_project.activate_item("test_entity")
        assert populated_project.get_item("test_entity").isactive is True

    def test_project_gets_active_items_from_container(self, populated_project):
        active = populated_project.get_active_items()
        assert len(active) == 1
        assert active[0].name == "test_entity"

    def test_project_serialization_with_container(self, populated_project):
        data = populated_project.to_dict()
        assert "name" in data
        assert "items" in data
        assert "test_entity" in data["items"]

        # Deserialize
        new_project = TestProject.from_dict(data)
        assert new_project.name == populated_project.name
        assert len(new_project._items) == 1
        assert new_project.get_item("test_entity").value == 10

    def test_project_container_edge_case_empty_project(self, test_project):
        data = test_project.to_dict()
        new_project = TestProject.from_dict(data)
        assert len(new_project._items) == 0

    def test_project_container_error_duplicate_item(self, populated_project, test_entity):
        test_entity.name = "duplicate"
        populated_project.add_item(test_entity)
        with pytest.raises(ValueError):
            populated_project.add_item(TestEntity(name="duplicate", value=20))

    def test_project_container_error_invalid_item_type(self, test_project):
        with pytest.raises(TypeError):
            test_project.add_item(BaseEntity(name="invalid"))


class TestSerializationChainsIntegration:
    """Integration tests for serialization of object chains."""

    def test_nested_entity_serialization(self, test_entity):
        # Create nested entity
        nested = TestEntity(name="nested", value=5)
        test_entity.nested = nested

        data = test_entity.to_dict()
        assert "nested" in data
        assert data["nested"]["name"] == "nested"

        # Deserialize
        new_entity = TestEntity.from_dict(data)
        assert new_entity.nested.name == "nested"
        assert new_entity.nested.value == 5

    def test_container_with_nested_entities_serialization(self, test_container, test_entity):
        nested = TestEntity(name="nested", value=15)
        test_entity.nested = nested
        test_container.add(test_entity)

        data = test_container.to_dict()
        assert "items" in data
        assert "test_entity" in data["items"]
        assert "nested" in data["items"]["test_entity"]

        # Deserialize
        new_container = TestContainer.from_dict(data)
        assert len(new_container) == 1
        item = new_container.get("test_entity")
        assert item.nested.value == 15

    def test_project_with_nested_container_serialization(self, test_project, test_entity):
        nested = TestEntity(name="nested", value=25)
        test_entity.nested = nested
        test_project.add_item(test_entity)

        data = test_project.to_dict()
        assert "items" in data
        assert "test_entity" in data["items"]
        assert "nested" in data["items"]["test_entity"]

        # Deserialize
        new_project = TestProject.from_dict(data)
        assert len(new_project._items) == 1
        item = new_project.get_item("test_entity")
        assert item.nested.value == 25

    def test_cyclic_reference_handling(self, test_entity):
        # Create cyclic reference
        test_entity.self_ref = test_entity

        data = test_entity.to_dict()
        assert "self_ref" in data
        assert data["self_ref"] == "<cyclic reference>"

    def test_deep_nesting_serialization(self):
        # Create deep nesting
        level1 = TestEntity(name="level1", value=1)
        level2 = TestEntity(name="level2", value=2)
        level3 = TestEntity(name="level3", value=3)

        level1.child = level2
        level2.child = level3

        data = level1.to_dict()
        assert "child" in data
        assert data["child"]["child"]["name"] == "level3"

        # Deserialize
        new_level1 = TestEntity.from_dict(data)
        assert new_level1.child.child.value == 3

    def test_serialization_error_invalid_data(self):
        invalid_data = {"name": "test", "invalid_field": "value"}
        with pytest.raises(ValueError):
            TestEntity.from_dict(invalid_data)


class TestGeneralWorkflowIntegration:
    """Integration tests for general workflow: entity creation, operation registration, request processing."""

    def test_full_workflow_entity_creation_and_manipulation(self, test_manipulator, test_super, test_project):
        # Register operation
        test_manipulator.register_operation(test_super)

        # Create entity
        entity = TestEntity(name="workflow_entity", value=100)
        test_project.add_item(entity)

        # Process request on entity
        request = {"operation": "test_op", "obj": entity}
        result = test_manipulator.process_request(request)
        assert result["status"] is True
        assert "executed test_op on" in result["result"]

    def test_workflow_with_container_and_project(self, test_manipulator, test_super, test_project):
        # Register operation
        test_manipulator.register_operation(test_super)

        # Create and add entity to project
        test_project.create_item("workflow_item")

        # Get entity from project
        entity = test_project.get_item("workflow_item")

        # Process via manipulator
        result = test_manipulator.test_op(obj=entity, raise_on_error=False)
        assert result["status"] is True
        assert "workflow_item" in result["result"]

    def test_workflow_serialization_and_deserialization(self, test_manipulator, test_super, test_project):
        # Register operation
        test_manipulator.register_operation(test_super)

        # Create project with items
        test_project.create_item("item1")
        test_project.create_item("item2")

        # Serialize project
        project_data = test_project.to_dict()

        # Deserialize project
        new_project = TestProject.from_dict(project_data)
        assert len(new_project._items) == 2

        # Process on deserialized entity
        entity = new_project.get_item("item1")
        result = test_manipulator.test_op(obj=entity, raise_on_error=False)
        assert result["status"] is True

    def test_workflow_sequence_requests(self, test_manipulator, test_super, test_project):
        # Register operation
        test_manipulator.register_operation(test_super)

        # Create entities
        test_project.create_item("seq1")
        test_project.create_item("seq2")

        # Process sequence of requests
        requests = {
            "req1": {"operation": "test_op", "obj": test_project.get_item("seq1")},
            "req2": {"operation": "test_op", "obj": test_project.get_item("seq2")}
        }
        results = test_manipulator.process_request(requests)
        assert "req1" in results
        assert "req2" in results
        assert all(r["status"] for r in results.values())

    def test_workflow_edge_case_empty_container(self, test_manipulator, test_super, test_project):
        # Register operation
        test_manipulator.register_operation(test_super)

        # Try to process on non-existent item
        with pytest.raises(Exception):  # Manipulator raises on error
            test_manipulator.test_op(obj=None, raise_on_error=True)

    def test_workflow_error_invalid_operation(self, test_manipulator, test_project):
        test_project.create_item("error_item")
        entity = test_project.get_item("error_item")

        # Try unregistered operation
        request = {"operation": "invalid_op", "obj": entity}
        result = test_manipulator.process_request(request)
        assert result["status"] is False
        assert "not registered" in result["error"]

    def test_workflow_error_invalid_entity_type(self, test_manipulator, test_super):
        # Register operation
        test_manipulator.register_operation(test_super)

        # Try with invalid object
        result = test_manipulator.test_op(obj="string", raise_on_error=False)
        assert result["status"] is True  # Super handles gracefully
        assert "executed test_op" in result["result"]