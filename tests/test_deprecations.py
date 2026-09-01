# test_deprecations.py
"""What 1.x announced it would remove, and 2.0 removed.

A deprecation is a promise in both directions: the replacement exists now, and the old name works
until the next major version. Both halves were pinned here while the old names lived. They are
gone in 2.0, so what is pinned now is that they are gone and that each replacement does the job --
one name per job, which is the whole reason `clear()` was split.
"""
import pytest

from msb_arch import BaseContainer, BaseEntity, Manipulator, Project, RequestJournal, Super


class Part(BaseEntity):
    price: float


class Parts(BaseContainer[Part]):
    pass


class Depot(Project):
    _item_type = Part

    def create_item(self, item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None:
        self.add_item(Part(name=item_code, price=1.0, isactive=isactive))


class Pricing(Super):
    OPERATION = "price"

    def _price_parts(self, obj, attributes):
        return sum(part.price for part in obj.get_items())


class Workshop(Manipulator):
    pass


# --- the names are gone ---------------------------------------------------------------------------

@pytest.mark.parametrize("owner, gone", [
    (Part, "clear"),
    (Parts, "clear"),
    (Depot, "clear"),
    (Super, "clear"),
    (RequestJournal, "replay"),
])
def test_the_deprecated_name_is_no_longer_there(owner, gone):
    """`clear()` meant three different things depending on what you called it on."""
    assert not hasattr(owner, gone), f"{owner.__name__}.{gone} should have gone in 2.0"


# --- and each job has its own name -----------------------------------------------------------------

def test_reset_attributes_nulls_an_entity_s_attributes():
    part = Part(name="bolt", price=4.5)

    part.reset_attributes()

    assert part.price is None
    assert part.name == "bolt"


def test_remove_all_empties_a_container():
    box = Parts(name="box")
    box.add(Part(name="bolt", price=4.5))

    box.remove_all()

    assert len(box) == 0
    assert box.name == "box"


def test_remove_all_empties_a_project():
    depot = Depot(name="depot")
    depot.create_item("bolt")

    depot.remove_all()

    assert depot.get_items() == []
    assert depot.name == "depot"


def test_release_drops_what_an_operation_holds():
    workshop = Workshop(base_classes=[Part, Parts])
    pricing = Pricing(workshop)
    workshop.register_operation(pricing)
    box = Parts(name="box")
    box.add(Part(name="bolt", price=4.5))
    workshop.price(box)

    pricing.release()

    assert workshop.price(box) == 4.5           # still usable afterwards


def test_a_session_is_replayed_through_the_orchestrator():
    """Replaying belongs on the thing that runs requests, not on the record of them."""
    workshop = Workshop(base_classes=[Part, Parts])
    box = Parts(name="box")
    box.add(Part(name="bolt", price=4.5))
    journal = RequestJournal()
    workshop.add_interceptor(journal)
    workshop.configure(box.get("bolt"), set={"params": {"price": 9.0}})
    workshop.remove_interceptor(journal)

    box.get("bolt").price = 4.5
    outcome = workshop.replay(journal)

    assert outcome.failed == []
    assert box.get("bolt").price == 9.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
