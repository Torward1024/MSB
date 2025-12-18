import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any
from src.msb_arch.base.baseentity import BaseEntity


class TestEntity(BaseEntity):
    value: int
    optional_value: Any = None


@pytest.fixture
def test_entity():
    return TestEntity(name="test_entity", value=42, optional_value="hello")


@pytest.fixture
def test_entity_with_cache():
    return TestEntity(name="test_entity", value=42, use_cache=True)


class TestBaseEntityInit:
    @patch('src.msb_arch.base.baseentity.logger')
    def test_init_valid(self, mock_logger):
        entity = TestEntity(name="test", value=42)
        assert entity.name == "test"
        assert entity.isactive is True
        assert entity.value == 42
        mock_logger.debug.assert_called_once()

    def test_init_without_optional(self):
        entity = TestEntity(name="test", value=42)
        assert entity.optional_value is None

    @pytest.mark.parametrize("invalid_name", [None, 123, []])
    def test_init_invalid_name_type(self, invalid_name):
        with pytest.raises(TypeError):
            TestEntity(name=invalid_name, value=42)

    def test_init_unknown_attribute(self):
        with pytest.raises(ValueError, match="Unknown attributes"):
            TestEntity(name="test", value=42, unknown=123)

    @pytest.mark.parametrize("invalid_value", ["string", None])
    def test_init_invalid_value_type(self, invalid_value):
        with pytest.raises(TypeError):
            TestEntity(name="test", value=invalid_value)

    def test_init_with_kwargs(self):
        entity = TestEntity(name="test", value=42, optional_value="world")
        assert entity.optional_value == "world"


class TestBaseEntitySet:
    def test_set_valid(self, test_entity):
        test_entity.set({"value": 100})
        assert test_entity.value == 100

    def test_set_unknown_attribute(self, test_entity):
        with pytest.raises(ValueError, match="Unknown attribute"):
            test_entity.set({"unknown": 123})

    def test_set_invalid_type(self, test_entity):
        with pytest.raises(TypeError):
            test_entity.set({"value": "invalid"})

    @patch('src.msb_arch.base.baseentity.logger')
    def test_set_logs(self, mock_logger, test_entity):
        test_entity.set({"value": 100})
        mock_logger.debug.assert_called()


class TestBaseEntityGet:
    def test_get_single_attribute(self, test_entity):
        assert test_entity.get("value") == 42

    def test_get_list_attributes(self, test_entity):
        result = test_entity.get(["value", "optional_value"])
        assert result == {"value": 42, "optional_value": "hello"}

    def test_get_all(self, test_entity):
        result = test_entity.get()
        assert "value" in result
        assert "optional_value" in result

    def test_get_nonexistent_attribute(self, test_entity):
        with pytest.raises(KeyError):
            test_entity.get("nonexistent")

    def test_get_invalid_key_type(self, test_entity):
        with pytest.raises(TypeError):
            test_entity.get(123)

    @patch('src.msb_arch.base.baseentity.logger')
    def test_get_logs(self, mock_logger, test_entity):
        test_entity.get("value")
        mock_logger.debug.assert_called()


class TestBaseEntityActivateDeactivate:
    @patch('src.msb_arch.base.baseentity.logger')
    def test_activate(self, mock_logger, test_entity):
        test_entity.deactivate()
        test_entity.activate()
        assert test_entity.isactive is True
        mock_logger.debug.assert_called()

    @patch('src.msb_arch.base.baseentity.logger')
    def test_deactivate(self, mock_logger, test_entity):
        test_entity.deactivate()
        assert test_entity.isactive is False
        mock_logger.debug.assert_called()


class TestBaseEntityHasAttribute:
    def test_has_attribute_existing(self, test_entity):
        assert test_entity.has_attribute("value") is True

    def test_has_attribute_nonexistent(self, test_entity):
        assert test_entity.has_attribute("nonexistent") is False


class TestBaseEntityClone:
    def test_clone(self, test_entity):
        cloned = test_entity.clone()
        assert cloned.name == test_entity.name
        assert cloned.value == test_entity.value
        assert cloned is not test_entity


