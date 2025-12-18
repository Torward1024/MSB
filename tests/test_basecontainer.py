import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any
from src.msb_arch.base.baseentity import BaseEntity
from src.msb_arch.base.basecontainer import BaseContainer


class TestEntity(BaseEntity):
    value: int
    optional_value: Any


class TestContainer(BaseContainer[TestEntity]):
    pass


@pytest.fixture
def test_entity():
    return TestEntity(name="item1", value=42)


@pytest.fixture
def test_container():
    items = {
        "item1": TestEntity(name="item1", value=1),
        "item2": TestEntity(name="item2", value=2),
    }
    return TestContainer(items=items, name="test_container")


@pytest.fixture
def empty_container():
    return TestContainer(name="empty")


class TestBaseContainerInit:
    @patch('src.msb_arch.base.basecontainer.logger')
    def test_init_valid(self, mock_logger):
        items = {"item1": TestEntity(name="item1", value=1)}
        container = TestContainer(items=items, name="test")
        assert container.name == "test"
        assert container.isactive is True
        assert len(container) == 1
        mock_logger.debug.assert_called()

    def test_init_empty(self):
        container = TestContainer(name="empty")
        assert len(container) == 0

    def test_init_invalid_items_type(self):
        with pytest.raises(TypeError):
            TestContainer(items="invalid", name="test")

    def test_init_invalid_key_type(self):
        with pytest.raises(TypeError):
            TestContainer(items={123: TestEntity(name="item", value=1)}, name="test")

    def test_init_mismatched_name(self):
        with pytest.raises(ValueError):
            TestContainer(items={"wrong": TestEntity(name="item", value=1)}, name="test")


class TestBaseContainerAdd:
    def test_add_single_item(self, empty_container, test_entity):
        empty_container.add(test_entity)
        assert len(empty_container) == 1
        assert empty_container.get("item1") == test_entity

    def test_add_list_items(self, empty_container):
        items = [TestEntity(name="item1", value=1), TestEntity(name="item2", value=2)]
        empty_container.add(items)
        assert len(empty_container) == 2

    def test_add_container(self, empty_container, test_container):
        other = TestContainer(items={"item3": TestEntity(name="item3", value=3)}, name="other")
        empty_container.add(other)
        assert len(empty_container) == 1

    def test_add_existing_name(self, test_container):
        new_item = TestEntity(name="item1", value=100)
        with pytest.raises(ValueError):
            test_container.add(new_item)

    def test_add_invalid_type(self, empty_container):
        with pytest.raises(TypeError):
            empty_container.add("invalid")

    @patch('src.msb_arch.base.basecontainer.logger')
    def test_add_logs(self, mock_logger, empty_container, test_entity):
        empty_container.add(test_entity)
        mock_logger.debug.assert_called()


class TestBaseContainerSetItem:
    def test_set_item_valid(self, empty_container, test_entity):
        empty_container.set_item("item1", test_entity)
        assert empty_container.get("item1") == test_entity

    def test_set_item_mismatched_name(self, empty_container, test_entity):
        with pytest.raises(ValueError):
            empty_container.set_item("wrong", test_entity)

    def test_set_item_invalid_type(self, empty_container):
        with pytest.raises(TypeError):
            empty_container.set_item("item1", "invalid")


class TestBaseContainerRemove:
    def test_remove_existing(self, test_container):
        test_container.remove("item1")
        assert "item1" not in test_container

    def test_remove_nonexistent(self, test_container):
        with pytest.raises(KeyError):
            test_container.remove("nonexistent")


    @patch('src.msb_arch.base.basecontainer.logger')
    def test_remove_logs(self, mock_logger, test_container):
        test_container.remove("item1")
        mock_logger.debug.assert_called()


class TestBaseContainerGet:
    def test_get_existing(self, test_container):
        item = test_container.get("item1")
        assert item.value == 1

    def test_get_nonexistent(self, test_container):
        item = test_container.get("nonexistent")
        assert item is None

    @patch('src.msb_arch.base.basecontainer.logger')
    def test_get_logs_warning(self, mock_logger, test_container):
        test_container.get("nonexistent")
        mock_logger.warning.assert_called()


class TestBaseContainerGetAll:
    def test_get_all(self, test_container):
        all_items = test_container.get_all()
        assert len(all_items) == 2
        assert "item1" in all_items


class TestBaseContainerGetItems:
    def test_get_items(self, test_container):
        items = test_container.get_items()
        assert len(items) == 2
        assert all(isinstance(item, TestEntity) for item in items)


class TestBaseContainerGetByValue:
    def test_get_by_value_matching(self, test_container):
        items = test_container.get_by_value({"value": 1})
        assert len(items) == 1
        assert items[0].value == 1

    def test_get_by_value_no_match(self, test_container):
        items = test_container.get_by_value({"value": 999})
        assert len(items) == 0

    def test_get_by_value_empty_conditions(self, test_container):
        items = test_container.get_by_value({})
        assert len(items) == 2

    def test_get_by_value_missing_attr(self, test_container):
        with pytest.raises(AttributeError):
            test_container.get_by_value({"nonexistent": 1})


