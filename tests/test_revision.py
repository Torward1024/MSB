"""Did this object change? -- answered without keeping a copy of what it was.

The first of the four steps towards knowing whether a result is still good. It is deliberately
the cheapest one: a counter on the path that already runs on every write.
"""
import pytest

from msb_arch import BaseContainer, BaseEntity


class Item(BaseEntity):
    value: int


class Items(BaseContainer[Item]):
    pass


def test_a_new_object_has_not_changed():
    assert Item(name="i", value=1).revision == 0


def test_a_write_moves_it():
    item = Item(name="i", value=1)
    item.value = 2
    assert item.revision == 1
    item.value = 3
    assert item.revision == 2


def test_writing_the_same_value_still_counts_as_a_write():
    """It counts writes, not differences. Comparing values would mean holding the old one,
    which is the expensive answer this exists to avoid."""
    item = Item(name="i", value=1)
    item.value = 1
    assert item.revision == 1


def test_reading_does_not_move_it():
    item = Item(name="i", value=1)
    item.get("value")
    item.to_dict()
    assert item.revision == 0


def test_two_reads_of_the_number_answer_the_question():
    """The whole use: same number, nothing happened; different number, something did."""
    item = Item(name="i", value=1)
    before = item.revision
    assert item.revision == before

    item.value = 7
    assert item.revision != before


def test_adding_to_a_container_is_a_write_to_the_container():
    box = Items(name="box")
    assert box.revision == 0
    box.add(Item(name="i", value=1))
    assert box.revision == 1


def test_a_container_does_not_move_when_an_item_is_written_to():
    """Stated as a limit rather than discovered as a bug. Making it move would mean walking up
    the ownership graph on every write whether anything caches or not; ask the item."""
    item = Item(name="i", value=1)
    box = Items(name="box", items={"i": item})
    held = box.get("i")

    before = box.revision
    held.value = 2

    assert held.revision == 1
    assert box.revision == before


def test_it_is_not_serialised():
    """A number restored from a file would claim to compare with something it never saw."""
    item = Item(name="i", value=1)
    item.value = 5

    assert "revision" not in item.to_dict() and "_revision" not in item.to_dict()
    assert Item.from_dict(item.to_dict()).revision == 0
