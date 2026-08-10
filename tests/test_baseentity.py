import pytest
from unittest.mock import patch, MagicMock
from typing import (Callable,
                    Dict,
                    Any,
                    List,
                    Literal,
                    Optional,
                    Sequence,
                    Set,
                    Tuple,
                    Type,
                    Union)
from msb_arch.base.baseentity import BaseEntity, CYCLIC_REFERENCE
from msb_arch.errors import TypeValidationError


class TestEntity(BaseEntity):
    value: int
    optional_value: Any = None


class GenericEntity(BaseEntity):
    """Entity covering every generic form supported by `_validate_type`."""
    tags: List[int]
    mapping: Dict[str, List[int]]
    deep: Dict[str, List[Dict[str, int]]]
    pair: Tuple[str, int]
    many: Tuple[int, ...]
    labels: Set[str]
    optional_text: Optional[str]
    number_or_text: Union[int, str]
    piped: int | str
    mode: Literal["fast", "slow"]
    handler: Callable[[int], str]
    entity_class: Type[BaseEntity]
    sequence: Sequence[int]
    plain_list: list
    anything: Any


@pytest.fixture
def test_entity():
    return TestEntity(name="test_entity", value=42, optional_value="hello")


@pytest.fixture
def test_entity_with_cache():
    return TestEntity(name="test_entity", value=42, use_cache=True)


class TestBaseEntityInit:
    @patch('msb_arch.base.serializable.logger')
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

    @pytest.mark.parametrize("invalid_value", ["string", 1.5, []])
    def test_init_invalid_value_type(self, invalid_value):
        with pytest.raises(TypeError):
            TestEntity(name="test", value=invalid_value)

    def test_init_none_is_allowed_for_any_attribute_but_name(self):
        # 'value' used to be rejected purely because of its name; only 'name' is mandatory.
        entity = TestEntity(name="test", value=None)
        assert entity.value is None
        with pytest.raises(TypeError):
            TestEntity(name=None, value=42)

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

    @patch('msb_arch.base.baseentity.logger')
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

    @patch('msb_arch.base.baseentity.logger')
    def test_get_logs(self, mock_logger, test_entity):
        test_entity.get("value")
        mock_logger.debug.assert_called()


class TestBaseEntityActivateDeactivate:
    @patch('msb_arch.base.serializable.logger')
    def test_activate(self, mock_logger, test_entity):
        test_entity.deactivate()
        test_entity.activate()
        assert test_entity.isactive is True
        mock_logger.debug.assert_called()

    @patch('msb_arch.base.serializable.logger')
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
        # Should not raise: None is accepted for every attribute except 'name'.
        test_entity._validate_type("value", None, int)

    def test_validate_type_none_rejected_for_name(self, test_entity):
        with pytest.raises(TypeError, match="cannot be None"):
            test_entity._validate_type("name", None, str)

    @pytest.mark.parametrize("value,expected_type", [
        ([1, 2, 3], list),
        ({"key": "value"}, dict),
        (42, int),
    ])
    def test_validate_type_complex(self, test_entity, value, expected_type):
        test_entity._validate_type("test", value, expected_type)


