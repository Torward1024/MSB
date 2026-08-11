"""Working out what a Super offers from the code that does it."""
import pytest

from msb_arch.catalogue import derive, label_for, order
from msb_arch.super.super import Super


class Chain(Super):
    """A Super whose handlers call one another, as a real one does."""

    OPERATION = "compute"

    def _compute_root(self, obj, attributes):
        return obj.get_items()

    def _compute_middle(self, obj, attributes):
        base = self._compute_root(obj, attributes)
        return base

    def _compute_leaf(self, obj, attributes):
        return self._compute_middle(obj, attributes), self._compute_root(obj, attributes)


def test_the_handlers_are_found_without_being_listed():
    """A Super's handlers name themselves, so the catalogue costs no declaration."""
    found = derive(Chain(None), "_compute_")
    assert set(found) == {"root", "middle", "leaf"}


def test_the_edges_between_handlers_are_exact():
    """Handlers call each other by name, and a call is a call. This is the edge set a
    scheduler needs: what may run at once, and what a change invalidates."""
    found = derive(Chain(None), "_compute_")

    assert found["root"]["requires"] == []
    assert found["middle"]["requires"] == ["root"]
    assert found["leaf"]["requires"] == ["middle", "root"]


def test_what_a_handler_reads_is_an_upper_bound():
    """Offered for checking a declaration, never for replacing one -- a shared helper fetches
    what its caller may not use, so this answer is wide by construction."""
    found = derive(Chain(None), "_compute_")
    assert "items" not in found["root"]["reads"], "only model accessors count"


def test_ordering_puts_each_after_what_it_needs():
    found = derive(Chain(None), "_compute_")
    assert order(found, ["leaf", "root", "middle"]) == ["root", "middle", "leaf"]


def test_a_prerequisite_nobody_asked_for_is_not_invented():
    """The caller asked for two things; it gets two things back."""
    found = derive(Chain(None), "_compute_")
    assert order(found, ["leaf", "middle"]) == ["middle", "leaf"]


def test_a_cycle_is_reported_rather_than_raised(caplog):
    """A cycle is a defect in the handlers, not a reason to refuse to run them."""
    cyclic = {"a": {"requires": ["b"]}, "b": {"requires": ["a"]}}
    assert sorted(order(cyclic, ["a", "b"])) == ["a", "b"]


def test_a_label_follows_from_the_name():
    assert label_for("uv_coverage") == "Uv Coverage"
    assert label_for("uv_coverage", {"uv": "UV"}) == "UV Coverage"
    assert label_for("beam_pattern") == "Beam Pattern"


def test_a_super_whose_source_cannot_be_read_answers_empty():
    """Introspection that cannot see the code says so by returning nothing, rather than by
    raising in the middle of building somebody's menu."""
    assert derive(object(), "_compute_") == {}