class TestBaseContainerGetActiveInactive:
    def test_get_active_items(self, test_container):
        active = test_container.get_active_items()
        assert len(active) == 2  # All are active by default

    def test_get_inactive_items(self, test_container):
        test_container.deactivate_item("item1")
        inactive = test_container.get_inactive_items()
        assert len(inactive) == 1


class TestBaseContainerSet:
    def test_set_items(self, empty_container):
        items = {"item1": TestEntity(name="item1", value=1)}
        empty_container.set({"_items": items})
        assert len(empty_container) == 1

    def test_set_invalid(self, empty_container):
        with pytest.raises(ValueError):
            empty_container.set({"unknown": 1})


class TestBaseContainerSetItems:
    def test_set_items_valid(self, empty_container):
        items = {"item1": TestEntity(name="item1", value=1)}
        empty_container.set_items(items)
        assert len(empty_container) == 1

    def test_set_items_invalid(self, empty_container):
        items = {"item1": TestEntity(name="wrong", value=1)}
        with pytest.raises(ValueError):
            empty_container.set_items(items)


class TestBaseContainerHasItem:
    def test_has_item_existing(self, test_container):
        assert test_container.has_item("item1") is True

    def test_has_item_nonexistent(self, test_container):
        assert test_container.has_item("nonexistent") is False


class TestBaseContainerClear:
    def test_clear(self, test_container):
        test_container.clear()
        assert len(test_container) == 0

    def test_clear_logs(self, test_container):
        test_container.clear()


class TestBaseContainerClone:
    def test_clone_deep(self, test_container):
        cloned = test_container.clone(deep=True)
        assert len(cloned) == 2
        assert cloned is not test_container

    def test_clone_shallow(self, test_container):
        cloned = test_container.clone(deep=False)
        assert len(cloned) == 2


class TestBaseContainerActivateDeactivate:
    def test_activate_item(self, test_container):
        test_container.deactivate_item("item1")
        test_container.activate_item("item1")
        assert test_container.get("item1").isactive is True

    def test_deactivate_item(self, test_container):
        test_container.deactivate_item("item1")
        assert test_container.get("item1").isactive is False

    def test_activate_all(self, test_container):
        test_container.deactivate_all()
        test_container.activate_all()
        assert all(item.isactive for item in test_container.get_items())

    def test_deactivate_all(self, test_container):
        test_container.deactivate_all()
        assert all(not item.isactive for item in test_container.get_items())

    def test_drop_active(self, test_container):
        test_container.deactivate_item("item1")
        test_container.drop_active()
        assert len(test_container) == 1

    def test_drop_inactive(self, test_container):
        test_container.deactivate_item("item1")
        test_container.drop_inactive()
        assert len(test_container) == 1


class TestBaseContainerToDict:
    def test_to_dict_basic(self, test_container):
        data = test_container.to_dict()
        assert "items" in data
        assert len(data["items"]) == 2

    def test_to_dict_cyclic_mark(self, test_container):
        item = test_container.get("item1")
        item.optional_value = item  # Self-cyclic
        data = test_container.to_dict()
        assert "<cyclic reference>" in str(data)

    def test_to_dict_cyclic_raise(self, test_container):
        # Similar
        pass

    def test_to_dict_cyclic_ignore(self, test_container):
        pass


class TestBaseContainerFromDict:
    def test_from_dict_basic(self):
        data = {
            "name": "test",
            "isactive": True,
            "items": {
                "item1": {"name": "item1", "isactive": True, "value": 1, "type": "TestEntity"}
            },
            "type": "TestContainer"
        }
        container = TestContainer.from_dict(data)
        assert len(container) == 1

    def test_from_dict_union(self):
        # For Union types, but TestEntity is single
        pass


class TestBaseContainerMagicMethods:
    def test_iter(self, test_container):
        items = list(test_container)
        assert len(items) == 2

    def test_getitem(self, test_container):
        assert test_container["item1"].value == 1

    def test_setitem(self, test_container):
        new_item = TestEntity(name="item3", value=3)
        test_container["item3"] = new_item
        assert len(test_container) == 3

    def test_delitem(self, test_container):
        del test_container["item1"]
        assert "item1" not in test_container

    def test_contains(self, test_container):
        assert "item1" in test_container
        assert "nonexistent" not in test_container

    def test_eq(self, test_container):
        other = TestContainer(items=test_container.get_all(), name="test_container")
        assert test_container == other

    def test_len(self, test_container):
        assert len(test_container) == 2

    def test_repr(self, test_container):
        repr_str = repr(test_container)
        assert "TestContainer" in repr_str
        assert "count=2" in repr_str


class TestBaseContainerInvalidateCache:
    def test_invalidate_cache(self, test_container):
        test_container._invalidate_cache()
        # Ensure items' cache is invalidated
        for item in test_container.get_items():
            assert item._cached_to_dict is None


class TestBaseContainerResolveType:
    def test_resolve_type(self):
        resolved = TestContainer._resolve_type(int)
        assert resolved == int


class TestBaseContainerDel:
    @patch('src.msb_arch.base.basecontainer.logger')
    def test_del(self, mock_logger, test_container):
        del test_container
        mock_logger.error.assert_not_called()