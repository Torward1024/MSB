"""What a `Super` requires of whatever drives it.

`Super.__init__` took a `Manipulator`, which reads as though an operation needs the
orchestrator entire -- registry, facades, batching -- when it calls exactly one method on it.
It now names `MethodProvider`, a protocol of that one method.

Three things follow, and each is a test below: an operation can be driven by anything that
answers the question, the operation layer no longer imports the entry-point layer above it to
say what it accepts, and a `Manipulator` satisfies the protocol without declaring that it does.
"""
import pytest

from msb_arch import (BaseEntity,
                      Manipulator,
                      MethodProvider,
                      Super,
                      errors)


class Widget(BaseEntity):
    size: int

    def get_size(self) -> int:
        return self.size


class Inspector(Super):
    OPERATION = "inspect"

    def _inspect(self, obj, attributes):
        return self._apply_methods(obj, attributes)


class Bench(Manipulator):
    pass


class TinyProvider:
    """Everything a Super needs, in three lines and without a Manipulator anywhere."""

    def __init__(self, methods):
        self.methods = methods

    def get_methods_for_type(self, obj_type):
        return self.methods


def test_a_super_runs_on_anything_that_answers_the_question():
    """The point of the protocol: no orchestrator is required to exercise an operation."""
    inspector = Inspector(TinyProvider({"get_size": Widget.get_size}))
    results = inspector.execute(Widget(name="w", size=7), {"get_size": None})
    assert results["status"] is True
    assert results["result"]["get_size"]["result"] == 7


def test_a_manipulator_satisfies_the_protocol_without_saying_so():
    """Structural typing, so nothing had to be declared or changed on the Manipulator."""
    assert isinstance(Bench(base_classes=[Widget]), MethodProvider)


def test_a_stub_satisfies_the_protocol_too():
    assert isinstance(TinyProvider({}), MethodProvider)


def test_something_without_the_method_does_not():
    assert not isinstance(object(), MethodProvider)


def test_a_super_with_no_provider_still_reports_clearly():
    inspector = Inspector()
    with pytest.raises(errors.DispatchError, match="No methods available"):
        inspector._get_methods(Widget)


def test_the_operation_layer_does_not_import_the_entry_point_layer():
    """`super` importing from `mega` was a dependency pointing up through the layers, and it
    existed only to spell a type hint that was already a string."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent
              / "src" / "msb_arch" / "super" / "super.py").read_text(encoding="utf-8")
    assert "from ..mega" not in source
    assert "import Manipulator" not in source
