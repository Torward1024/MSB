import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any
from msb_arch.base.baseentity import BaseEntity, CYCLIC_REFERENCE
from msb_arch.base.basecontainer import BaseContainer


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
    @patch('msb_arch.base.basecontainer.logger')
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

    @patch('msb_arch.base.basecontainer.logger')
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


    @patch('msb_arch.base.basecontainer.logger')
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

    @patch('msb_arch.base.basecontainer.logger')
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

    def test_from_dict_restores_a_subclass_of_the_item_type(self):
        class SpecialEntity(TestEntity):
            extra: int

        container = TestContainer(name="mixed")
        container.add(TestEntity(name="plain", value=1))
        container.add(SpecialEntity(name="special", value=2, extra=7))

        restored = TestContainer.from_dict(container.to_dict())
        assert type(restored.get("plain")) is TestEntity
        assert type(restored.get("special")) is SpecialEntity
        assert restored.get("special").extra == 7

    def test_from_dict_rejects_a_type_that_is_not_an_item_type(self):
        class Unrelated(BaseEntity):
            value: int

        data = {
            "name": "test",
            "isactive": True,
            "items": {
                "item1": {"name": "item1", "isactive": True, "value": 1, "type": "Unrelated"}
            },
        }
        with pytest.raises(ValueError, match="Invalid type 'Unrelated'"):
            TestContainer.from_dict(data)


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


class TestBaseContainerCyclicReferences:
    """A container that reaches itself is marked, skipped or reported, but never followed."""

    def _self_containing(self):
        container = TestContainer(name="cyclic")
        container.add(TestEntity(name="item1", value=1))
        container._items["itself"] = container
        return container

    def test_mark(self):
        container = self._self_containing()
        items = container.to_dict(handle_cyclic_refs="mark")["items"]
        assert items["itself"] == CYCLIC_REFERENCE
        assert items["item1"]["value"] == 1

    def test_ignore(self):
        container = self._self_containing()
        assert set(container.to_dict(handle_cyclic_refs="ignore")["items"]) == {"item1"}

    def test_raise(self):
        container = self._self_containing()
        with pytest.raises(ValueError, match="Cyclic reference detected"):
            container.to_dict(handle_cyclic_refs="raise")

    def test_invalid_mode_is_rejected(self):
        container = TestContainer(name="plain")
        with pytest.raises(ValueError, match="Invalid handle_cyclic_refs"):
            container.to_dict(handle_cyclic_refs="nonsense")


class TestBaseContainerCacheInvalidation:
    def test_mutating_an_item_invalidates_the_container(self):
        container = TestContainer(name="cached", use_cache=True)
        container.add(TestEntity(name="item1", value=1))
        assert container.to_dict()["items"]["item1"]["value"] == 1
        container.get("item1").value = 99
        assert container.to_dict()["items"]["item1"]["value"] == 99

    def test_mutating_an_item_invalidates_a_nested_container(self):
        class OuterContainer(BaseContainer[TestContainer]):
            pass

        inner = TestContainer(name="inner")
        inner.add(TestEntity(name="item1", value=1))
        outer = OuterContainer(name="outer", use_cache=True)
        outer.add(inner)

        assert outer.to_dict()["items"]["inner"]["items"]["item1"]["value"] == 1
        outer.get("inner").get("item1").value = 5
        assert outer.to_dict()["items"]["inner"]["items"]["item1"]["value"] == 5

    def test_removing_an_item_invalidates_the_container(self):
        container = TestContainer(name="cached", use_cache=True)
        container.add(TestEntity(name="item1", value=1))
        assert set(container.to_dict()["items"]) == {"item1"}
        container.remove("item1")
        assert container.to_dict()["items"] == {}


class TestBaseContainerInvalidateCache:
    def test_invalidate_cache_drops_the_containers_own_cache(self):
        container = TestContainer(name="cached", use_cache=True)
        container.add(TestEntity(name="item1", value=1))
        assert container.to_dict() is container._cached_to_dict
        container._invalidate_cache()
        assert container._cached_to_dict is None

    def test_invalidate_cache_leaves_items_untouched(self):
        # Walking the items would be quadratic, and an item is not stale because its
        # container changed. Adding must therefore not touch the caches already built.
        container = TestContainer(name="cached")
        items = [TestEntity(name=f"item{i}", value=i, use_cache=True) for i in range(5)]
        for item in items:
            container.add(item)
        stored = container.get_items()
        for item in stored:
            item.to_dict()
        assert all(item._cached_to_dict is not None for item in stored)

        container.add(TestEntity(name="late", value=99, use_cache=True))
        assert all(item._cached_to_dict is not None for item in stored)

    def test_add_does_not_scale_with_container_size(self):
        # Guards against reintroducing a per-item walk: adding must not read the
        # attributes of the items already stored.
        container = TestContainer(name="probe")
        for i in range(50):
            container.add(TestEntity(name=f"item{i}", value=i))
        touched = []
        for item in container.get_items():
            item._invalidate_cache = lambda item=item: touched.append(item.name)
        container.add(TestEntity(name="late", value=99))
        assert touched == []


class TestBaseContainerResolveType:
    def test_resolve_type(self):
        resolved = TestContainer._resolve_type(int)
        assert resolved == int


