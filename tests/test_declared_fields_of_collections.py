# test_declared_fields_of_collections.py
"""A container and a project own their declared fields, exactly as an entity does.

Reported from downstream, where a model of a brain was being put on MSB. A container that
declares `role: str` wrote the field and then dropped it on the way back in, restoring the
class's default over what the file said -- and `__eq__` left those fields out, so every
round-trip test of such a class passed while the values were being lost. A project was worse: it
never wrote its own fields at all, in the one class the documentation calls "the thing an
application writes to a file".
"""
import json
from typing import Dict, List, Literal, Optional

import pytest

from msb_arch import BaseContainer, BaseEntity, Project, errors, invariant


class Col(BaseEntity):
    weight: float = 0.0


class Tagged(BaseContainer[Col]):
    role: Literal["encoder", "associative"] = "associative"
    cells: int = 2048
    labels: List[str] = []
    notes: Optional[str] = None


class Zone(Project):
    _item_type = Col

    role: Literal["encoder", "associative"] = "associative"
    cells: int = 2048
    lookup: Dict[str, int] = {}

    def create_item(self, item_code: str = "ITEM", isactive: bool = True) -> None:
        self.add_item(Col(name=item_code, isactive=isactive))


# --- a container -----------------------------------------------------------------------------------

def test_a_container_takes_its_fields_at_construction():
    box = Tagged(name="box", role="encoder", cells=512)

    assert (box.role, box.cells) == ("encoder", 512)


def test_a_container_round_trips_its_fields_through_json():
    box = Tagged(name="box", role="encoder", cells=512, labels=["a"], notes="hand written")
    box.add(Col(name="c0", weight=1.0))

    restored = Tagged.from_dict(json.loads(json.dumps(dict(box.to_dict()))))

    assert (restored.role, restored.cells) == ("encoder", 512)
    assert restored.labels == ["a"] and restored.notes == "hand written"
    assert restored == box


def test_two_containers_differing_only_in_a_field_are_not_equal():
    """What hid the loss: equality looked at the name, the flag and the items, and stopped."""
    one = Tagged(name="box", role="encoder")
    other = Tagged(name="box", role="associative")

    assert one != other


def test_a_declared_list_on_a_container_belongs_to_the_object():
    first, second = Tagged(name="a"), Tagged(name="b")

    first.labels.append("x")

    assert first.labels == ["x"] and second.labels == []


# --- a project --------------------------------------------------------------------------------------

def test_a_project_writes_its_own_fields():
    zone = Zone(name="v1", role="encoder", cells=512)

    written = dict(zone.to_dict())

    assert written["role"] == "encoder" and written["cells"] == 512


def test_a_project_round_trips_its_fields_through_json():
    zone = Zone(name="v1", role="encoder", cells=512, lookup={"c0": 1})
    zone.create_item("c0")

    restored = Zone.from_dict(json.loads(json.dumps(dict(zone.to_dict()))))

    assert (restored.role, restored.cells) == ("encoder", 512)
    assert restored.lookup == {"c0": 1}
    assert restored == zone


def test_two_projects_differing_only_in_a_field_are_not_equal():
    assert Zone(name="v1", role="encoder") != Zone(name="v1", role="associative")


def test_a_project_keeps_the_file_shape_it_had_when_it_declares_nothing():
    """Nothing extra in everybody's data: a project with no fields of its own writes the same two
    keys it always did, and `isactive` only once it is no longer the default."""
    class Plain(Project):
        _item_type = Col

        def create_item(self, item_code: str = "ITEM", isactive: bool = True) -> None:
            self.add_item(Col(name=item_code))

    plain = Plain(name="p")
    assert sorted(dict(plain.to_dict())) == ["items", "name"]

    plain.isactive = False
    assert sorted(dict(plain.to_dict())) == ["isactive", "items", "name"]
    assert Plain.from_dict(dict(plain.to_dict())).isactive is False


def test_a_file_written_before_the_fields_existed_still_reads():
    restored = Zone.from_dict({"name": "v1", "items": {}})

    assert restored.role == "associative" and restored.cells == 2048


# --- set, which a project did not have --------------------------------------------------------------