class TestBaseEntityValidateTypeGenerics:
    """Structural validation of parameterized type hints, nested to any depth."""

    @pytest.mark.parametrize("field,value", [
        ("tags", [1, 2, 3]),
        ("tags", []),
        ("tags", [1, None, 3]),
        ("mapping", {"a": [1, 2]}),
        ("mapping", {}),
        ("deep", {"a": [{"b": 1}]}),
        ("pair", ("a", 1)),
        ("many", (1, 2, 3)),
        ("many", ()),
        ("labels", {"a", "b"}),
        ("optional_text", "text"),
        ("number_or_text", 5),
        ("number_or_text", "five"),
        ("piped", "text"),
        ("mode", "fast"),
        ("handler", len),
        ("entity_class", TestEntity),
        ("sequence", [1, 2]),
        ("plain_list", [1, "mixed", None]),
        ("anything", object()),
    ])
    def test_accepts_matching_value(self, field, value):
        entity = GenericEntity(name="generic", **{field: value})
        assert entity.get(field) == value or entity.get(field) is value

    @pytest.mark.parametrize("field,value", [
        ("tags", ["a"]),
        ("tags", [1, 3.5]),
        ("tags", "not_a_list"),
        ("mapping", {"a": ["x"]}),
        ("mapping", {1: [1]}),
        ("deep", {"a": [{"b": "x"}]}),
        ("pair", ("a", "b")),
        ("pair", ("a", 1, 2)),
        ("many", (1, "x")),
        ("labels", {1}),
        ("optional_text", 5),
        ("number_or_text", 1.5),
        ("piped", []),
        ("mode", "medium"),
        ("handler", 5),
        ("entity_class", int),
        ("sequence", 5),
        ("plain_list", "not_a_list"),
    ])
    def test_rejects_mismatching_value(self, field, value):
        with pytest.raises(TypeError):
            GenericEntity(name="generic", **{field: value})

    def test_none_is_accepted_for_every_generic_field(self):
        entity = GenericEntity(name="generic")
        assert entity.tags is None
        assert entity.mapping is None
        assert entity.mode is None

    def test_error_message_points_at_the_nested_element(self):
        with pytest.raises(TypeError, match="Item in list 'tags'"):
            GenericEntity(name="generic", tags=["a"])
        with pytest.raises(TypeError, match="Key in 'mapping'"):
            GenericEntity(name="generic", mapping={1: [1]})

    def test_validation_applies_on_assignment_and_set(self):
        entity = GenericEntity(name="generic", tags=[1])
        with pytest.raises(TypeError):
            entity.tags = ["a"]
        with pytest.raises(TypeError):
            entity.set({"tags": ["a"]})
        with pytest.raises(TypeError):
            entity["tags"] = ["a"]
        entity.tags = [7]
        assert entity.tags == [7]


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

    def test_cleared_entity_can_still_be_serialized_and_restored(self, test_entity):
        # clear() nulls every attribute, so a None-valued payload must round-trip.
        test_entity.clear()
        restored = TestEntity.from_dict(test_entity.to_dict())
        assert restored.value is None
        assert restored.to_dict() == test_entity.to_dict()

    def test_cleared_entity_can_still_be_cloned(self, test_entity):
        test_entity.clear()
        assert test_entity.clone().to_dict() == test_entity.to_dict()


class TestBaseEntityCyclicReferences:
    """A reference back into the structure is marked, not followed."""

    def test_two_node_cycle_terminates(self):
        class Node(BaseEntity):
            peer: 'Node'

        first = Node(name='first', peer=None)
        second = Node(name='second', peer=first)
        first.peer = second

        data = first.to_dict()
        assert data['peer']['name'] == 'second'
        assert data['peer']['peer'] == CYCLIC_REFERENCE

    def test_self_reference_is_marked(self):
        class Node(BaseEntity):
            peer: 'Node'

        node = Node(name='node', peer=None)
        node.peer = node
        assert node.to_dict()['peer'] == CYCLIC_REFERENCE

    def test_three_node_cycle_terminates(self):
        class Node(BaseEntity):
            peer: 'Node'

        first = Node(name='first', peer=None)
        second = Node(name='second', peer=None)
        third = Node(name='third', peer=first)
        second.peer = third
        first.peer = second

        data = first.to_dict()
        assert data['peer']['peer']['peer'] == CYCLIC_REFERENCE

    def test_a_shared_reference_is_serialized_once(self):
        class Leaf(BaseEntity):
            tag: str

        class Holder(BaseEntity):
            left: Leaf
            right: Leaf

        shared = Leaf(name='shared', tag='x')
        holder = Holder(name='holder', left=shared, right=shared)
        data = holder.to_dict()
        assert data['left']['tag'] == 'x'
        assert data['right'] == CYCLIC_REFERENCE


class TestBaseEntityCacheInvalidation:
    """A cached serialization must not survive a change anywhere below it."""

    def test_mutating_a_nested_entity_passed_to_the_constructor(self):
        class Inner(BaseEntity):
            v: int

        class Outer(BaseEntity):
            inner: Inner

        outer = Outer(name='outer', inner=Inner(name='inner', v=1), use_cache=True)
        assert outer.to_dict()['inner']['v'] == 1
        outer.inner.v = 42
        assert outer.to_dict()['inner']['v'] == 42

    def test_mutating_a_nested_entity_assigned_afterwards(self):
        class Inner(BaseEntity):
            v: int

        class Outer(BaseEntity):
            inner: Inner

        outer = Outer(name='outer', use_cache=True)
        outer.inner = Inner(name='inner', v=1)
        assert outer.to_dict()['inner']['v'] == 1
        outer.inner.v = 7
        assert outer.to_dict()['inner']['v'] == 7

    def test_invalidation_reaches_the_root_of_a_deep_chain(self):
        class Third(BaseEntity):
            v: int

        class Second(BaseEntity):
            child: Third

        class First(BaseEntity):
            child: Second

        leaf = Third(name='third', v=1)
        root = First(name='first', child=Second(name='second', child=leaf, use_cache=True),
                     use_cache=True)
        assert root.to_dict()['child']['child']['v'] == 1
        leaf.v = 5
        assert root.to_dict()['child']['child']['v'] == 5

    def test_the_owner_is_held_weakly(self):
        import gc
        import weakref

        class Inner(BaseEntity):
            v: int

        class Outer(BaseEntity):
            inner: Inner

        inner = Inner(name='inner', v=1)
        outer = Outer(name='outer', inner=inner)
        ref = weakref.ref(outer)
        del outer
        gc.collect()
        assert ref() is None
        inner.v = 2  # invalidation must cope with a dead owner
        assert inner.v == 2

    def test_cached_result_is_the_same_mapping(self):
        entity = TestEntity(name='cached', value=1, use_cache=True)
        assert entity.to_dict() is entity.to_dict()


