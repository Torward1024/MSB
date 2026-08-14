# test_readonly_cache.py
"""A cached serialization is a snapshot, and a snapshot does not change under you.

With `use_cache=True` the same mapping comes back from every `to_dict` call, so a caller who
changed it changed the cache -- for itself and for everyone else holding it, with no error and no
sign. The documentation said "treat it as read only", which is a rake with a label on it.
"""
import copy
import json
import pickle
import pytest

from msb_arch import BaseContainer, BaseEntity
from msb_arch.base.serializable import ReadOnlyMapping
from msb_arch.errors import SerializationError


class Part(BaseEntity):
    price: float
    tags: list


class Parts(BaseContainer[Part]):
    pass


@pytest.fixture
def box() -> Parts:
    box = Parts(name="box", use_cache=True)
    box.add(Part(name="bolt", price=4.5, tags=["fastener"], use_cache=True))
    return box


# --- the writes are gone ---------------------------------------------------------------------------

def test_writing_to_a_cached_mapping_raises_instead_of_corrupting_it(box):
    data = box.to_dict()

    with pytest.raises(SerializationError):
        data["items"] = {}
    with pytest.raises(SerializationError):
        del data["name"]
    with pytest.raises(SerializationError):
        data.update({"name": "other"})
    with pytest.raises(SerializationError):
        data.pop("name")
    with pytest.raises(SerializationError):
        data.setdefault("extra", 1)
    with pytest.raises(SerializationError):
        data.clear()

    assert box.to_dict()["name"] == "box"


def test_it_is_also_a_type_error_so_the_builtin_catch_still_works(box):
    with pytest.raises(TypeError):
        box.to_dict()["name"] = "other"


def test_the_whole_tree_is_read_only_not_just_the_top(box):
    data = box.to_dict()

    with pytest.raises(SerializationError):
        data["items"]["bolt"]["price"] = 99.0

    assert box.to_dict()["items"]["bolt"]["price"] == 4.5


def test_a_nested_list_is_read_only_too(box):
    """A list inside a cached mapping is as much part of the cache as the mappings are."""
    tags = box.to_dict()["items"]["bolt"]["tags"]

    assert tags == ["fastener"]
    with pytest.raises(SerializationError):
        tags.append("extra")
    with pytest.raises(SerializationError):
        tags[0] = "other"
    with pytest.raises(SerializationError):
        tags.pop()

    assert box.to_dict()["items"]["bolt"]["tags"] == ["fastener"]
    assert list(tags) + ["extra"] == ["fastener", "extra"]      # copy it to change it
    assert json.loads(json.dumps(box.to_dict()))["items"]["bolt"]["tags"] == ["fastener"]


# --- everything else works exactly as before -------------------------------------------------------

def test_it_is_a_dict_and_serialises(box):
    data = box.to_dict()

    assert isinstance(data, dict)
    assert json.loads(json.dumps(data))["name"] == "box"
    assert data == json.loads(json.dumps(data))
    assert {**data}["name"] == "box"
    assert data["items"]["bolt"]["price"] == 4.5
    assert sorted(data.keys())[0] == "isactive"


def test_it_round_trips_through_from_dict(box):
    restored = Parts.from_dict(box.to_dict())

    assert restored == box
    assert restored.get("bolt").price == 4.5


def test_copying_it_gives_something_writable(box):
    data = box.to_dict()

    editable = dict(data)
    editable["name"] = "changed"                    # the copy is a plain dictionary

    assert type(copy.copy(data)) is dict
    assert type(copy.deepcopy(data)) is dict
    assert type(pickle.loads(pickle.dumps(data))) is dict

    deep = copy.deepcopy(data)
    deep["items"]["bolt"]["price"] = 99.0           # and so is everything inside it
    assert box.to_dict()["items"]["bolt"]["price"] == 4.5


def test_without_caching_nothing_is_frozen():
    """Nothing else holds that mapping, so there is nothing to protect."""
    box = Parts(name="box", use_cache=False)
    box.add(Part(name="bolt", price=4.5, tags=[], use_cache=False))

    data = box.to_dict()
    data["extra"] = True                            # an ordinary dictionary, as it always was

    assert type(data) is dict
    assert "extra" not in box.to_dict()


def test_a_write_to_the_object_still_replaces_the_snapshot(box):
    first = box.to_dict()
    assert first["items"]["bolt"]["price"] == 4.5

    box.get("bolt").price = 6.0
    second = box.to_dict()

    assert second["items"]["bolt"]["price"] == 6.0
    assert isinstance(second, ReadOnlyMapping)


def test_an_already_frozen_item_is_not_rebuilt(box):
    """An item that caches hands up a frozen mapping, and the container leaves it as it is."""
    bolt = box.get("bolt")
    item_snapshot = bolt.to_dict()

    assert box.to_dict()["items"]["bolt"] is item_snapshot


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
