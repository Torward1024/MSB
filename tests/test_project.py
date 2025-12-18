import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any
from src.msb_arch.super.project import Project
from src.msb_arch.base.baseentity import BaseEntity


class TestEntity(BaseEntity):
    value: int


class TestProject(Project):
    _item_type = TestEntity
    name = 'TestProject'

    def create_item(self, item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None:
        item = TestEntity(name=item_code, value=42, isactive=isactive)
        self.add_item(item)
    
    @classmethod
    def from_dict(cls, data):
        return super().from_dict(data)


@pytest.fixture
def test_entity():
    return TestEntity(name="item1", value=1)


@pytest.fixture
def test_project():
    items = {"item1": TestEntity(name="item1", value=1), "item2": TestEntity(name="item2", value=2)}
    return TestProject(name="test_project", items=items)


class TestProjectInit:
    @patch('src.msb_arch.super.project.logger')
    def test_init_valid(self, mock_logger):
        project = TestProject(name="test")
        assert project.name == "test"
        assert len(project._items) == 0
        mock_logger.info.assert_called()

    def test_init_with_items(self):
        items = {"item1": TestEntity(name="item1", value=1)}
        project = TestProject(name="test", items=items)
        assert len(project._items) == 1

    def test_init_invalid_name(self):
        with pytest.raises(ValueError):
            TestProject(name="")


class TestProjectCreateContainer:
    def test_create_container(self):
        container = TestProject._create_container(name='test')
        assert container is not None


class TestProjectAddItem:
    def test_add_item_valid(self, test_project, test_entity):
        test_entity.name = "new_item"
        test_project.add_item(test_entity)
        assert test_project._items.has_item("new_item")

    def test_add_item_wrong_type(self, test_project):
        wrong_item = BaseEntity(name="wrong")
        with pytest.raises(TypeError):
            test_project.add_item(wrong_item)

    def test_add_item_duplicate(self, test_project):
        duplicate = TestEntity(name="item1", value=100)
        with pytest.raises(ValueError):
            test_project.add_item(duplicate)

    @patch('src.msb_arch.super.project.logger')
    def test_add_item_logs(self, mock_logger, test_project):
        item = TestEntity(name="new", value=1)
        test_project.add_item(item)
        mock_logger.debug.assert_called()


class TestProjectCreateItem:
    def test_create_item(self, test_project):
        test_project.create_item("new_item")
        assert test_project._items.has_item("new_item")
        item = test_project.get_item("new_item")
        assert item.value == 42


class TestProjectSetItem:
    @patch('src.msb_arch.super.project.logger')
    def test_set_item(self, mock_logger, test_project):
        new_item = TestEntity(name="set_item", value=99)
        test_project.set_item("set_item", new_item)
        assert test_project.get_item("set_item").value == 99
        mock_logger.info.assert_called()


class TestProjectRemoveItem:
    @patch('src.msb_arch.super.project.logger')
    def test_remove_item(self, mock_logger, test_project):
        test_project.remove_item("item1")
        assert not test_project._items.has_item("item1")
        mock_logger.info.assert_called()


class TestProjectGetActiveInactive:
    def test_get_active_items(self, test_project):
        active = test_project.get_active_items()
        assert len(active) == 2

    def test_get_inactive_items(self, test_project):
        test_project.deactivate_item("item1")
        inactive = test_project.get_inactive_items()
        assert len(inactive) == 1


class TestProjectGetItem:
    @patch('src.msb_arch.super.project.logger')
    def test_get_item(self, mock_logger, test_project):
        item = test_project.get_item("item1")
        assert item.value == 1
        mock_logger.debug.assert_called()


class TestProjectGetItems:
    def test_get_items(self, test_project):
        items = test_project.get_items()
        assert len(items) == 2


class TestProjectGetSetName:
    @patch('src.msb_arch.super.project.logger')
    def test_get_name(self, mock_logger, test_project):
        name = test_project.get_name()
        assert name == "test_project"
        mock_logger.debug.assert_called()

    @patch('src.msb_arch.super.project.logger')
    def test_set_name(self, mock_logger, test_project):
        test_project.set_name("new_name")
        assert test_project.name == "new_name"
        mock_logger.info.assert_called()

    def test_set_name_invalid(self, test_project):
        with pytest.raises(ValueError):
            test_project.set_name("")


class TestProjectSetGetProject:
    @patch('src.msb_arch.super.project.logger')
    def test_set_project(self, mock_logger, test_project):
        new_items = {"new1": TestEntity(name="new1", value=10)}
        test_project.set_project("new_proj", new_items)
        assert test_project.name == "new_proj"
        assert len(test_project._items) == 1
        mock_logger.info.assert_called()

    @patch('src.msb_arch.super.project.logger')
    def test_get_project(self, mock_logger, test_project):
        proj = test_project.get_project()
        assert "name" in proj
        assert "items" in proj
        mock_logger.info.assert_called()


class TestProjectClear:
    @patch('src.msb_arch.super.project.logger')
    def test_clear(self, mock_logger, test_project):
        test_project.clear()
        assert len(test_project._items) == 0
        mock_logger.info.assert_called()


class TestProjectActivateDeactivate:
    @patch('src.msb_arch.super.project.logger')
    def test_activate_item(self, mock_logger, test_project):
        test_project.deactivate_item("item1")
        test_project.activate_item("item1")
        assert test_project.get_item("item1").isactive is True
        mock_logger.info.assert_called()

    @patch('src.msb_arch.super.project.logger')
    def test_deactivate_item(self, mock_logger, test_project):
        test_project.deactivate_item("item1")
        assert test_project.get_item("item1").isactive is False
        mock_logger.info.assert_called()

    def test_activate_all(self, test_project):
        test_project.deactivate_all()
        test_project.activate_all()
        assert all(item.isactive for item in test_project.get_active_items())

    def test_deactivate_all(self, test_project):
        test_project.deactivate_all()
        assert all(not item.isactive for item in test_project.get_inactive_items())

    def test_drop_active(self, test_project):
        test_project.deactivate_item("item1")
        test_project.drop_active()
        assert len(test_project._items) == 1

    def test_drop_inactive(self, test_project):
        test_project.deactivate_item("item1")
        test_project.drop_inactive()
        assert len(test_project._items) == 1


class TestProjectToDict:
    def test_to_dict(self, test_project):
        data = test_project.to_dict()
        assert data["name"] == "test_project"
        assert "items" in data


class TestProjectFromDict:
    def test_from_dict_valid(self):
        data = {
            "name": "test",
            "items": {
                "item1": {"name": "item1", "isactive": True, "value": 1, "type": "TestEntity"}
            }
        }
        project = TestProject.from_dict(data)
        assert project.name == "test"
        assert len(project._items) == 1

    def test_from_dict_invalid_name(self):
        data = {"name": "", "items": {}}
        with pytest.raises(ValueError):
            TestProject.from_dict(data)

    def test_from_dict_invalid_item(self):
        data = {
            "name": "test",
            "items": {
                "item1": {"invalid": "data"}
            }
        }
        with pytest.raises(ValueError):
            TestProject.from_dict(data)


class TestProjectRepr:
    def test_repr(self, test_project):
        repr_str = repr(test_project)
        assert "Project" in repr_str
        assert "test_project" in repr_str


class TestProjectDel:
    @patch('src.msb_arch.super.project.logger')
    def test_del(self, mock_logger, test_project):
        del test_project