class TestBaseEntityInternalFields:
    """Underscore-prefixed fields are framework state and must stay out of the public surface."""

    def test_clear_keeps_internal_fields(self, test_entity):
        # _type_cache used to be nulled on the instance, shadowing the class-level cache.
        test_entity.clear()
        assert isinstance(test_entity._type_cache, dict)
        assert test_entity._use_cache is False

    def test_equality_ignores_internal_fields(self, test_entity):
        other = TestEntity.from_dict(test_entity.to_dict())
        other._cached_to_dict = {"stale": True}
        assert other == test_entity

    def test_cleared_entities_compare_equal_after_a_round_trip(self, test_entity):
        test_entity.clear()
        assert TestEntity.from_dict(test_entity.to_dict()) == test_entity

    def test_repr_shows_only_public_attributes(self, test_entity):
        repr_str = repr(test_entity)
        assert "value=42" in repr_str
        for internal in ("_type_cache", "_cached_to_dict", "_use_cache"):
            assert internal not in repr_str


class TestBaseEntityInvalidateCache:
    def test_invalidate_cache(self, test_entity_with_cache):
        test_entity_with_cache._cached_to_dict = {"test": "data"}
        test_entity_with_cache._invalidate_cache()
        assert test_entity_with_cache._cached_to_dict is None


def _build_module(module_name, source):
    """Compile `source` into a fresh importable module, as if it were a separate file."""
    import sys
    import types
    module = types.ModuleType(module_name)
    module.__dict__['__name__'] = module_name
    sys.modules[module_name] = module
    exec(compile(source, module_name, 'exec'), module.__dict__)
    for attribute in vars(module).values():
        if isinstance(attribute, type):
            attribute.__module__ = module_name
    return module


class TestBaseEntityResolveType:
    def test_resolve_type_basic(self):
        resolved = TestEntity._resolve_type(int)
        assert resolved == int

    def test_resolve_type_forward_ref(self):
        class Referenced(BaseEntity):
            tag: str

        class Referring(BaseEntity):
            peer: 'Referenced'

        Referring._lookup_type_name = classmethod(lambda cls, name, path="": Referenced)
        assert Referring._resolve_type('Referenced') is Referenced

    def test_type_cache_is_per_class(self):
        assert TestEntity._type_cache is not BaseEntity._type_cache
        assert GenericEntity._type_cache is not TestEntity._type_cache

    def test_same_name_in_two_modules_does_not_collide(self):
        # A cache shared across the hierarchy and keyed by name used to make the second
        # module's class fail validation against the first module's class of the same name.
        source = (
            "from msb_arch.base.baseentity import BaseEntity\n"
            "class Node(BaseEntity):\n"
            "    tag: str\n"
            "class Holder(BaseEntity):\n"
            "    peer: 'Node'\n"
        )
        first = _build_module('msb_test_module_a', source)
        second = _build_module('msb_test_module_b', source)

        assert first.Node is not second.Node
        first.Holder(name='a', peer=first.Node(name='na', tag='A'))
        second.Holder(name='b', peer=second.Node(name='nb', tag='B'))

    def test_a_type_hint_naming_a_framework_symbol_prefers_the_local_class(self):
        source = (
            "from msb_arch.base.baseentity import BaseEntity\n"
            "class Any(BaseEntity):\n"
            "    tag: str\n"
            "class Uses(BaseEntity):\n"
            "    field: 'Any'\n"
        )
        module = _build_module('msb_test_module_shadow', source)
        module.Uses(name='u', field=module.Any(name='a', tag='x'))
        with pytest.raises(TypeError):
            module.Uses(name='u', field=123)


