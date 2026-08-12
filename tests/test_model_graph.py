"""The shape of a model, read back from what its classes already declare.

A class says what it holds. Nobody says what holds *it*, and that is the direction every real
question is asked in: change this type, and what feels it? These tests use a small model with
one of each shape a real one has -- a plain field, an optional one, a collection, a container,
and a type that holds its own kind.
"""
from typing import Dict, List, Optional

import pytest

from msb_arch.base.basecontainer import BaseContainer
from msb_arch.base.baseentity import BaseEntity
from msb_arch.errors import NotFoundError
from msb_arch.mega.manipulator import Manipulator
from msb_arch.model import dependents_of, derive_model, holdings_of


class Bolt(BaseEntity):
    length: float


class Wheel(BaseEntity):
    """Holds one type directly and another through a collection."""
    diameter: float
    hub: Bolt
    spokes: List[Bolt]


class Wheels(BaseContainer[Wheel]):
    pass


class Engine(BaseEntity):
    power: int
    spare: Optional[Bolt]


class Car(BaseEntity):
    wheels: Wheels
    engine: Engine
    spares: Dict[str, Wheel]


class Trailer(BaseEntity):
    """A type that can hold its own kind: the graph has to survive a cycle."""
    towed: Optional["Trailer"]


@pytest.fixture
def graph():
    return derive_model([Car, Trailer])


# --- what a class declares ------------------------------------------------------------

def test_a_plain_field_is_an_edge(graph):
    assert graph["Wheel"]["holds"]["hub"] == ["Bolt"]


def test_a_collection_is_an_edge_too(graph):
    """The type is inside a `List`, and an annotation is not a wall."""
    assert graph["Wheel"]["holds"]["spokes"] == ["Bolt"]
    assert graph["Car"]["holds"]["spares"] == ["Wheel"]


def test_an_optional_field_is_an_edge(graph):
    assert graph["Engine"]["holds"]["spare"] == ["Bolt"]


def test_a_container_declares_what_it_holds(graph):
    assert graph["Wheels"]["holds"]["items"] == ["Wheel"]
    assert graph["Wheels"]["container"] is True
    assert graph["Car"]["container"] is False


def test_unmodelled_types_are_left_out(graph):
    """A graph of everything that mentions `str` is a graph of everything."""
    assert "float" not in graph and "int" not in graph
    assert "diameter" not in graph["Wheel"]["holds"]


def test_a_type_nothing_was_named_for_is_still_reached(graph):
    """Only `Car` and `Trailer` were passed in; the rest were found by walking."""
    assert set(graph) == {"Car", "Wheels", "Wheel", "Bolt", "Engine", "Trailer"}


# --- the direction nothing in the code answers ------------------------------------------

def test_the_edges_are_turned_round(graph):
    assert graph["Bolt"]["held_by"] == {"Wheel": ["hub", "spokes"], "Engine": ["spare"]}


def test_what_a_change_reaches_is_transitive(graph):
    """A `Bolt` is held by a `Wheel`, held by `Wheels`, held by a `Car`."""
    assert dependents_of(graph, "Bolt") == ["Car", "Engine", "Wheel", "Wheels"]


def test_a_type_nothing_holds_has_no_dependents(graph):
    assert dependents_of(graph, "Car") == []


def test_what_a_type_reaches_is_the_same_walk_the_other_way(graph):
    assert holdings_of(graph, "Car") == ["Bolt", "Engine", "Wheel", "Wheels"]
    assert holdings_of(graph, "Bolt") == []


def test_a_type_that_holds_its_own_kind_terminates(graph):
    """Followed once and left. A cycle in a model is ordinary -- a tree of the same thing."""
    assert graph["Trailer"]["holds"]["towed"] == ["Trailer"]
    assert dependents_of(graph, "Trailer") == []
    assert holdings_of(graph, "Trailer") == []


def test_asking_about_a_type_that_is_not_there(graph):
    assert dependents_of(graph, "Bicycle") == []


# --- reached the way everything else is -------------------------------------------------

def test_the_manipulator_assembles_it_from_what_it_knows():
    """Its own state, so it builds the answer -- the same split as the operation catalogue."""
    manipulator = Manipulator(managing_object=Car(name="c", wheels=Wheels(name="w"),
                                                  engine=Engine(name="e", power=1, spare=None),
                                                  spares={}))
    graph = manipulator.describe_model()
    assert "Wheel" in graph
    assert manipulator.dependents_of("Bolt") == ["Car", "Engine", "Wheel", "Wheels"]


def test_it_is_asked_for_as_a_request():
    """An interface reaching into a manipulator to read its types is what requests prevent."""
    manipulator = Manipulator(base_classes=[Car])
    graph = manipulator.catalogue(Bolt(name="b", length=1.0), method="model")
    assert graph["Wheels"]["holds"]["items"] == ["Wheel"]

    answer = manipulator.catalogue(Bolt(name="b", length=1.0), method="model", of="Bolt")
    assert answer["dependents"] == ["Car", "Engine", "Wheel", "Wheels"]
    assert answer["holds"] == []


def test_asking_about_a_type_the_model_does_not_have_says_so():
    manipulator = Manipulator(base_classes=[Car])
    with pytest.raises(NotFoundError):
        manipulator.catalogue(Bolt(name="b", length=1.0), method="model", of="Bicycle")


def test_a_field_added_to_a_class_changes_the_answer():
    """The reason to derive it. A drawn diagram would now be wrong and would not say so."""
    class Radio(BaseEntity):
        band: str

    class Dashboard(BaseEntity):
        clock: str

    assert derive_model([Dashboard])["Dashboard"]["holds"] == {}

    class Dashboard(BaseEntity):          # noqa: F811 -- the same class, one field later
        clock: str
        radio: Radio

    assert derive_model([Dashboard])["Dashboard"]["holds"] == {"radio": ["Radio"]}
