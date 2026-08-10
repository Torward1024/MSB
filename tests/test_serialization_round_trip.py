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
from typing import Dict, FrozenSet, List, Optional, Set, Tuple, Union

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

def test_a_class_that_has_not_versioned_itself_writes_no_version():
    """The default must be invisible.

    Writing the key always put it into everybody's data for a feature most models never use,
    and broke every hand-written `from_dict` override that rejected what it did not recognise
    -- which is what a careful override does. A class at version 1 now serializes exactly as
    it did before versioning existed.
    """
    assert SCHEMA_FIELD not in full_rig().to_dict()


def test_a_class_that_has_versioned_itself_says_so():
    class Versioned(BaseEntity):
        SCHEMA_VERSION = 3
        value: int

        @classmethod
        def migrate(cls, data, from_version):
            return data

    assert Versioned(name="v", value=1).to_dict()[SCHEMA_FIELD] == 3


def test_a_hand_written_from_dict_override_still_works():
    """What broke downstream: an override that builds its class from the keys it knows."""
    class Strict(BaseEntity):
        value: int

        @classmethod
        def from_dict(cls, data):
            known = {"name", "isactive", "type", "value"}
            unexpected = set(data) - known
            if unexpected:
                raise AssertionError(f"unexpected keys in serialized data: {unexpected}")
            return cls(name=data["name"], value=data["value"])

    assert Strict.from_dict(Strict(name="s", value=7).to_dict()).value == 7


def test_data_from_the_same_version_needs_no_migration():
    assert through_json(full_rig(), Rig).name == "r1"


def test_data_with_no_version_is_read_as_version_one():
    """Everything written before versioning existed, which must keep loading."""
    payload = full_rig().to_dict()
    payload.pop(SCHEMA_FIELD, None)
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


# --- B9: data MSB did not write -----------------------------------------------------------

class Sensor(BaseEntity):
    unit: str


class Camera(BaseEntity):
    pixels: int


class LookAlike(BaseEntity):
    """The same shape as `Sensor`, so nothing about the data distinguishes the two."""
    unit: str


class Station(BaseEntity):
    primary: Sensor
    devices: List[Sensor]
    lookup: Dict[str, Sensor]


FOREIGN = {
    "name": "S1", "isactive": True,
    "primary": {"name": "p", "unit": "K"},
    "devices": [{"name": "d1", "unit": "V"}],
    "lookup": {"a": {"name": "a", "unit": "A"}},
}


def test_json_without_a_type_field_loads_from_the_annotation():
    """Data from another system carries no `type`, so the declared type has to answer."""
    station = Station.from_dict(FOREIGN)
    assert isinstance(station.primary, Sensor)
    assert isinstance(station.devices[0], Sensor)
    assert isinstance(station.lookup["a"], Sensor)


def test_a_container_of_foreign_entities_loads():
    class Stations(BaseContainer[Station]):
        pass

    box = Stations.from_dict({"name": "box", "isactive": True, "items": {"S1": FOREIGN}})
    assert isinstance(box.get("S1"), Station)


def test_a_union_picks_the_member_whose_shape_fits():
    class Slot(BaseEntity):
        device: Union[Sensor, Camera]

    assert isinstance(Slot.from_dict({"name": "s", "device": {"name": "d", "pixels": 12}}).device,
                      Camera)
    assert isinstance(Slot.from_dict({"name": "s", "device": {"name": "d", "unit": "K"}}).device,
                      Sensor)


def test_a_discriminator_decides_where_the_shapes_cannot():
    """Two members of one shape are indistinguishable, and order is not an answer."""
    class Tagged(BaseEntity):
        DISCRIMINATORS = {"device": "kind"}
        device: Union[Sensor, LookAlike]

    tagged = Tagged.from_dict({"name": "t", "device": {"name": "d", "unit": "K",
                                                       "kind": "LookAlike"}})
    assert isinstance(tagged.device, LookAlike)


def test_a_discriminator_reaches_inside_a_collection():
    class TaggedMany(BaseEntity):
        DISCRIMINATORS = {"devices": "kind"}
        devices: List[Union[Sensor, LookAlike]]

    many = TaggedMany.from_dict({"name": "t", "devices": [{"name": "d", "unit": "K",
                                                           "kind": "LookAlike"}]})
    assert isinstance(many.devices[0], LookAlike)


# --- mapping keys -------------------------------------------------------------------------

class Dish(BaseEntity):
    """`Dict[float, float]` is how a real instrument table is spelled: frequency to value."""
    sefd: Dict[float, float]
    counts: Dict[int, str]
    flags: Dict[bool, str]
    labels: Dict[str, float]


def test_a_mapping_keyed_by_a_number_survives_json():
    """JSON has only string keys, so without restoring them from the annotation a
    `Dict[float, float]` could not round-trip at all -- the keys came back as strings and
    validation rejected them. Found by a downstream project that keeps instrument tables
    exactly this way."""
    dish = Dish(name="d", sefd={1420.0: 350.0, 8400.0: 500.0}, counts={1: "one"},
                flags={True: "yes"}, labels={"gain": 1.0})
    restored = through_json(dish, Dish)

    assert restored.sefd == {1420.0: 350.0, 8400.0: 500.0}
    assert all(isinstance(key, float) for key in restored.sefd)
    assert restored == dish


@pytest.mark.parametrize("field, key_type", [
    ("sefd", float), ("counts", int), ("flags", bool), ("labels", str),
])
def test_each_declared_key_type_comes_back(field, key_type):
    dish = Dish(name="d", sefd={1.0: 1.0}, counts={1: "one"}, flags={False: "no"},
                labels={"a": 1.0})
    restored = through_json(dish, Dish)
    assert all(isinstance(key, key_type) for key in getattr(restored, field))


def test_a_key_that_cannot_be_converted_is_left_alone():
    """So the error names the field, rather than coming from the conversion."""
    payload = {"name": "d", "isactive": True, "type": "Dish",
               "sefd": {"not a number": 1.0}, "counts": {}, "flags": {}, "labels": {}}
    with pytest.raises(errors.TypeValidationError, match="sefd"):
        Dish.from_dict(payload)