class TestBaseEntityToDict:
    def test_to_dict_basic(self, test_entity):
        data = test_entity.to_dict()
        assert data["name"] == "test_entity"
        assert data["isactive"] is True
        assert data["value"] == 42
        assert "type" in data

    def test_to_dict_with_nested(self):
        nested = TestEntity(name="nested", value=10)
        entity = TestEntity(name="parent", value=1, optional_value=nested)
        data = entity.to_dict()
        assert data["optional_value"]["value"] == 10

    def test_to_dict_cyclic_reference(self):
        entity = TestEntity(name="self_ref", value=1)
        entity.optional_value = entity  # cyclic
        data = entity.to_dict()
        assert data["optional_value"] == "<cyclic reference>"

    def test_to_dict_with_cache(self, test_entity_with_cache):
        data1 = test_entity_with_cache.to_dict()
        data2 = test_entity_with_cache.to_dict()
        assert data1 == data2
        # Cache should be used


class TestBaseEntityFromDict:
    def test_from_dict_basic(self):
        data = {"name": "test", "isactive": True, "value": 42, "type": "TestEntity"}
        entity = TestEntity.from_dict(data)
        assert entity.name == "test"
        assert entity.value == 42

    def test_from_dict_with_nested(self):
        data = {
            "name": "parent",
            "isactive": True,
            "value": 1,
            "optional_value": {"name": "nested", "isactive": True, "value": 10, "type": "TestEntity"},
            "type": "TestEntity"
        }
        entity = TestEntity.from_dict(data)
        assert entity.optional_value.value == 10

    def test_from_dict_unknown_attribute(self):
        data = {"name": "test", "unknown": 123, "type": "TestEntity"}
        with pytest.raises(ValueError):
            TestEntity.from_dict(data)


class TestBaseEntityValidateType:
    def test_validate_type_valid(self, test_entity):
        # Should not raise
        test_entity._validate_type("value", 100, int)

    def test_validate_type_invalid(self, test_entity):
        with pytest.raises(TypeError):
            test_entity._validate_type("value", "string", int)

    def test_validate_type_none_allowed(self, test_entity):
        with pytest.raises(TypeError):
            test_entity._validate_type("value", None, int)

    @pytest.mark.parametrize("value,expected_type", [
        ([1, 2, 3], list),
        ({"key": "value"}, dict),
        (42, int),
    ])
    def test_validate_type_complex(self, test_entity, value, expected_type):
        test_entity._validate_type("test", value, expected_type)


class TestBaseEntityMagicMethods:
    def test_getitem(self, test_entity):
        assert test_entity["value"] == 42

    def test_getitem_nonexistent(self, test_entity):
        with pytest.raises(KeyError):
            _ = test_entity["nonexistent"]

    def test_setitem(self, test_entity):
        test_entity["value"] = 100
        assert test_entity.value == 100

    def test_setitem_invalid(self, test_entity):
        with pytest.raises(TypeError):
            test_entity["value"] = "invalid"

    def test_contains(self, test_entity):
        assert "value" in test_entity
        assert "nonexistent" not in test_entity

    def test_eq(self, test_entity):
        other = TestEntity(name="test_entity", value=42, optional_value="hello")
        assert test_entity == other

    def test_eq_different(self, test_entity):
        other = TestEntity(name="other", value=42)
        assert test_entity != other

    def test_repr(self, test_entity):
        repr_str = repr(test_entity)
        assert "TestEntity" in repr_str
        assert "value=42" in repr_str


class TestBaseEntityClear:
    def test_clear(self, test_entity):
        test_entity.clear()
        assert test_entity.value is None
        assert test_entity.optional_value is None


class TestBaseEntityInvalidateCache:
    def test_invalidate_cache(self, test_entity_with_cache):
        test_entity_with_cache._cached_to_dict = {"test": "data"}
        test_entity_with_cache._invalidate_cache()
        assert test_entity_with_cache._cached_to_dict is None


class TestBaseEntityResolveType:
    def test_resolve_type_basic(self):
        resolved = TestEntity._resolve_type(int)
        assert resolved == int

    def test_resolve_type_forward_ref(self):
        # Assuming some forward ref, but for simplicity
        pass  # Skip for now, as it requires more setup


class TestBaseEntitySetattr:
    @patch('src.msb_arch.base.baseentity.logger')
    def test_setattr_valid(self, mock_logger, test_entity):
        test_entity.value = 100
        assert test_entity.value == 100
        mock_logger.debug.assert_called()

    def test_setattr_invalid_type(self, test_entity):
        with pytest.raises(TypeError):
            test_entity.value = "invalid"

    def test_setattr_unknown(self, test_entity):
        with pytest.raises(ValueError):
            test_entity.unknown = 123


class TestBaseEntityDel:
    @patch('src.msb_arch.base.baseentity.logger')
    def test_del(self, mock_logger, test_entity):
        # Just ensure no error
        del test_entity
        mock_logger.error.assert_not_called()