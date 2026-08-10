"""Execute the Python examples in the documentation.

Documentation rots quietly: an example keeps looking right long after the API moved, and
the only person who finds out is a reader following it. This runs every fenced Python block
so that cannot happen silently.

Conventions, so the test is a rule rather than a curiosity:

- A ```python block must run. Blocks of one document execute in order, in one shared
  namespace, exactly as a reader following the page would.
- A block illustrating a *shape* rather than code -- a request dictionary with placeholders,
  a response layout -- is fenced ```text instead. It is documentation, not an example.
- A block that demonstrates an error declares it on its first line with `# raises: <Type>`,
  and the test insists it really does raise that. The name may be a built-in or one of the
  types in `msb_arch.errors`, and a subclass satisfies it -- so a block declaring `TypeError`
  still passes once the framework raises its own `TypeValidationError` beneath it.
- `api.md` is excluded: it is a signature reference, and its blocks are declarations rather
  than programs.

`STALE` records documents whose examples are known to be out of date, with the number of
blocks that still fail. The number may only go down. A new breakage anywhere fails the test,
and repairing an old one requires lowering the count, so the debt cannot be quietly kept. It
is empty, and should stay that way.

One thing this cannot catch: an example that runs and claims a wrong result in a comment.
`print(x)  # 8` passes whatever `x` is. Where an example states what it produces, write it as
an `assert` instead, and the claim is checked along with the code.
"""
import builtins
import contextlib
import io
import logging
import os
import pathlib
import re

import pytest

from msb_arch import errors
from msb_arch.utils.logging_setup import logger as package_logger

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
REPO = DOCS.parent

# A signature reference, not a tutorial: its blocks declare rather than execute.
EXCLUDED = {"api.md", "ROADMAP.md"}

# Documents whose examples predate the current API. These numbers may only decrease, and as
# of P11 there are none: every fenced Python block in the documentation runs. Adding an entry
# here is admitting debt, so prefer fixing the example.
STALE = {}

RAISES = re.compile(r"^\s*#\s*raises:\s*(\w+)", re.M)


def documents():
    """Every documentation page that carries Python examples, plus the README."""
    found = [p for p in sorted(DOCS.rglob("*.md")) if p.name not in EXCLUDED]
    found.append(REPO / "README.md")
    return [p for p in found if "```python" in p.read_text(encoding="utf-8")]


def blocks_of(path):
    return re.findall(r"```python\n(.*?)```", path.read_text(encoding="utf-8"), re.S)


def declared_type(name):
    """Resolve a name from a `# raises:` marker to the class it denotes."""
    return getattr(errors, name, None) or getattr(builtins, name, None)


def run_document(path):
    """Execute a document's blocks in order and return the failures."""
    namespace = {}
    failures = []
    for index, block in enumerate(blocks_of(path)):
        expected = RAISES.search(block)
        wanted = declared_type(expected.group(1)) if expected else None
        if expected and wanted is None:
            failures.append(f"block {index}: `# raises: {expected.group(1)}` names no known type")
            continue
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(block, f"{path.name}#{index}", "exec"), namespace)
        except Exception as exc:                          # noqa: BLE001 - reported below
            if wanted and isinstance(exc, wanted):
                continue
            failures.append(f"block {index}: {type(exc).__name__}: {exc}")
        else:
            if expected:
                failures.append(
                    f"block {index}: declared `# raises: {expected.group(1)}` but did not raise"
                )
    return failures


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    """Run examples somewhere harmless and undo what they configure.

    Examples legitimately call `setup_logging` and write files; without this they would
    attach handlers to the package logger for the rest of the session and drop `app.log`
    into the repository.
    """
    saved_handlers = package_logger.handlers[:]
    saved_level = package_logger.level
    saved_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield
    os.chdir(saved_cwd)
    for handler in package_logger.handlers[:]:
        if handler not in saved_handlers:
            package_logger.removeHandler(handler)
            handler.close()
    package_logger.handlers[:] = saved_handlers
    package_logger.setLevel(saved_level)


@pytest.mark.parametrize("path", documents(), ids=lambda p: p.name)
def test_examples_run(path):
    relative = path.relative_to(REPO).as_posix()
    failures = run_document(path)
    allowed = STALE.get(relative, 0)

    if len(failures) > allowed:
        detail = "\n  ".join(failures)
        pytest.fail(
            f"{relative}: {len(failures)} example(s) fail, {allowed} allowed\n  {detail}"
        )
    if len(failures) < allowed:
        pytest.fail(
            f"{relative}: only {len(failures)} example(s) fail but {allowed} are allowed. "
            f"Lower the number in STALE."
        )


def test_stale_list_names_real_documents():
    """A document that was repaired and removed must not linger in the list."""
    for relative in STALE:
        assert (REPO / relative).exists(), f"{relative} in STALE does not exist"


def test_every_document_has_examples_or_is_excluded():
    """A guide with no runnable example is worth noticing."""
    guides = [p for p in (DOCS / "modules").glob("*.md")]
    without = [p.name for p in guides if "```python" not in p.read_text(encoding="utf-8")]
    assert not without, f"module guides with no examples: {without}"


# --- the version --------------------------------------------------------------------------

def test_the_package_builds_the_version_it_declares():
    """The number in `__version__` is the number a built wheel carries.

    This exists because it once was not. `pyproject.toml` held its own copy, 1.1.2 was tagged
    and released with only `__version__` bumped, and the build produced 1.1.1 -- which PyPI
    refused as a file it already had. The release failed loudly, which was luck: had 1.1.1 not
    already been published, a wheel labelled with the wrong version would have gone out.

    `pyproject.toml` now declares the version dynamic and reads it from the package, so there
    is one number. This test fails if a second one ever appears.
    """
    import pathlib
    import tomllib

    root = pathlib.Path(__file__).resolve().parent.parent
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert "version" not in metadata["project"], (
        "pyproject.toml declares a version of its own; it must read the package's instead, "
        "or the two will disagree and the wheel will be built from this one")
    assert "version" in metadata["project"].get("dynamic", [])
    assert metadata["tool"]["hatch"]["version"]["path"] == "src/msb_arch/__init__.py"


def test_the_version_is_a_release_number():
    """A version that cannot be ordered cannot be depended on."""
    import re

    import msb_arch

    assert re.fullmatch(r"\d+\.\d+\.\d+", msb_arch.__version__), (
        f"'{msb_arch.__version__}' is not major.minor.patch")


def test_the_changelog_documents_the_current_version():
    """A release whose changelog says nothing about it is a release nobody can read."""
    import pathlib

    import msb_arch

    changelog = (pathlib.Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(
        encoding="utf-8")
    assert f"## [{msb_arch.__version__}]" in changelog, (
        f"CHANGELOG.md has no section for {msb_arch.__version__}")