def test_a_project_writes_a_group_of_fields_at_once():
    """`@invariant` says a rule over two fields is satisfied by writing them together, through
    `set`. A project had no `set`, so such a rule could not be satisfied at all."""
    class Banded(Zone):
        @invariant("cells must fit the role")
        def _fits(self) -> bool:
            return self.cells <= (512 if self.role == "encoder" else 4096)

    banded = Banded(name="v1", role="associative", cells=4096)

    banded.set({"role": "encoder", "cells": 512})
    assert (banded.role, banded.cells) == ("encoder", 512)

    with pytest.raises(errors.InvariantError):
        banded.set({"role": "encoder", "cells": 4096})
    assert (banded.role, banded.cells) == ("encoder", 512)


def test_a_container_writes_a_group_of_fields_at_once():
    """It used to check its rules between the fields of one group, and keep what it had written."""
    class Banded(Tagged):
        @invariant("cells must fit the role")
        def _fits(self) -> bool:
            return self.cells <= (512 if self.role == "encoder" else 4096)

    banded = Banded(name="box", role="associative", cells=4096)

    banded.set({"role": "encoder", "cells": 512})
    assert (banded.role, banded.cells) == ("encoder", 512)

    with pytest.raises(errors.InvariantError):
        banded.set({"role": "associative", "cells": 9000})
    assert (banded.role, banded.cells) == ("encoder", 512)


def test_a_container_still_replaces_its_items_through_set():
    box = Tagged(name="box", role="encoder")
    box.add(Col(name="c0"))

    box.set({"_items": {"c1": Col(name="c1")}, "cells": 256})

    assert sorted(box.get_all()) == ["c1"]
    assert (box.role, box.cells) == ("encoder", 256)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# --- a subclass with a constructor of its own ------------------------------------------------------

class NarrowShelf(BaseContainer[Col]):
    """The common shape downstream: a constructor that names what it takes and nothing more."""

    role: str = "spare"

    def __init__(self, items=None, name=None, isactive=True, use_cache=False):
        super().__init__(items=items, name=name, isactive=isactive, use_cache=use_cache)


class NarrowZone(Project):
    _item_type = Col

    role: str = "spare"

    def __init__(self, name="NARROW", items=None):
        super().__init__(name=name, items=items)

    def create_item(self, item_code: str = "ITEM", isactive: bool = True) -> None:
        self.add_item(Col(name=item_code))


def test_a_container_whose_constructor_is_narrow_still_restores_its_fields():
    """`from_dict` must not hand a class keywords its constructor never asked for.

    Caught by an application downstream whose project declares `__init__(self, name, items)`:
    3.2.0 passed the fields as keywords and every `from_dict` raised `TypeError`. Where the
    constructor cannot take them, they are applied after it -- as one group, so the rules are
    still checked once.
    """
    shelf = NarrowShelf(name="front")
    shelf.role = "main"
    shelf.add(Col(name="c0"))

    restored = NarrowShelf.from_dict(json.loads(json.dumps(dict(shelf.to_dict()))))

    assert restored.role == "main"
    assert restored == shelf


def test_a_project_whose_constructor_is_narrow_still_restores_its_fields():
    zone = NarrowZone(name="v1")
    zone.role = "main"
    zone.create_item("c0")

    restored = NarrowZone.from_dict(json.loads(json.dumps(dict(zone.to_dict()))))

    assert restored.role == "main"
    assert restored == zone


def test_a_narrow_project_restores_an_inactive_flag_too():
    zone = NarrowZone(name="v1")
    zone.isactive = False

    assert NarrowZone.from_dict(dict(zone.to_dict())).isactive is False


def test_a_rule_over_restored_fields_is_checked_once_on_a_narrow_subclass():
    class Banded(NarrowZone):
        capacity: int = 10

        @invariant("capacity must fit the role")
        def _fits(self) -> bool:
            return self.capacity <= (5 if self.role == "main" else 100)

    sound = Banded(name="v1")
    sound.set({"role": "main", "capacity": 5})

    assert Banded.from_dict(dict(sound.to_dict())) == sound

    broken = dict(sound.to_dict())
    broken["capacity"] = 50
    # Restoring wraps what went wrong in `SerializationError` -- data that cannot be read is
    # what the caller asked about -- and carries the rule in the message.
    with pytest.raises(errors.SerializationError, match="capacity must fit the role"):
        Banded.from_dict(broken)
