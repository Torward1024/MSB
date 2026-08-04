"""Serialization that survives JSON, and data that carries its own version.

Two claims are tested here, both of which the framework made and neither of which held.

The first is a faithful round trip. `to_dict` descended into an entity held *directly* by a
field and stopped there, so an entity inside a list or a dict was left in the mapping as a
live object: `json.dumps` refused it, and nothing could restore it. Sets and frozensets went
out as themselves, which JSON has no notion of, and a tuple that survived `dumps` as a list
came back and was rejected for not being a tuple.

The second is that a file written today can be read tomorrow. Serialized data now carries the
version of the class that wrote it, and a class that changes shape says how to read the old
one.

The tests go through real `json.dumps`/`json.loads` rather than comparing dictionaries, since
a dictionary comparison is exactly what failed to notice any of this.
"""
import json
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import pytest

from msb_arch import BaseContainer, BaseEntity, errors
from msb_arch.base.serializable import SCHEMA_FIELD


class Part(BaseEntity):
    mass: float


class Rig(BaseEntity):
    bands: Set[str]
    span: Tuple[float, float]
    locked: FrozenSet[int]
    table: Dict[str, List[float]]
    single: Part
    many: List[Part]
    keyed: Dict[str, Part]
    note: Optional[str]


class Rigs(BaseContainer[Rig]):
    pass


def full_rig():
    return Rig(name="r1", bands={"K", "Q"}, span=(1.0, 2.0), locked=frozenset({4, 3}),
               table={"gain": [1.0, 2.0]}, single=Part(name="a", mass=1.0),
               many=[Part(name="b", mass=2.0)], keyed={"c": Part(name="c", mass=3.0)},
               note=None)


def through_json(obj, restore_as):
    """A real round trip. Comparing dictionaries would not have caught any of this."""
    return restore_as.from_dict(json.loads(json.dumps(obj.to_dict())))


# --- B12: the round trip ------------------------------------------------------------------

def test_an_entity_survives_json():
    restored = through_json(full_rig(), Rig)
    assert restored.bands == {"K", "Q"}
    assert restored.span == (1.0, 2.0)
    assert restored.locked == frozenset({3, 4})
    assert restored.table == {"gain": [1.0, 2.0]}
    assert restored.note is None


@pytest.mark.parametrize("field, expected", [
    ("bands", set), ("span", tuple), ("locked", frozenset), ("table", dict),
])
def test_the_declared_type_comes_back_not_the_json_one(field, expected):
    """JSON has only lists and objects, so the annotation is what restores the real type."""
    assert type(getattr(through_json(full_rig(), Rig), field)) is expected


def test_entities_inside_collections_are_serialized():
    """They used to be left in the mapping as live objects, so nothing could be written."""
    payload = full_rig().to_dict()
    assert isinstance(payload["many"][0], dict)
    assert isinstance(payload["keyed"]["c"], dict)
    assert payload["many"][0]["mass"] == 2.0


def test_entities_inside_collections_come_back_as_entities():
    restored = through_json(full_rig(), Rig)
    assert isinstance(restored.many[0], Part)
    assert restored.many[0].mass == 2.0
    assert isinstance(restored.keyed["c"], Part)
    assert restored.keyed["c"].mass == 3.0


def test_a_container_of_such_entities_survives_json():
    box = Rigs(name="box")
    box.add(full_rig(), copy_items=False)
    restored = through_json(box, Rigs)
    assert restored.get("r1").keyed["c"].mass == 3.0


def test_a_set_serializes_in_a_stable_order():
    """Its iteration order is arbitrary, so without this the same object writes differently
    each run and any later hash, diff or comparison of the output is meaningless."""
    rig = full_rig()
    assert rig.to_dict()["bands"] == ["K", "Q"]
    assert rig.to_dict()["locked"] == [3, 4]


def test_a_subclass_in_a_collection_keeps_its_type():
    class HeavyPart(Part):
        density: float

    class Crate(BaseEntity):
        contents: List[Part]

    crate = Crate(name="c", contents=[HeavyPart(name="h", mass=9.0, density=2.0)])
    restored = through_json(crate, Crate)
    assert isinstance(restored.contents[0], HeavyPart)
    assert restored.contents[0].density == 2.0


def test_a_cycle_through_a_collection_terminates():
    class Node(BaseEntity):
        peers: List["Node"]

    first = Node(name="first", peers=[])
    second = Node(name="second", peers=[first])
    first.peers.append(second)

    payload = first.to_dict()                     # must not recurse forever
    assert json.dumps(payload)


# --- B4: the schema version ---------------------------------------------------------------

def test_serialized_data_carries_the_version_that_wrote_it():
    assert full_rig().to_dict()[SCHEMA_FIELD] == 1


def test_data_from_the_same_version_needs_no_migration():
    assert through_json(full_rig(), Rig).name == "r1"


def test_data_with_no_version_is_read_as_version_one():
    """Everything written before versioning existed, which must keep loading."""
    payload = full_rig().to_dict()
    del payload[SCHEMA_FIELD]
    assert Rig.from_dict(payload).name == "r1"


def test_a_class_that_changed_shape_without_saying_how_refuses_the_old_data():
    class Moved(BaseEntity):
        SCHEMA_VERSION = 2
        diameter: float

    old = {"name": "d", "isactive": True, "type": "Moved", SCHEMA_FIELD: 1, "size": 25.0}
    with pytest.raises(errors.SerializationError, match="version 1"):
        Moved.from_dict(old)


def test_migrate_brings_older_data_forward():
    class Renamed(BaseEntity):
        SCHEMA_VERSION = 2
        diameter: float

        @classmethod
        def migrate(cls, data, from_version):
            if from_version == 1:
                data["diameter"] = data.pop("size")
            return data

    old = {"name": "d", "isactive": True, "type": "Renamed", SCHEMA_FIELD: 1, "size": 25.0}
    assert Renamed.from_dict(old).diameter == 25.0


def test_a_migration_is_not_run_when_the_version_matches():
    class Guarded(BaseEntity):
        SCHEMA_VERSION = 3
        value: int

        @classmethod
        def migrate(cls, data, from_version):
            raise AssertionError("migrate must not be called for matching versions")

    assert through_json(Guarded(name="g", value=1), Guarded).value == 1
