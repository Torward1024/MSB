"""The exception taxonomy, and the promise that it did not break anything.

Two things are worth testing about an exception hierarchy. The first is its shape: every type
the framework raises has to be reachable through `MSBError`, or "catch anything from MSB" is
not true. The second matters more, because it is what an upgrade can silently destroy: each
type also derives from the built-in it replaced, so code written against the old behaviour
keeps catching what it always caught. Those tests below are deliberately written the old way,
naming `TypeError` and `ValueError` rather than the new classes.

The last test is a ratchet: it fails if a bare built-in is raised anywhere in the package
again, so the taxonomy cannot quietly erode one convenient `raise ValueError` at a time.
"""
import pathlib
import re

import pytest

from msb_arch import (BaseContainer,
                      BaseEntity,
                      Manipulator,
                      Super,
                      errors)
from msb_arch.utils.validation import check_positive


class Widget(BaseEntity):
    size: int


class Widgets(BaseContainer[Widget]):
    pass


class Exploding(Widget):
    def detonate(self) -> None:
        raise RuntimeError("boom")


class SpecialWidgets(Widgets):
    """A subclass of an already parameterized container: its type argument is inherited."""


class Inspector(Super):
    OPERATION = "inspect"

    def _inspect(self, obj, attributes):
        return self._apply_methods(obj, attributes)


class Strict(Super):
    OPERATION = "strictly"

    def _strictly(self, obj, attributes):
        return self._apply_methods(obj, attributes, strict=True)


class Bench(Manipulator):
    pass


@pytest.fixture
def manipulator():
    bench = Bench(base_classes=[Widget, Widgets, Exploding])
    bench.register_operation(Inspector(bench))
    bench.register_operation(Strict(bench))
    return bench


# --- the shape of the hierarchy -------------------------------------------------------

def test_every_exception_derives_from_msberror():
    for name in errors.__all__:
        exception_type = getattr(errors, name)
        assert issubclass(exception_type, errors.MSBError), f"{name} is outside MSBError"


def test_every_exception_is_exported_from_the_package():
    import msb_arch

    for name in errors.__all__:
        assert name in msb_arch.__all__, f"{name} is missing from msb_arch.__all__"
        assert getattr(msb_arch, name) is getattr(errors, name)


def test_the_two_intermediate_types_are_never_raised_alone():
    """`ValidationError` and `OperationError` group; they do not describe anything."""
    package = pathlib.Path(__file__).resolve().parent.parent / "src" / "msb_arch"
    raised = re.compile(r"raise (ValidationError|OperationError)\(")
    for path in package.rglob("*.py"):
        assert not raised.search(path.read_text(encoding="utf-8")), f"{path.name} raises a group"


# --- what old code still catches ------------------------------------------------------

def test_a_wrong_type_is_still_a_typeerror():
    with pytest.raises(TypeError):
        Widget(name="w", size="large")


def test_an_unknown_attribute_is_still_a_valueerror():
    with pytest.raises(ValueError):
        Widget(name="w", nonesuch=1)


def test_a_missing_attribute_is_still_a_keyerror():
    with pytest.raises(KeyError):
        Widget(name="w", size=1).get("nonesuch")


def test_a_duplicate_item_is_still_a_valueerror():
    box = Widgets(name="box")
    box.add(Widget(name="w", size=1))
    with pytest.raises(ValueError):
        box.add(Widget(name="w", size=2))


def test_a_failed_constraint_is_still_a_valueerror():
    with pytest.raises(ValueError):
        check_positive(-1, "size")


def test_a_non_numeric_constraint_argument_is_still_a_typeerror():
    with pytest.raises(TypeError):
        check_positive("big", "size")


def test_a_duplicate_registration_is_still_a_valueerror(manipulator):
    with pytest.raises(ValueError):
        manipulator.register_operation(Inspector(manipulator))


def test_a_malformed_request_is_still_a_typeerror(manipulator):
    with pytest.raises(TypeError):
        manipulator.process_request(["not", "a", "dict"])


