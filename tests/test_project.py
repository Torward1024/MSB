import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any
from msb_arch.super.project import Project
from msb_arch.base.baseentity import BaseEntity
from msb_arch import errors


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
    @patch('msb_arch.super.project.logger')
    def test_init_valid(self, mock_logger):
        project = TestProject(name="test")
        assert project.name == "test"
        assert len(project._items) == 0
        mock_logger.debug.assert_called()

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

    def test_container_type_is_reused_across_calls(self):
        # A fresh class per call leaked one class per project and left the containers of
        # two projects of the same type unrelated.
        first = TestProject._create_container(name='first')
        second = TestProject._create_container(name='second')
        assert type(first) is type(second)

    def test_containers_of_two_projects_compare_equal(self):
        first = TestProject(name='ProjectA')
        second = TestProject(name='ProjectB')
        first.add_item(TestEntity(name='item1', value=1))
        second.add_item(TestEntity(name='item1', value=1))
        second._items.name = first._items.name
        assert first._items == second._items

    def test_repeated_projects_do_not_accumulate_classes(self):
        classes = {type(TestProject(name=f'Project{i}')._items) for i in range(25)}
        assert len(classes) == 1


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

    @patch('msb_arch.super.project.logger')
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
    @patch('msb_arch.super.project.logger')
    def test_set_item(self, mock_logger, test_project):
        new_item = TestEntity(name="set_item", value=99)
        test_project.set_item("set_item", new_item)
        assert test_project.get_item("set_item").value == 99
        mock_logger.info.assert_called()


class TestProjectRemoveItem:
    @patch('msb_arch.super.project.logger')
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
    @patch('msb_arch.super.project.logger')
    def test_get_item(self, mock_logger, test_project):
        item = test_project.get_item("item1")
        assert item.value == 1
        mock_logger.debug.assert_called()


class TestProjectGetItems:
    def test_get_items(self, test_project):
        items = test_project.get_items()
        assert len(items) == 2


class TestProjectGetSetName:
    @patch('msb_arch.super.project.logger')
    def test_get_name(self, mock_logger, test_project):
        name = test_project.get_name()
        assert name == "test_project"
        mock_logger.debug.assert_called()

    @patch('msb_arch.super.project.logger')
    def test_set_name(self, mock_logger, test_project):
        test_project.set_name("new_name")
        assert test_project.name == "new_name"
        mock_logger.info.assert_called()

    def test_set_name_invalid(self, test_project):
        with pytest.raises(ValueError):
            test_project.set_name("")


class TestProjectSetGetProject:
    @patch('msb_arch.super.project.logger')
    def test_set_project(self, mock_logger, test_project):
        new_items = {"new1": TestEntity(name="new1", value=10)}
        test_project.set_project("new_proj", new_items)
        assert test_project.name == "new_proj"
        assert len(test_project._items) == 1
        mock_logger.info.assert_called()

    @patch('msb_arch.super.project.logger')
    def test_get_project(self, mock_logger, test_project):
        proj = test_project.get_project()
        assert "name" in proj
        assert "items" in proj
        mock_logger.debug.assert_called()


class TestProjectClear:
    @patch('msb_arch.super.project.logger')
    def test_remove_all(self, mock_logger, test_project):
        test_project.remove_all()
        assert len(test_project._items) == 0
        mock_logger.debug.assert_called()


class TestProjectActivateDeactivate:
    @patch('msb_arch.super.project.logger')
    def test_activate_item(self, mock_logger, test_project):
        test_project.deactivate_item("item1")
        test_project.activate_item("item1")
        assert test_project.get_item("item1").isactive is True
        mock_logger.info.assert_called()

    @patch('msb_arch.super.project.logger')
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
    @patch('msb_arch.super.project.logger')
    def test_del(self, mock_logger, test_project):
        del test_project

