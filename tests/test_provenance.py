"""What happened in this session, and whether it changed anything.

Two questions with different costs. `revision` and the journal say *what ran*, for nothing.
Fingerprints say *what actually changed*, for one serialisation each way, and are off by default
for that reason.
"""
import pytest

from msb_arch import BaseContainer, BaseEntity, Manipulator, RequestJournal
from msb_arch.errors import NotFoundError


class Item(BaseEntity):
    value: int


class Items(BaseContainer[Item]):
    pass


@pytest.fixture
def item():
    return Item(name="one", value=1)


@pytest.fixture
def manipulator(item):
    return Manipulator(item, base_classes=[Item, Items])


# --- the fingerprint --------------------------------------------------------------------

def test_the_same_contents_hash_the_same():
    assert Item(name="i", value=1).fingerprint() == Item(name="i", value=1).fingerprint()


def test_different_contents_hash_differently():
    assert Item(name="i", value=1).fingerprint() != Item(name="i", value=2).fingerprint()


def test_the_name_is_part_of_the_contents():
    """Two differently named objects are not the same input to anything."""
    assert Item(name="a", value=1).fingerprint() != Item(name="b", value=1).fingerprint()


def test_a_container_feels_a_change_to_an_item():
    """Where `revision` deliberately stops, this one goes: it is the whole subtree."""
    box = Items(name="box", items={"i": Item(name="i", value=1)})
    before = box.fingerprint()
    box.get("i").value = 2

    assert box.fingerprint() != before


def test_writing_the_same_value_leaves_the_fingerprint_alone(item):
    """The difference from `revision`, which counts writes. This one is about contents."""
    before = item.fingerprint()
    item.value = 1

    assert item.revision == 1
    assert item.fingerprint() == before


def test_it_survives_a_round_trip(item):
    assert Item.from_dict(item.to_dict()).fingerprint() == item.fingerprint()


# --- the session ------------------------------------------------------------------------

def test_the_manipulator_finds_its_own_journal(manipulator, item):
    journal = RequestJournal()
    manipulator.add_interceptor(journal)
    manipulator.inspect(item, get="value")

    assert manipulator.journal() is journal
    assert [entry["operation"] for entry in manipulator.history()] == ["inspect"]


def test_the_history_can_be_narrowed_to_one_object(manipulator, item):
    manipulator.add_interceptor(RequestJournal())
    other = Item(name="two", value=2)
    manipulator.inspect(item, get="value")
    manipulator.inspect(other, get="value")

    assert [entry["object"] for entry in manipulator.history("two")] == ["two"]


def test_asking_for_a_history_nobody_recorded_says_so(manipulator):
    with pytest.raises(NotFoundError):
        manipulator.history()


def test_which_requests_changed_something(manipulator, item):
    """The point of recording fingerprints: reading is not changing, and a journal without
    them cannot tell the difference."""
    manipulator.add_interceptor(RequestJournal(fingerprints=True))
    manipulator.inspect(item, get="value")
    manipulator.configure(item, set={"params": {"value": 5}})
    manipulator.configure(item, set={"params": {"value": 5}})

    changed = manipulator.history(changed_only=True)
    assert [entry["operation"] for entry in changed] == ["configure"], (
        "reading changed nothing, and writing the same value twice changed nothing the second time")


def test_fingerprints_are_off_unless_asked_for(manipulator, item):
    manipulator.add_interceptor(RequestJournal())
    manipulator.configure(item, set={"params": {"value": 5}})

    assert "before" not in manipulator.history()[0]
    assert manipulator.history(changed_only=True) == []


# --- replaying ----------------------------------------------------------------------------

def test_a_session_replays_through_the_manipulator(manipulator, item):
    recorder = Manipulator(item, base_classes=[Item])
    journal = RequestJournal()
    recorder.add_interceptor(journal)
    recorder.configure(item, set={"params": {"value": 7}})

    item.value = 1
    outcome = manipulator.replay(journal)

    assert item.value == 7
    assert outcome.failed == []


def test_a_session_is_a_plan(manipulator, item):
    """Replaying is running a plan, so there is no second mechanism for it."""
    journal = RequestJournal()
    manipulator.add_interceptor(journal)
    manipulator.inspect(item, get="value")
    manipulator.inspect(item, get="name")

    plan = journal.as_plan()
    assert [step["operation"] for step in plan.values()] == ["inspect", "inspect"]
    assert list(plan.values())[1]["after"] == [list(plan)[0]], "the order it ran in is kept"


def test_replaying_nothing_is_not_an_error(manipulator):
    manipulator.add_interceptor(RequestJournal())
    assert manipulator.replay() == {}


def test_replaying_without_a_journal_says_so(manipulator):
    with pytest.raises(NotFoundError):
        manipulator.replay()


def test_the_old_way_still_works_and_warns(manipulator, item):
    """Deprecated in 1.3.0, removed in 2.0, and working the whole time."""
    recorder = Manipulator(item, base_classes=[Item])
    journal = RequestJournal()
    recorder.add_interceptor(journal)
    recorder.configure(item, set={"params": {"value": 3}})

    item.value = 1
    with pytest.deprecated_call():
        responses = journal.replay(manipulator)

    assert item.value == 3
    assert len(responses) == 1