def test_an_unparameterized_container_says_so():
    """It used to fail on `__args__` instead, because the attribute was found by inheritance."""
    class Untyped(BaseContainer):
        pass

    with pytest.raises(errors.ResolutionError, match="BaseContainer\\[YourType\\]"):
        Untyped(name="untyped")
    with pytest.raises(TypeError):
        Untyped(name="untyped")


def test_a_subclass_of_a_parameterized_container_still_resolves():
    """The type argument is inherited, so tightening the lookup must not break this."""
    box = SpecialWidgets(name="special")
    box.add(Widget(name="w", size=1))
    assert box.get("w").size == 1


# --- what new code can catch instead --------------------------------------------------

@pytest.mark.parametrize("expected, action", [
    (errors.TypeValidationError, lambda: Widget(name="w", size="large")),
    (errors.UnknownAttributeError, lambda: Widget(name="w", nonesuch=1)),
    (errors.NotFoundError, lambda: Widget(name="w", size=1).get("nonesuch")),
    (errors.ConstraintError, lambda: check_positive(-1, "size")),
])
def test_the_specific_type_is_raised(expected, action):
    with pytest.raises(expected):
        action()


def test_a_duplicate_name_is_narrower_than_an_item_name_problem():
    box = Widgets(name="box")
    box.add(Widget(name="w", size=1))
    with pytest.raises(errors.DuplicateNameError):
        box.add(Widget(name="w", size=2))
    assert issubclass(errors.DuplicateNameError, errors.ItemNameError)


def test_validation_catches_all_four_kinds():
    """The point of the grouping level: one `except` for anything the caller got wrong."""
    for action in (lambda: Widget(name="w", size="large"),
                   lambda: Widget(name="w", nonesuch=1),
                   lambda: check_positive(-1, "size")):
        with pytest.raises(errors.ValidationError):
            action()


def test_an_unsupported_object_is_a_dispatcherror(manipulator):
    """`process_request` reports rather than raises, so ask the registry directly."""
    with pytest.raises(errors.DispatchError):
        manipulator.get_methods_for_type(int)


# --- a failing handler ----------------------------------------------------------------

def test_strict_mode_raises_a_handlererror(manipulator):
    widget = Widget(name="w", size=1)
    with pytest.raises(errors.HandlerError):
        manipulator.strictly(widget, no_such_method=None)


def test_strict_apply_methods_keeps_the_original_exception_as_the_cause(manipulator):
    """Without the cause, a handler's traceback is reduced to a string, and a failure inside
    domain code becomes much harder to locate than before the framework owned the loop."""
    strict = Strict(manipulator)
    with pytest.raises(errors.HandlerError) as caught:
        strict._apply_methods(Exploding(name="e", size=1), {"detonate": None}, strict=True)
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert str(caught.value.__cause__) == "boom"


def test_a_facade_reports_the_failure_without_the_cause(manipulator):
    """Crossing the response boundary reduces the failure to a message, so `__cause__` is
    gone by the time a facade re-raises. Documented rather than fixed: carrying the
    exception object in a response would make responses unserializable."""
    with pytest.raises(errors.HandlerError) as caught:
        manipulator.strictly(Exploding(name="e", size=1), detonate=None)
    assert caught.value.__cause__ is None
    assert "boom" in str(caught.value)


def test_a_handler_error_is_still_catchable_as_a_plain_exception(manipulator):
    with pytest.raises(Exception):
        manipulator.strictly(Widget(name="w", size=1), no_such_method=None)


# --- the ratchet ----------------------------------------------------------------------

BARE = re.compile(r"^\s*raise (TypeError|ValueError|KeyError|AttributeError|Exception)\(", re.M)


def test_no_bare_builtin_is_raised_anywhere_in_the_package():
    """What a caller may catch is part of the contract, so it is not decided per call site."""
    package = pathlib.Path(__file__).resolve().parent.parent / "src" / "msb_arch"
    offenders = []
    for path in sorted(package.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BARE.match(line):
                offenders.append(f"{path.relative_to(package)}:{number}: {line.strip()}")
    assert not offenders, "raise one of msb_arch.errors instead:\n  " + "\n  ".join(offenders)
