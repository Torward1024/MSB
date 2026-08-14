# test_deprecations.py
"""Every deprecated name warns, and keeps doing exactly what it did.

A deprecation is a promise in both directions: the replacement exists now, and the old name works
until the next major version. Both halves are pinned here so neither can be broken quietly.
"""
import pytest

from msb_arch import BaseContainer, BaseEntity, Manipulator, Project, RequestJournal, Super


class Part(BaseEntity):
    price: float


class Parts(BaseContainer[Part]):
    pass


class Depot(Project):
    def create_item(self, item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None:
        self.add_item(Part(name=item_code, price=1.0, isactive=isactive))


class Pricing(Super):
    OPERATION = "price"

    def _price_parts(self, obj, attributes):
        return sum(part.price for part in obj.get_items())


class Workshop(Manipulator):
    pass


def test_entity_clear_warns_and_still_nulls_the_attributes():
    part = Part(name="bolt", price=4.5)

    with pytest.deprecated_call(match="reset_attributes"):
        part.clear()

    assert part.price is None
    assert part.name == "bolt"


def test_container_clear_warns_and_still_removes_the_items():
    box = Parts(name="box")
    box.add(Part(name="bolt", price=4.5))

    with pytest.deprecated_call(match="remove_all"):
        box.clear()

    assert len(box) == 0
    assert box.name == "box"


def test_project_clear_warns_and_still_empties_the_project():
    depot = Depot(name="depot")
    depot.create_item("bolt")

    with pytest.deprecated_call(match="remove_all"):
        depot.clear()

    assert depot.get_items() == {}


def test_super_clear_warns_and_still_drops_the_references():
    workshop = Workshop(base_classes=[Part, Parts])
    pricing = Pricing(workshop)

    with pytest.deprecated_call(match="release"):
        pricing.clear()

    assert pricing._manipulator is None


def test_journal_replay_warns_and_still_replays():
    box = Parts(name="box")
    box.add(Part(name="bolt", price=4.5))
    workshop = Workshop(base_classes=[Part, Parts], managing_object=box)
    journal = RequestJournal()
    workshop.add_interceptor(journal)
    workshop.inspect(box.get("bolt"), get="price")
    workshop.remove_interceptor(journal)

    with pytest.deprecated_call(match="manipulator.replay"):
        outcome = journal.replay(workshop)

    assert len(outcome) == 1


def test_the_three_replacements_are_three_different_jobs():
    """What made one name wrong: none of the three is a special case of another."""
    box = Parts(name="box")
    box.add(Part(name="bolt", price=4.5))
    bolt = box.get("bolt")

    bolt.reset_attributes()
    assert bolt.price is None
    assert len(box) == 1                    # nulling an attribute removes nothing

    box.remove_all()
    assert len(box) == 0
    assert bolt.name == "bolt"              # and removing an item empties nothing

    workshop = Workshop(base_classes=[Part, Parts])
    pricing = Pricing(workshop)
    pricing.release()
    assert pricing._manipulator is None     # while releasing touches no data at all
    assert bolt.name == "bolt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
