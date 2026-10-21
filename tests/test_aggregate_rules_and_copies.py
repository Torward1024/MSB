# test_aggregate_rules_and_copies.py
"""Two promises an aggregate makes: what saves can be loaded, and a copy belongs to its copier.

Both came from downstream, where a model of a brain was being put on MSB.

A rule over a whole aggregate -- "every edge joins zones that exist" -- is checked when the
aggregate itself changes, when it is built or restored, and whenever the application asks. It is
*not* checked after every change inside a member it holds, and deliberately: measured here, one
such check over 512 members costs 106 us against 7.8 us for adding a member, so checking after
every change would make building the aggregate quadratic. What that left open was worse than the
cost, though: a state could be written and then refuse to load, because restoring checked the
rules and writing did not. `save` checks them now, so the two cannot disagree.

The copies are a separate thing found along the way: `deepcopy` treats a weak reference as
atomic, so a copied subtree kept pointing at the objects the original belonged to.
"""
import copy
import json

import pytest

from msb_arch import BaseContainer, BaseEntity, Manipulator, Project, errors, invariant
from msb_arch.base.serializable import Serializable


class Col(BaseEntity):
    weight: float = 0.0


class Cols(BaseContainer[Col]):
    pass


class Edge(BaseEntity):
    source: str = ""
    target: str = ""


class Edges(BaseContainer[Edge]):
    pass


class Cortex(Project):
    _item_type = Serializable

    def create_item(self, item_code: str = "ITEM", isactive: bool = True) -> None:
        raise NotImplementedError("a cortex is assembled, not generated")

    @invariant("every edge joins zones that exist")
    def _edges_resolve(self) -> bool:
        held = {item.name: item for item in self.get_items()}
        zones, edges = held.get("zones"), held.get("edges")
        if zones is None or edges is None:
            return True
        names = set(zones.get_all())
        return all(edge.source in names and edge.target in names for edge in edges.get_items())


class Core(Manipulator):
    pass


@pytest.fixture
def cortex():
    assembled = Cortex(name="brain")
    zones = Cols(name="zones")
    zones.add(Col(name="z0"))
    assembled.add_item(zones)
    assembled.add_item(Edges(name="edges"))
    return assembled


@pytest.fixture
def core(cortex):
    return Core(base_classes=[Col, Cols, Edge, Edges, Cortex], managing_object=cortex)


# --- what saves can be loaded -------------------------------------------------------------------

def test_a_sound_aggregate_saves_and_loads(core, cortex, tmp_path):
    path = str(tmp_path / "brain.json")

    core.save(cortex, path=path)

    assert core.load(cortex, path=path) == cortex


def test_a_state_that_breaks_the_rule_refuses_to_save(core, cortex, tmp_path):
    """The asymmetry that mattered: restoring checked the rules, writing did not, so a snapshot
    could be written and then refuse to open -- for a model being trained, the whole run."""
    path = str(tmp_path / "brain.json")
    cortex.get_item("edges").add(Edge(name="bad", source="z0", target="nowhere"))

    with pytest.raises(errors.InvariantError, match="every edge joins"):
        core.save(cortex, path=path)

    assert not pytest.importorskip("pathlib").Path(path).exists()


def test_the_refusal_comes_back_as_a_failed_response(core, cortex, tmp_path):
    cortex.get_item("edges").add(Edge(name="bad", source="z0", target="nowhere"))

    answer = core.save(cortex, path=str(tmp_path / "brain.json"), raise_on_error=False)

    assert answer.ok is False and "every edge joins" in answer.error


def test_after_the_repair_it_saves_again(core, cortex, tmp_path):
    path = str(tmp_path / "brain.json")
    cortex.get_item("edges").add(Edge(name="bad", source="z0", target="nowhere"))
    with pytest.raises(errors.InvariantError):
        core.save(cortex, path=path)

    cortex.get_item("edges").remove("bad")
    core.save(cortex, path=path)

    assert core.load(cortex, path=path) == cortex


def test_a_change_inside_a_held_member_is_not_checked_there(cortex):
    """The documented limit, and the reason: it would make assembly quadratic.

    A rule over several held members is checked when the aggregate changes, on build, on restore,
    at save, and on demand. An application that wants a guard after every structural change has
    the interceptor chain, which sees every request.
    """
    cortex.get_item("edges").add(Edge(name="bad", source="z0", target="nowhere"))

    assert cortex.get_item("edges").has_item("bad")
    with pytest.raises(errors.InvariantError):
        cortex.check_invariants()


def test_an_aggregate_rule_is_still_checked_when_the_aggregate_itself_changes(cortex):
    broken = Edges(name="edges")
    broken.add(Edge(name="bad", source="z0", target="nowhere"))

    with pytest.raises(errors.InvariantError):
        cortex.set_item("edges", broken)

    assert cortex.get_item("edges").get_all() == {}


# --- a copy belongs to its copier ----------------------------------------------------------------