class TestBaseContainerLifetime:
    @patch('msb_arch.base.basecontainer.logger')
    def test_del(self, mock_logger, test_container):
        del test_container
        mock_logger.error.assert_not_called()

    def test_container_is_collected_when_dropped(self):
        import gc
        import weakref
        container = TestContainer(name="temporary")
        container.add(TestEntity(name="item1", value=1))
        ref = weakref.ref(container)
        del container
        gc.collect()
        assert ref() is None

    def test_container_owns_its_mapping(self):
        # The container used to keep the caller's dict by reference and empty it on
        # garbage collection, destroying data the caller still owned.
        import gc
        caller_items = {"item1": TestEntity(name="item1", value=1)}
        container = TestContainer(name="borrowing", items=caller_items)
        del container
        gc.collect()
        assert set(caller_items) == {"item1"}

    def test_clearing_the_container_leaves_the_callers_dict_alone(self):
        caller_items = {"item1": TestEntity(name="item1", value=1)}
        container = TestContainer(name="borrowing", items=caller_items)
        container.clear()
        assert len(container) == 0
        assert set(caller_items) == {"item1"}

class TestBaseContainerHashing:
    def test_container_is_hashable(self, test_container):
        assert len({test_container}) == 1

    def test_equal_containers_hash_equal(self):
        first = TestContainer(name="same")
        second = TestContainer(name="same")
        assert first == second
        assert hash(first) == hash(second)


class TestBaseContainerAddCopySemantics:
    def test_add_copies_by_default(self, empty_container, test_entity):
        empty_container.add(test_entity)
        stored = empty_container.get("item1")
        assert stored is not test_entity
        test_entity.value = 99
        assert stored.value == 42

    def test_add_can_store_the_object_itself(self, empty_container, test_entity):
        empty_container.add(test_entity, copy_items=False)
        assert empty_container.get("item1") is test_entity
        test_entity.value = 99
        assert empty_container.get("item1").value == 99


class TestHierarchySeparation:
    """A container is no longer an entity; both are Serializable."""

    def test_a_container_is_not_an_entity(self):
        from msb_arch.base.serializable import Serializable

        container = TestContainer(name="c")
        assert not isinstance(container, BaseEntity)
        assert isinstance(container, Serializable)

    def test_an_entity_is_not_a_container(self):
        from msb_arch.base.serializable import Serializable

        entity = TestEntity(name="e", value=1)
        assert not isinstance(entity, BaseContainer)
        assert isinstance(entity, Serializable)

    def test_get_means_different_things_without_clashing(self):
        entity = TestEntity(name="e", value=1)
        container = TestContainer(name="c")
        container.add(entity)
        # the entity addresses its attributes, the container its items
        assert entity.get("value") == 1
        assert container.get("e").value == 1
        assert entity.get() == {"name": "e", "isactive": True, "value": 1, "optional_value": None}

    def test_clear_means_different_things_without_clashing(self):
        entity = TestEntity(name="e", value=1)
        container = TestContainer(name="c")
        container.add(entity)
        container.clear()
        assert len(container) == 0
        entity.clear()
        assert entity.value is None
        assert entity.name == "e"

    def test_a_container_nested_in_an_entity_still_serializes(self):
        class Holder(BaseEntity):
            box: TestContainer

        holder = Holder(name="holder", box=TestContainer(name="box"))
        holder.box.add(TestEntity(name="item1", value=7))
        data = holder.to_dict()
        assert data["box"]["items"]["item1"]["value"] == 7

        restored = Holder.from_dict(data)
        assert isinstance(restored.box, TestContainer)
        assert restored.box.get("item1").value == 7

    def test_both_are_hashable(self):
        assert len({TestEntity(name="e", value=1), TestContainer(name="c")}) == 2


class DecoratedEntity(BaseEntity):
    """Mirrors how downstream code overrides to_dict: same signature, extra keys."""
    value: int

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["extra"] = "added by the subclass"
        return data


class DecoratedBox(BaseContainer[DecoratedEntity]):
    pass


class DecoratedHolder(BaseEntity):
    child: DecoratedEntity


class TestSubclassOverridesToDict:
    """A subclass may override to_dict with the signature it has always had.

    Threading the traversal state through a parameter broke every downstream override
    written as `def to_dict(self)`, which is the documented way to write one. The tests
    that existed did not catch it because the container was never populated, so items were
    never serialized through it.
    """

    def test_container_serializes_an_overriding_item(self):
        box = TestContainer(name="box")
        box.add(TestEntity(name="item1", value=1))
        assert box.to_dict()["items"]["item1"]["value"] == 1

    def test_an_overriding_item_keeps_its_additions(self):
        box = DecoratedBox(name="box")
        box.add(DecoratedEntity(name="item1", value=1))
        data = box.to_dict()["items"]["item1"]
        assert data["extra"] == "added by the subclass"
        assert data["value"] == 1

    def test_an_overriding_entity_nested_in_another_entity(self):
        holder = DecoratedHolder(name="holder", child=DecoratedEntity(name="child", value=2))
        assert holder.to_dict()["child"]["extra"] == "added by the subclass"

    def test_handle_cyclic_refs_is_still_positional(self):
        box = TestContainer(name="box")
        box.add(TestEntity(name="item1", value=1))
        assert "items" in box.to_dict("ignore")
        with pytest.raises(ValueError):
            box.to_dict("nonsense")

    def test_traversal_state_does_not_leak_between_calls(self):
        box = TestContainer(name="box")
        box.add(TestEntity(name="item1", value=1))
        first = box.to_dict()
        second = box.to_dict()
        assert first == second
        assert second["items"]["item1"]["value"] == 1

    def test_cycles_still_terminate_with_an_overriding_subclass(self):
        class Node(BaseEntity):
            peer: 'Node'

            def to_dict(self) -> dict:
                data = super().to_dict()
                data["marker"] = True
                return data

        first = Node(name="first", peer=None)
        second = Node(name="second", peer=first)
        first.peer = second
        data = first.to_dict()
        assert data["marker"] is True
        assert data["peer"]["peer"] == CYCLIC_REFERENCE
