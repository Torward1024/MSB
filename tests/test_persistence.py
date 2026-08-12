"""Writing an object to a file and reading it back, as built-in operations.

Every application on MSB writes these fifteen lines or does without them, so they belong here.
Two things decide whether that is an improvement or a nuisance, and both are tested below: the
format stays a default an application can replace, and the write is atomic.
"""
import json
import pathlib

import pytest

from msb_arch.base.basecontainer import BaseContainer
from msb_arch.base.baseentity import BaseEntity
from msb_arch.errors import NotFoundError, RequestError, SerializationError
from msb_arch.mega.manipulator import Manipulator
from msb_arch.super.super import Super


class Item(BaseEntity):
    value: int


class Items(BaseContainer[Item]):
    pass


@pytest.fixture
def item():
    return Item(name="one", value=7)


@pytest.fixture
def manipulator(item):
    return Manipulator(item)


def result_of(response):
    """Unwrap what a facade returned."""
    return response["result"] if isinstance(response, dict) and "status" in response else response


def test_an_object_survives_a_round_trip(manipulator, item, tmp_path):
    path = tmp_path / "item.json"
    assert result_of(manipulator.save(item, path=str(path)))["path"] == str(path)

    restored = result_of(manipulator.load(item, path=str(path)))
    assert isinstance(restored, Item)
    assert restored.name == "one" and restored.value == 7


def test_a_container_does_too(manipulator, tmp_path):
    box = Items(name="box", items={"a": Item(name="a", value=1), "b": Item(name="b", value=2)})
    path = tmp_path / "box.json"

    manipulator.save(box, path=str(path))
    restored = result_of(manipulator.load(box, path=str(path)))

    assert isinstance(restored, Items)
    assert sorted(restored.get_all()) == ["a", "b"]


def test_directories_are_made_as_needed(manipulator, item, tmp_path):
    """A caller naming a path should not have to create the way to it first."""
    path = tmp_path / "one" / "two" / "item.json"
    manipulator.save(item, path=str(path))
    assert path.is_file()


def test_what_is_written_is_json_anything_can_read(manipulator, item, tmp_path):
    """A file only this library can read would be a worse default than no default."""
    path = tmp_path / "item.json"
    manipulator.save(item, path=str(path))

    def refuse(constant):
        raise ValueError(f"{constant} is not valid JSON")

    data = json.loads(path.read_text(encoding="utf-8"), parse_constant=refuse)
    assert data["name"] == "one" and data["value"] == 7


# --- the two things that decide whether this helps ------------------------------------------

def test_an_interrupted_write_leaves_the_previous_file(manipulator, item, tmp_path, monkeypatch):
    """The reason a framework may take this on at all.

    Writing in place would leave a truncated file if the process died halfway, and a truncated
    file is worse than an old one: it still looks like data.
    """
    path = tmp_path / "item.json"
    manipulator.save(item, path=str(path))
    original = path.read_text(encoding="utf-8")

    def explode(self, target):
        raise OSError("no space left on device")

    # The write itself is interrupted, in the real function rather than in place of it.
    monkeypatch.setattr(pathlib.Path, "replace", explode)
    response = manipulator.save(Item(name="one", value=99), path=str(path), raise_on_error=False)

    assert response["status"] is False
    assert path.read_text(encoding="utf-8") == original, "the previous file must survive"
    assert not list(tmp_path.glob("*.writing")), "and nothing half-written is left behind"


def test_an_application_can_replace_the_format(item, tmp_path):
    """The format is a default, not a law. A built-in is replaced by registering over it."""
    written = {}

    class MyOwnFormat(Super):
        OPERATION = "save"

        def _save(self, obj, attributes):
            written[attributes["path"]] = f"{obj.name}={obj.value}"
            return {"path": attributes["path"], "format": "mine"}

    manipulator = Manipulator(item)
    manipulator.register_operation(MyOwnFormat(manipulator), operation="save")

    result = result_of(manipulator.save(item, path=str(tmp_path / "x.txt")))
    assert result["format"] == "mine"
    assert written[str(tmp_path / "x.txt")] == "one=7"


# --- refusing rather than guessing ----------------------------------------------------------

def test_saving_nowhere_is_refused(manipulator, item):
    with pytest.raises(RequestError):
        manipulator.save(item)


def test_loading_something_that_is_not_there_says_so(manipulator, item, tmp_path):
    with pytest.raises(NotFoundError):
        manipulator.load(item, path=str(tmp_path / "absent.json"))


def test_a_file_that_is_not_json_says_so(manipulator, item, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(SerializationError):
        manipulator.load(item, path=str(path))


def test_an_object_that_cannot_serialise_itself_is_refused(manipulator, tmp_path):
    with pytest.raises(RequestError):
        manipulator.save(object(), path=str(tmp_path / "x.json"))


def test_a_kind_can_be_named_for_something_that_does_not_exist_yet(manipulator, item, tmp_path):
    """Reading a thing there is no instance of: a request runs on something, and the caller
    says what to build instead."""
    path = tmp_path / "item.json"
    manipulator.save(item, path=str(path))

    restored = result_of(manipulator.load(None, path=str(path), kind=Item))
    assert isinstance(restored, Item) and restored.value == 7


def test_refusing_to_overwrite_when_asked_to(manipulator, item, tmp_path):
    path = tmp_path / "item.json"
    manipulator.save(item, path=str(path))

    with pytest.raises(RequestError):
        manipulator.save(item, path=str(path), overwrite=False)