def test_a_copied_item_has_exactly_one_owner():
    """`add` copies by default, and the copy used to keep the original's owner as well, so an
    address built from the ownership graph could walk into the tree the copy came from."""
    class Shelf(BaseContainer[Cols]):
        pass

    original = Cols(name="box")
    original.add(Col(name="c0"))
    shelf = Shelf(name="shelf")
    shelf.add(original)

    held = shelf.get("box")
    owners = [reference() for reference in held.get("c0").__dict__["_parents"].values()]

    assert [owner for owner in owners if owner is not None] == [held]


def test_an_address_of_a_copied_item_leads_back_to_it():
    class Shelf(BaseContainer[Cols]):
        pass

    shelf = Shelf(name="shelf")
    shelf.add(Cols(name="box"))
    shelf.get("box").add(Col(name="c0"))
    manipulator = Manipulator(base_classes=[Col, Cols, Shelf], managing_object=shelf)
    target = shelf.get("box").get("c0")

    address = manipulator.address(target)

    assert address == ["shelf", "box", "c0"]
    assert manipulator.locate(address) is target


def test_a_deepcopy_is_detached_and_keeps_its_own_cache_fresh():
    cached = Cols(name="cached", use_cache=True)
    cached.add(Col(name="c0", use_cache=True))
    cached.to_dict()

    twin = copy.deepcopy(cached)
    twin.to_dict()
    twin.get("c0").weight = 9.0

    assert dict(twin.to_dict())["items"]["c0"]["weight"] == 9.0
    assert dict(cached.to_dict())["items"]["c0"]["weight"] == 0.0
    assert twin.__dict__.get("_parents") in (None, {})


def test_an_address_round_trips_through_a_nested_project():
    """A project holds its items in a container of its own making. Naming that container in an
    address made the address unfollowable: nothing can ask a project for it by name."""
    class Zone(Project):
        _item_type = Col

        def create_item(self, item_code: str = "ITEM", isactive: bool = True) -> None:
            self.add_item(Col(name=item_code))

    class Zones(BaseContainer[Zone]):
        pass

    class Nest(Project):
        _item_type = Serializable

        def create_item(self, item_code: str = "ITEM", isactive: bool = True) -> None:
            raise NotImplementedError

    root = Nest(name="nested")
    zones = Zones(name="zones")
    inner = Zone(name="v1")
    inner.create_item("c0")
    zones.add(inner, copy_items=False)
    root.add_item(zones)
    manipulator = Manipulator(base_classes=[Col, Zone, Zones, Nest], managing_object=root)
    target = root.get_item("zones").get("v1").get_item("c0")

    address = manipulator.address(target)

    assert address == ["nested", "zones", "v1", "c0"]
    assert manipulator.locate(address) is target


def test_an_address_recorded_before_the_fix_still_resolves():
    """A journal on disk names the project's own container. Those sessions stay replayable."""
    class Zone(Project):
        _item_type = Col

        def create_item(self, item_code: str = "ITEM", isactive: bool = True) -> None:
            self.add_item(Col(name=item_code))

    class Zones(BaseContainer[Zone]):
        pass

    class Nest(Project):
        _item_type = Serializable

        def create_item(self, item_code: str = "ITEM", isactive: bool = True) -> None:
            raise NotImplementedError

    root = Nest(name="nested")
    zones = Zones(name="zones")
    inner = Zone(name="v1")
    inner.create_item("c0")
    zones.add(inner, copy_items=False)
    root.add_item(zones)
    manipulator = Manipulator(base_classes=[Col, Zone, Zones, Nest], managing_object=root)
    target = root.get_item("zones").get("v1").get_item("c0")

    # The container is named in the middle of the path, where nothing can be skipped past it.
    legacy = ["nested", "nested_items", "zones", "v1", "v1_items", "c0"]

    assert manipulator.locate(legacy) is target
    assert manipulator.locate(manipulator.address(target)) is target


def test_a_recorded_session_replays_onto_a_nested_shape(tmp_path):
    """The whole reason addressing matters: the journal is replayed by address."""
    from msb_arch import RequestJournal

    class Zone(Project):
        _item_type = Col

        def create_item(self, item_code: str = "ITEM", isactive: bool = True) -> None:
            self.add_item(Col(name=item_code))

    class Zones(BaseContainer[Zone]):
        pass

    class Nest(Project):
        _item_type = Serializable

        def create_item(self, item_code: str = "ITEM", isactive: bool = True) -> None:
            raise NotImplementedError

    def shape():
        root = Nest(name="nested")
        zones = Zones(name="zones")
        zone = Zone(name="v1")
        zone.create_item("c0")
        zones.add(zone, copy_items=False)
        root.add_item(zones)
        return root

    recorded = shape()
    recorder = Manipulator(base_classes=[Col, Zone, Zones, Nest], managing_object=recorded)
    journal = RequestJournal()
    recorder.add_interceptor(journal)
    recorder.configure(recorded.get_item("zones").get("v1").get_item("c0"),
                       set={"params": {"weight": 7.0}})
    recorder.remove_interceptor(journal)

    fresh = shape()
    replaying = Manipulator(base_classes=[Col, Zone, Zones, Nest], managing_object=fresh)
    outcome = replaying.replay(json.loads(json.dumps(journal.entries)))

    assert outcome.failed == []
    assert fresh.get_item("zones").get("v1").get_item("c0").weight == 7.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