class TestBaseEntityPolymorphicFromDict:
    """Nested entities are restored as the class named in their serialized payload."""

    def test_nested_user_type_is_restored(self):
        class Leaf(BaseEntity):
            tag: str

        class Holder(BaseEntity):
            child: Leaf

        holder = Holder(name='h', child=Leaf(name='l', tag='x'))
        restored = Holder.from_dict(holder.to_dict())
        assert isinstance(restored.child, Leaf)
        assert restored.child.tag == 'x'

    def test_subclass_stored_under_a_base_annotation_keeps_its_type(self):
        class Leaf(BaseEntity):
            tag: str

        class SpecialLeaf(Leaf):
            extra: int

        class Holder(BaseEntity):
            child: Leaf

        holder = Holder(name='h', child=SpecialLeaf(name='s', tag='y', extra=7))
        restored = Holder.from_dict(holder.to_dict())
        assert isinstance(restored.child, SpecialLeaf)
        assert restored.child.extra == 7

    def test_ambiguous_type_name_is_reported(self):
        source = (
            "from msb_arch.base.baseentity import BaseEntity\n"
            "class Duplicated(BaseEntity):\n"
            "    v: int\n"
        )
        _build_module('msb_test_dup_a', source)
        _build_module('msb_test_dup_b', source)

        class Referrer(BaseEntity):
            child: BaseEntity

        payload = {'name': 'r', 'child': {'name': 'd', 'isactive': True,
                                          'type': 'Duplicated', 'v': 1}}
        with pytest.raises(TypeError, match="Ambiguous type 'Duplicated'"):
            Referrer.from_dict(payload)

    def test_unknown_type_falls_back_to_the_annotation(self):
        class Leaf(BaseEntity):
            tag: str

        class Holder(BaseEntity):
            child: Leaf

        payload = {'name': 'h', 'isactive': True,
                   'child': {'name': 'l', 'isactive': True, 'type': 'NeverDefined', 'tag': 'z'}}
        restored = Holder.from_dict(payload)
        assert isinstance(restored.child, Leaf)


class TestBaseEntitySetattr:
    @patch('msb_arch.base.serializable.logger')
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


class TestBaseEntityLifetime:
    @patch('msb_arch.base.baseentity.logger')
    def test_del(self, mock_logger, test_entity):
        # Just ensure no error
        del test_entity
        mock_logger.error.assert_not_called()

    def test_entity_is_collected_when_dropped(self):
        import gc
        import weakref
        entity = TestEntity(name="temporary", value=1)
        ref = weakref.ref(entity)
        del entity
        gc.collect()
        assert ref() is None

    def test_dropping_one_reference_leaves_the_other_usable(self):
        # clear() used to run from __del__, so a shared entity could be wiped while a
        # second reference to it was still live.
        import gc
        entity = TestEntity(name="shared", value=42)
        alias = entity
        del entity
        gc.collect()
        assert alias.value == 42

class TestBaseEntityHashing:
    """Defining __eq__ without __hash__ used to make every entity unhashable."""

    def test_entity_can_go_into_a_set(self, test_entity):
        assert len({test_entity}) == 1

    def test_equal_entities_hash_equal(self):
        first = TestEntity(name="same", value=1)
        second = TestEntity(name="same", value=1)
        assert first == second
        assert hash(first) == hash(second)
        assert len({first, second}) == 1

    def test_unequal_entities_stay_distinct(self):
        first = TestEntity(name="same", value=1)
        second = TestEntity(name="same", value=2)
        assert first != second
        assert len({first, second}) == 2

    def test_entity_works_as_a_dictionary_key(self):
        key = TestEntity(name="key", value=1)
        lookup = TestEntity(name="key", value=1)
        assert {key: "stored"}[lookup] == "stored"

    def test_entities_of_different_classes_do_not_collide(self):
        assert hash(TestEntity(name="x", value=1)) != hash(GenericEntity(name="x"))


class TestBaseEntityRegistryLifetime:
    """The class registry must not keep classes alive on its own."""

    def test_a_dynamic_class_is_released(self):
        import gc
        from msb_arch.base.baseentity import EntityMeta

        created = type("EphemeralEntity", (BaseEntity,), {"__annotations__": {"v": int}})
        assert EntityMeta.registered_classes("EphemeralEntity") == [created]
        del created
        gc.collect()
        assert EntityMeta.registered_classes("EphemeralEntity") == []

    def test_a_live_class_stays_resolvable(self):
        import gc
        from msb_arch.base.baseentity import EntityMeta

        gc.collect()
        assert TestEntity in EntityMeta.registered_classes("TestEntity")

    def test_registry_lookup_is_ordered(self):
        from msb_arch.base.baseentity import EntityMeta

        names = EntityMeta.registered_classes("TestEntity")
        assert names == sorted(names, key=lambda c: (c.__module__ or "", c.__qualname__))


