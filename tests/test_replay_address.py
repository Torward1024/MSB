# test_replay_address.py
"""A replayed step must reach the object the session meant, in the model in hand.

Two failures this pins, both of which used to be silent:

- The journal put the *live* object into a replayed step whenever it was still alive, so
  replaying against a fresh model wrote into the model the session was recorded from and left the
  fresh one untouched.
- A step that had lost its object fell back to the recorded name, and a name is unique inside a
  container rather than across a model, so `store/left/bolt` answered for `store/right/bolt`.
"""
import gc
import logging
import pytest

from msb_arch import BaseContainer, BaseEntity, Manipulator, Project, RequestJournal
from msb_arch.model import path_of


class Part(BaseEntity):
    price: float

    def set_price(self, value: float) -> bool:
        self.price = value
        return True


class Parts(BaseContainer[Part]):
    pass


class Shelf(BaseContainer[Parts]):
    pass


class Workshop(Manipulator):
    pass


def _store(name: str = "store") -> Shelf:
    """A model with the same name in two places: `store/left/bolt` and `store/right/bolt`."""
    store = Shelf(name=name)
    for side, price in (("left", 1.0), ("right", 2.0)):
        parts = Parts(name=side)
        parts.add(Part(name="bolt", price=price))
        store.add(parts)
    return store


def _recorded(store: Shelf) -> RequestJournal:
    """Record `configure(store/right/bolt, set_price=42)`.

    The manipulator that recorded it is left to be collected, so a test that drops the model
    really drops it -- a manipulator holds what it manages.
    """
    journal = RequestJournal()
    workshop = Workshop(base_classes=[Part, Parts, Shelf], managing_object=store)
    workshop.add_interceptor(journal)
    workshop.configure(store.get("right").get("bolt"), set_price=42.0)
    return journal


# --- the address itself -------------------------------------------------------------------------

def test_path_of_reads_the_ownership_graph():
    store = _store()
    assert path_of(store.get("right").get("bolt")) == ["store", "right", "bolt"]
    assert path_of(store.get("left").get("bolt")) == ["store", "left", "bolt"]


def test_path_of_an_object_nothing_owns_is_its_name():
    assert path_of(Part(name="loose", price=1.0)) == ["loose"]


def test_path_of_something_that_is_not_a_model_object_is_empty():
    assert path_of("bolt") == []
    assert path_of(None) == []


def test_locate_says_which_one_where_find_cannot():
    store = _store()
    workshop = Workshop(base_classes=[Part, Parts, Shelf], managing_object=store)

    assert workshop.locate(["store", "right", "bolt"]).price == 2.0
    assert workshop.locate(["right", "bolt"]).price == 2.0      # the root segment is optional
    assert workshop.locate(["store", "middle", "bolt"]) is None
    assert workshop.locate([]) is None


def test_find_answers_with_the_first_match_and_stops_there():
    """A convenience lookup, priced like one: it does not walk the rest of the model to check."""
    store = _store()
    workshop = Workshop(base_classes=[Part, Parts, Shelf], managing_object=store)

    assert workshop.find("bolt") is store.get("left").get("bolt")
    assert workshop.find("nothing") is None


# --- what the journal records --------------------------------------------------------------------

def test_an_entry_records_where_the_object_was():
    store = _store()
    journal = _recorded(store)

    entry = journal.entries[-1]
    assert entry["object"] == "bolt"                            # unchanged, for old readers
    assert entry["path"] == ["store", "right", "bolt"]


def test_a_step_carries_no_reference_to_the_recorded_model():
    store = _store()
    journal = _recorded(store)
    fresh = _store()
    replaying = Workshop(base_classes=[Part, Parts, Shelf], managing_object=fresh)

    plan = journal.as_plan(resolve=replaying._recorded_object)

    for step in plan.values():
        assert step["obj"] is fresh.get("right").get("bolt")


# --- the two failures ----------------------------------------------------------------------------

def test_replay_writes_into_the_model_it_is_replayed_against():
    """The recorded model is still alive. It must not be the one that changes."""
    store = _store()
    journal = _recorded(store)
    assert store.get("right").get("bolt").price == 42.0         # the recording did that

    store.get("right").get("bolt").price = 2.0                  # put it back
    fresh = _store()
    replaying = Workshop(base_classes=[Part, Parts, Shelf], managing_object=fresh)

    replaying.replay(journal)

    assert fresh.get("right").get("bolt").price == 42.0
    assert store.get("right").get("bolt").price == 2.0


def test_replay_reaches_the_object_the_session_meant():
    """Nothing of the recorded model is left. The name alone answers with the wrong `bolt`."""
    store = _store()
    journal = _recorded(store)
    del store
    gc.collect()

    fresh = _store()
    replaying = Workshop(base_classes=[Part, Parts, Shelf], managing_object=fresh)

    replaying.replay(journal)

    assert fresh.get("right").get("bolt").price == 42.0
    assert fresh.get("left").get("bolt").price == 1.0


# --- journals written before paths existed -------------------------------------------------------

def test_an_entry_without_a_path_still_replays_by_name(caplog):
    store = _store()
    journal = _recorded(store)
    for entry in journal.entries:
        entry.pop("path", None)
    del store
    gc.collect()

    fresh = _store()
    replaying = Workshop(base_classes=[Part, Parts, Shelf], managing_object=fresh)

    with caplog.at_level(logging.WARNING):
        replaying.replay(journal)

    assert fresh.get("left").get("bolt").price == 42.0          # the first match, as it always was
    assert "2 objects here are called that" in caplog.text      # and it says the name was ambiguous