class TestProjectFromDictIsConcrete:
    """from_dict used to be abstract while carrying a full implementation."""

    def test_a_subclass_need_not_override_from_dict(self):
        class MinimalProject(Project):
            _item_type = TestEntity

            def create_item(self, item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None:
                self.add_item(TestEntity(name=item_code, value=42, isactive=isactive))

        project = MinimalProject(name="Minimal")
        project.create_item("item1")
        restored = MinimalProject.from_dict(project.to_dict())
        assert restored.get_item("item1").value == 42

    def test_create_item_is_still_abstract(self):
        class Incomplete(Project):
            _item_type = TestEntity

        with pytest.raises(TypeError):
            Incomplete(name="Incomplete")


# --- a project is a Serializable, like an entity and a container ---------------------------------

class ProjectTask(BaseEntity):
    effort: float = 1.0


class UrgentProjectTask(ProjectTask):
    fee: float = 0.0


class Tasks(Project):
    _item_type = ProjectTask

    def create_item(self, item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None:
        self.add_item(ProjectTask(name=item_code, isactive=isactive))


def test_two_equal_projects_compare_equal():
    """It inherited identity comparison, so `load(...) == project` was False for its own file."""
    project = Tasks(name="p")
    project.create_item("t1")

    assert Tasks.from_dict(project.to_dict()) == project
    assert project != Tasks(name="other")


def test_an_item_is_rebuilt_as_the_class_its_data_names():
    """A project holding a subclass could be written and not read: the extra fields were rejected."""
    project = Tasks(name="p")
    project.add_item(UrgentProjectTask(name="u", fee=5.0))

    restored = Tasks.from_dict(project.to_dict())

    assert type(restored.get_item("u")) is UrgentProjectTask
    assert restored.get_item("u").fee == 5.0


def test_a_project_that_declares_no_item_type_still_reads_its_own_file():
    class Loose(Project):
        def create_item(self, item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None:
            self.add_item(ProjectTask(name=item_code, isactive=isactive))

    project = Loose(name="p")
    project.create_item("t1")

    assert type(Loose.from_dict(project.to_dict()).get_item("t1")) is ProjectTask


def test_data_naming_a_type_the_project_does_not_hold_is_refused():
    class Unrelated(BaseEntity):
        size: int = 1

    data = dict(Tasks(name="p").to_dict())
    data["items"] = {"x": dict(Unrelated(name="x").to_dict())}

    # Named at the boundary, rather than as a type failure from the container further in.
    with pytest.raises(errors.SerializationError, match="is not a ProjectTask"):
        Tasks.from_dict(data)


def test_a_project_has_a_fingerprint_and_a_revision():
    project = Tasks(name="p")
    project.create_item("t1")

    before = project.fingerprint()
    project.get_item("t1").effort = 9.0

    assert project.fingerprint() != before
    assert project.revision >= 0


def test_the_shape_of_a_saved_project_is_unchanged():
    """Files written by earlier versions still read, so the keys stay exactly these."""
    project = Tasks(name="p")
    project.create_item("t1")

    assert sorted(dict(project.to_dict())) == ["items", "name"]


def test_a_rule_about_the_project_is_checked_on_every_change():
    from msb_arch import invariant

    class Guarded(Tasks):
        @invariant("a project needs at least one task")
        def _not_empty(self) -> bool:
            return len(self.get_items()) > 0

    with pytest.raises(errors.InvariantError):
        Guarded(name="empty")

    project = Guarded(name="g", items={"t1": ProjectTask(name="t1")})
    for change in (lambda: project.remove_item("t1"),
                   lambda: project.remove_all(),
                   lambda: project.drop_active()):
        with pytest.raises(errors.InvariantError):
            change()
        assert [item.name for item in project.get_items()] == ["t1"]

    project.create_item("t2")
    project.remove_item("t2")
    assert [item.name for item in project.get_items()] == ["t1"]


def test_get_items_means_the_same_on_a_project_as_on_a_container():
    """One handler written for both used to walk objects in one case and names in the other."""
    project = Tasks(name="p")
    project.create_item("t1")
    project.create_item("t2")

    assert [item.name for item in project.get_items()] == ["t1", "t2"]
    assert sorted(project.get_all()) == ["t1", "t2"]
    assert project.get_all()["t1"] is project.get_item("t1")


def test_a_handler_written_for_a_container_walks_a_project_the_same_way():
    from msb_arch import BaseContainer

    class Basket(BaseContainer[ProjectTask]):
        pass

    basket = Basket(name="b")
    basket.add(ProjectTask(name="t1"))
    project = Tasks(name="p")
    project.create_item("t1")

    def total_effort(holder):
        return sum(item.effort for item in holder.get_items())

    assert total_effort(basket) == total_effort(project)


def test_a_request_reaches_an_item_through_the_project():
    """`inspect(collection, name=..., ...)` means the same for a project as for a container."""
    from msb_arch import Manipulator

    class Shop(Manipulator):
        pass

    project = Tasks(name="p")
    project.create_item("t1")
    shop = Shop(base_classes=[ProjectTask, Tasks])

    assert shop.inspect(project, name="t1", get="effort") == 1.0

    shop.configure(project, name="t1", set={"params": {"effort": 5.0}})
    assert project.get_item("t1").effort == 5.0

    refused = shop.inspect(project, name="absent", get="effort", raise_on_error=False)
    assert refused.ok is False
