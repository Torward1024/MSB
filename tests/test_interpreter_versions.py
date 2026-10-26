# test_interpreter_versions.py
"""Every interpreter the package promises to work on is one the suite is run on.

`requires-python = ">=3.12"` promised four versions and the workflow ran one. What that hid:
Python 3.14 made annotations lazy (PEP 649/749), so a class body that annotates a name no
longer leaves `__annotations__` in the namespace the metaclass is handed -- it leaves an
`__annotate__` function. The metaclass read the namespace key, found nothing, and every field
a class declared itself was silently dropped. `credit: float = 0.0` became an unknown
attribute, 273 tests failed on 3.14 and 3.15, and 3.12 stayed green the whole time.

The lesson is not about annotations. A version in `requires-python` that nothing runs is a
claim, and this module turns the claim into a test: the matrix must start where the metadata
starts, cover every minor version in between, and reach at least the interpreter in hand --
so the day someone runs this on a version the workflow does not list, it says so.
"""
import ast
import pathlib
import re
import sys
import tomllib

import pytest

from msb_arch import BaseEntity
from msb_arch.base.serializable import _own_annotations

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

#: Only in a source checkout. Installed from a wheel, there is no workflow to read.
packaging_present = pytest.mark.skipif(
    not (PYPROJECT.exists() and WORKFLOW.exists()),
    reason="runs against a source checkout, not an installed wheel",
)


def _promised_minimum() -> tuple:
    """Return the lowest Python `requires-python` allows, as a `(major, minor)` pair."""
    metadata = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    spec = metadata["project"]["requires-python"]
    match = re.fullmatch(r">=\s*(\d+)\.(\d+)", spec.strip())
    assert match, f"requires-python is {spec!r}; this test reads the form '>=X.Y'"
    return int(match.group(1)), int(match.group(2))


def _tested_versions() -> list:
    """Return the Python versions the CI matrix names, in the order it names them."""
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"python-version:\s*\[([^\]]+)\]", text)
    assert match, "the workflow does not declare a python-version matrix"
    return [tuple(int(part) for part in version.split("."))
            for version in re.findall(r"['\"](\d+\.\d+)['\"]", match.group(1))]


# --- the promise and the matrix agree ---------------------------------------------------------

@packaging_present
def test_the_matrix_starts_where_the_metadata_starts():
    assert _tested_versions()[0] == _promised_minimum()


@packaging_present
def test_the_matrix_skips_no_version_in_between():
    """A gap is the same hole in a smaller shape: 3.13 untested is 3.13 unknown."""
    tested = _tested_versions()
    expected = [(tested[0][0], minor)
                for minor in range(tested[0][1], tested[-1][1] + 1)]

    assert tested == expected


@packaging_present
def test_the_matrix_reaches_the_interpreter_running_this():
    """Fails on the first Python released after the matrix was last extended, which is the
    only moment anybody is in a position to notice."""
    tested = _tested_versions()

    assert max(tested) >= sys.version_info[:2], (
        f"running on {sys.version_info.major}.{sys.version_info.minor}, "
        f"matrix stops at {max(tested)[0]}.{max(tested)[1]}")


# --- declared fields, read through the documented API ------------------------------------------

def test_a_class_keeps_the_field_it_declares_itself():
    """What 3.14 broke. Green on 3.12 before the fix and after it, which is the point: this
    assertion was never the weak part -- running it on one interpreter was."""
    class Client(BaseEntity):
        credit: float = 0.0

    assert "credit" in Client._fields
    assert Client(name="c", credit=5.0).credit == 5.0


def test_a_field_declared_on_a_base_arrives_too():
    class Account(BaseEntity):
        balance: float = 0.0

    class Savings(Account):
        rate: float = 0.01

    assert {"balance", "rate"} <= set(Savings._fields)


def test_a_subclass_redeclaring_a_field_wins():
    class Loose(BaseEntity):
        code: object = None

    class Strict(Loose):
        code: str = ""

    assert Strict._fields["code"] is str


def test_own_annotations_does_not_inherit():
    class Account(BaseEntity):
        balance: float = 0.0

    class Savings(Account):
        rate: float = 0.01

    assert set(_own_annotations(Savings)) == {"rate"}


def test_a_forward_reference_does_not_raise_while_the_class_is_built():
    """Lazy annotations exist so a name defined further down the module can be named above it.
    Reading them eagerly at class creation would give that back.
    """
    class Holder(BaseEntity):
        later: "DefinedBelow" = None

    class DefinedBelow(BaseEntity):
        pass

    assert "later" in Holder._fields


# --- the detail that broke, kept out of the source --------------------------------------------

@packaging_present
def test_no_module_reads_the_annotations_of_a_namespace_or_a_class_directly():
    """`__annotations__` on a class, and in a class body's namespace, are implementation
    details -- the documentation has said to use `inspect.get_annotations` since 3.10. Reading
    the namespace key is what cost two interpreters. `_own_annotations` is the one place that
    knows how to ask, so nothing else may ask.
    """
    reading = re.compile(r"""(?:\.get\(\s*['"]__annotations__|getattr\([^)]*['"]__annotations__|"""
                         r"""\[\s*['"]__annotations__['"]\s*\]|\.__annotations__)""")
    offenders = []
    for path in sorted((ROOT / "src" / "msb_arch").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        # The helper's own body is the exception, found by name rather than by a comment a
        # later edit could carry along to code that does not deserve it.
        allowed = range(0)
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.FunctionDef) and node.name == "_own_annotations":
                allowed = range(node.lineno, (node.end_lineno or node.lineno) + 1)
        for number, line in enumerate(text.splitlines(), 1):
            if number in allowed or line.lstrip().startswith("#"):
                continue
            if reading.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")

    assert offenders == [], (
        "read annotations through `_own_annotations` instead:\n" + "\n".join(offenders))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