class TestBaseEntityMultipleOwners:
    """An entity stored without copying belongs to every container holding it."""

    def test_every_owner_is_invalidated(self):
        from msb_arch.base.basecontainer import BaseContainer

        class Owned(BaseEntity):
            v: int

        class Box(BaseContainer[Owned]):
            pass

        item = Owned(name="shared", v=1)
        first = Box(name="first", use_cache=True)
        second = Box(name="second", use_cache=True)
        first.add(item, copy_items=False)
        second.add(item, copy_items=False)
        assert first.to_dict()["items"]["shared"]["v"] == 1
        assert second.to_dict()["items"]["shared"]["v"] == 1

        item.v = 99
        assert first.to_dict()["items"]["shared"]["v"] == 99
        assert second.to_dict()["items"]["shared"]["v"] == 99

    def test_a_dead_owner_is_forgotten(self):
        import gc
        from msb_arch.base.basecontainer import BaseContainer

        class Owned(BaseEntity):
            v: int

        class Box(BaseContainer[Owned]):
            pass

        item = Owned(name="shared", v=1)
        keeper = Box(name="keeper")
        temporary = Box(name="temporary")
        keeper.add(item, copy_items=False)
        temporary.add(item, copy_items=False)
        assert len(item._parents) == 2

        del temporary
        gc.collect()
        item.v = 2                      # invalidation prunes the dead reference
        assert len(item._parents) == 1

    def test_an_unowned_entity_tracks_nothing(self):
        entity = TestEntity(name="orphan", value=1)
        entity.value = 2
        assert entity.__dict__.get("_parents") is None


# --- the numeric tower ---------------------------------------------------------------------

class NumericEntity(BaseEntity):
    """An entity whose numbers are declared the way anyone declares numbers."""
    scalar: float
    pair: Tuple[float, float]
    many: List[float]
    mapping: Dict[str, float]
    maybe: Optional[float]
    either: Union[float, str]
    whole: int


def test_an_int_is_accepted_where_a_float_is_declared():
    """PEP 484's numeric tower, which every type checker follows.

    This came from a real report: adding a space telescope failed with "Item 0 in tuple
    'pitch_range' must be of type <class 'float'>, got <class 'int'>" because the range was
    written `(0, 90)`. That is how anyone writes a range of degrees.
    """
    entity = NumericEntity(name="n", scalar=1, pair=(0, 90), many=[1, 2],
                           mapping={"a": 1}, maybe=5, either=7)

    assert entity.scalar == 1
    assert entity.pair == (0, 90)


def test_a_widened_int_is_not_quietly_turned_into_a_float():
    """Accepting a value is not the same as changing it."""
    entity = NumericEntity(name="n", scalar=1)
    assert isinstance(entity.scalar, int), "the value the caller passed is the value it keeps"


def test_a_float_is_still_rejected_where_a_whole_number_is_declared():
    """The tower widens in one direction only. An annotation asking for an int means it."""
    with pytest.raises(TypeValidationError):
        NumericEntity(name="n", whole=3.5)


def test_a_string_is_still_rejected_where_a_float_is_declared():
    """The widening must not have opened the door generally."""
    with pytest.raises(TypeValidationError):
        NumericEntity(name="n", scalar="1")
    with pytest.raises(TypeValidationError):
        NumericEntity(name="n", pair=(0, "90"))


def test_the_widening_survives_every_route_to_an_attribute():
    """There are three: the constructor, `set`, and item assignment. The first uses a compiled
    fast path and the others do not, which is how the first fix reached only half of them."""
    entity = NumericEntity(name="n", scalar=1.0)

    entity.set({"scalar": 2})
    assert entity.scalar == 2

    entity["scalar"] = 3
    assert entity.scalar == 3


def test_an_int_where_a_float_is_declared_round_trips():
    """It has to survive being written and read, or the widening only moves the failure."""
    entity = NumericEntity(name="n", scalar=1, pair=(0, 90))
    restored = NumericEntity.from_dict(entity.to_dict())

    assert restored.scalar == 1
    assert restored.pair == (0, 90)
