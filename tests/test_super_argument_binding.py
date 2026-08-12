"""Characterization tests for `Super._validate_and_apply_method`.

This is the busiest extension point: downstream handlers call it once per requested method,
and everything the operation layer does to an object passes through here. Its argument
binding branches had no coverage at all.

These tests pin down what it does today, before anything changes. Where the current
behaviour looks surprising the test says so in words rather than quietly enshrining it.
"""
import pytest

from msb_arch import Super


class Binder(Super):
    OPERATION = "bind"

    def _bind(self, obj, attributes):
        return True


@pytest.fixture
def binder():
    return Binder()


def bound(binder, obj, name, args, methods, extra=None):
    """Apply a method and return the response."""
    return binder._validate_and_apply_method(obj, name, args, methods, extra)


class TestMethodLookup:
    def test_unknown_method_is_reported_not_raised(self, binder):
        result = bound(binder, "obj", "missing", None, {})
        assert result["status"] is False
        assert result["error"] == "Method 'missing' not found"
        assert result["method"] == "missing"

    def test_known_method_is_applied(self, binder):
        result = bound(binder, "obj", "known", None, {"known": lambda self: "done"})
        assert result["status"] is True
        assert result["result"] == "done"


class TestBindingByShape:
    """How `method_args` is turned into the call depends on the method's own signature."""

    def test_no_parameters_means_the_object_is_passed_anyway(self, binder):
        # A method declaring nothing beyond self is still called with the object, which is
        # how a plain getter such as Widget.get_code() is reached.
        seen = []
        methods = {"m": lambda self: seen.append(self) or "ok"}
        assert bound(binder, "target", "m", None, methods)["result"] == "ok"
        assert seen == ["target"]

    def test_a_scalar_fills_the_first_required_parameter(self, binder):
        methods = {"m": lambda self, value: f"{self}:{value}"}
        assert bound(binder, "target", "m", 42, methods)["result"] == "target:42"

    def test_a_dict_is_spread_over_the_parameters(self, binder):
        methods = {"m": lambda self, first, second: f"{first}-{second}"}
        result = bound(binder, "target", "m", {"first": 1, "second": 2}, methods)
        assert result["result"] == "1-2"

    def test_a_scalar_fills_the_first_optional_when_nothing_is_required(self, binder):
        methods = {"m": lambda self, value=None: f"got {value}"}
        assert bound(binder, "target", "m", "x", methods)["result"] == "got x"

    def test_a_parameter_named_obj_is_reserved(self, binder):
        # `obj` is special: a callable declaring it is invoked with keywords only and gets
        # the target through that name. Only reachable for a plain function registered with
        # register_method -- a class method declares `self`, which is filtered out, so its
        # `obj` parameter would be bound by keyword while `self` was left unfilled.
        methods = {"m": lambda obj, value=None: f"{obj}/{value}"}
        assert bound(binder, "target", "m", {"value": 1}, methods)["result"] == "target/1"

    def test_a_scalar_overwrites_a_parameter_named_obj(self, binder):
        # The scalar lands on the first required parameter, which here is `obj` itself, so
        # the target is replaced by the argument and the real parameter is left missing.
        methods = {"m": lambda obj, value: f"{obj}/{value}"}
        result = bound(binder, "target", "m", "scalar", methods)
        assert result["status"] is False
        assert "Missing required argument 'value'" in result["error"]

    def test_extra_args_are_merged_over_the_request(self, binder):
        methods = {"m": lambda self, first=None, second=None: f"{first}-{second}"}
        result = bound(binder, "t", "m", {"first": 1}, methods, extra={"second": 2})
        assert result["result"] == "1-2"

    def test_extra_args_win_over_the_request(self, binder):
        methods = {"m": lambda self, value=None: value}
        result = bound(binder, "t", "m", {"value": "from request"}, methods,
                       extra={"value": "from extra"})
        assert result["result"] == "from extra"


class TestUnknownKeysAreDropped:
    def test_keys_the_method_does_not_declare_are_discarded(self, binder):
        # Surprising but deliberate: a misspelled argument is silently ignored rather than
        # reported, so a typo in a request looks like a successful call.
        methods = {"m": lambda self, value=None: f"value={value}"}
        result = bound(binder, "t", "m", {"valeu": "typo"}, methods)
        assert result["status"] is True
        assert result["result"] == "value=None"


class TestMissingArguments:
    def test_a_missing_required_argument_is_reported(self, binder):
        methods = {"m": lambda self, required: required}
        result = bound(binder, "t", "m", None, methods)
        assert result["status"] is False
        assert "Missing required argument 'required'" in result["error"]

    def test_a_dict_missing_one_required_argument_is_reported(self, binder):
        methods = {"m": lambda self, first, second: (first, second)}
        result = bound(binder, "t", "m", {"first": 1}, methods)
        assert result["status"] is False
        assert "second" in result["error"]


class TestFailuresBecomeResponses:
    def test_a_type_error_inside_the_method_is_reported(self, binder):
        def explode(self, value=None):
            return 1 + "two"

        result = bound(binder, "t", "m", None, {"m": explode})
        assert result["status"] is False
        assert result["error"].startswith("TypeError:")

    def test_any_other_exception_is_reported(self, binder):
        def explode(self, value=None):
            raise RuntimeError("boom")

        result = bound(binder, "t", "m", None, {"m": explode})
        assert result["status"] is False
        assert "boom" in result["error"]

    def test_a_falsy_result_still_counts_as_success(self, binder):
        for value in (None, 0, "", [], False):
            result = bound(binder, "t", "m", None, {"m": lambda self, v=value: v})
            assert result["status"] is True, f"{value!r} was treated as a failure"
            assert result["result"] == value


class TestVariadicSignatures:
    def test_var_keyword_is_not_treated_as_required(self, binder):
        methods = {"m": lambda self, **kwargs: sorted(kwargs)}
        result = bound(binder, "t", "m", {"a": 1, "b": 2}, methods)
        assert result["status"] is True

    def test_var_positional_is_not_treated_as_required(self, binder):
        methods = {"m": lambda self, *args: "ok"}
        assert bound(binder, "t", "m", None, methods)["status"] is True