def test_a_path_that_is_not_in_this_model_says_so(caplog):
    store = _store()
    journal = _recorded(store)
    for entry in journal.entries:
        entry["path"] = ["store", "elsewhere", "bolt"]
    del store
    gc.collect()

    fresh = _store()
    replaying = Workshop(base_classes=[Part, Parts, Shelf], managing_object=fresh)

    with caplog.at_level(logging.WARNING):
        replaying.replay(journal)

    assert "not in this model" in caplog.text
    assert fresh.get("left").get("bolt").price == 42.0          # falls back to the name


def test_a_manipulator_managing_nothing_replays_on_what_the_journal_saw():
    """No model to address against; the live object is the only answer there is."""
    store = _store()
    journal = RequestJournal()
    workshop = Workshop(base_classes=[Part, Parts, Shelf], managing_object=store)
    workshop.add_interceptor(journal)
    workshop.configure(store.get("right").get("bolt"), set_price=42.0)
    workshop.set_managing_object(None)
    workshop.remove_interceptor(journal)
    store.get("right").get("bolt").price = 2.0

    outcome = workshop.replay(journal)

    assert outcome.failed == []
    assert store.get("right").get("bolt").price == 42.0
    assert store.get("left").get("bolt").price == 1.0


def test_a_step_recorded_outside_the_managed_model_still_reaches_its_object():
    """The object was never in the model being replayed against, but it is still alive."""
    loose = Part(name="loose", price=1.0)
    journal = RequestJournal()
    workshop = Workshop(base_classes=[Part, Parts, Shelf], managing_object=_store())
    workshop.add_interceptor(journal)
    workshop.configure(loose, set_price=7.0)
    workshop.remove_interceptor(journal)
    loose.price = 1.0

    workshop.replay(journal)

    assert loose.price == 7.0


def test_as_plan_without_a_resolver_behaves_as_it_did():
    store = _store()
    journal = _recorded(store)

    plan = journal.as_plan()

    assert next(iter(plan.values()))["obj"] is store.get("right").get("bolt")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_locate_addresses_the_model_and_nothing_else():
    """A path names objects. A method or a plain field of the same name is a miss."""
    store = _store()
    workshop = Workshop(base_classes=[Part, Parts, Shelf], managing_object=store)

    assert workshop.locate(["store", "get_items"]) is None
    assert workshop.locate(["store", "right", "bolt", "price"]) is None
    assert workshop.locate(["store", "right", "bolt", "set_price"]) is None


# --- the two shapes a real model actually has ----------------------------------------------------

class Bolt(BaseEntity):
    size: int


class Bolts(BaseContainer[Bolt]):
    pass


class Machine(BaseEntity):
    """An entity holding a container in a *field*, which is how a model names its parts.

    The container has a name of its own -- `bolts_of_press` -- and the field is called `bolts`.
    A path is built from names and `locate` descends by members, so the two have to meet.
    """

    bolts: Bolts


class Works(Project):
    _item_type = Machine

    def create_item(self, **kwargs):
        self.add_item(Machine(name=kwargs.get("name", "machine"),
                              bolts=Bolts(name=f"bolts_of_{kwargs.get('name', 'machine')}")))


def _works() -> Works:
    """`works / press / bolts_of_press / bolt`, with a second machine holding a `bolt` too."""
    works = Works("works")
    for side in ("press", "lathe"):
        works.create_item(name=side)
        works.get_item(side).bolts.add(Bolt(name="bolt", size=1 if side == "press" else 2))
    return works


def test_locate_descends_from_a_project_into_its_items():
    """A `Project` has `get_items` and `get_item`, and no `get`. `locate` asked for `get`, the
    AttributeError was swallowed, and every path rooted at a project died on its first segment
    -- which is every path in an application whose model is a project."""
    works = _works()
    workshop = Workshop(base_classes=[Bolt, Bolts, Machine], managing_object=works)

    assert workshop.locate(["press"]) is works.get_item("press")


def test_locate_follows_a_container_held_in_a_field():
    """`path_of` is built from *object* names and `locate` descends by *member* names. A
    container held in a field has a name of its own, so the two disagreed and the path could
    not be followed."""
    works = _works()
    workshop = Workshop(base_classes=[Bolt, Bolts, Machine], managing_object=works)
    target = works.get_item("press").bolts.get("bolt")

    address = workshop.address(target)
    # `address` reports the ownership graph as it is, and a project owns its items through a
    # container of its own. That container is the top of the path and `locate` starts below it,
    # exactly as it starts below the root's own name.
    assert address[-3:] == ["press", "bolts_of_press", "bolt"]
    assert workshop.locate(address) is target


def test_address_and_locate_are_inverses_on_a_project():
    """What the pair claims. Both machines hold a `bolt`, so a name cannot say which."""
    works = _works()
    workshop = Workshop(base_classes=[Bolt, Bolts, Machine], managing_object=works)

    for side in ("press", "lathe"):
        target = works.get_item(side).bolts.get("bolt")
        assert workshop.locate(workshop.address(target)) is target, side
