# test_adapters.py
"""The domain behind three adapters: HTTP, a command line, and SQL storage.

The documentation claims MSB is a domain layer any adapter can sit on without the domain changing.
Claims are tests here. The HTTP half runs when FastAPI is installed and is skipped otherwise, since
MSB itself depends on nothing.
"""
import argparse
import json
import sqlite3

import pytest

from msb_arch import BaseContainer, BaseEntity, Manipulator, Super, invariant


class Client(BaseEntity):
    credit: float = 0.0

    @invariant("credit cannot be negative")
    def _solvent(self) -> bool:
        return self.credit >= 0


class Clients(BaseContainer[Client]):
    pass


class Discount(Super):
    OPERATION = "discount"

    def _discount_clients(self, obj, attributes):
        rate = attributes.get("rate", 0.1)
        return {client.name: round(client.credit * rate, 2) for client in obj.get_items()}


class Service(Manipulator):
    pass


@pytest.fixture
def service():
    book = Clients(name="book")
    book.add(Client(name="ada", credit=100.0))
    orchestrator = Service(base_classes=[Client, Clients], managing_object=book)
    orchestrator.register_operation(Discount(orchestrator))
    return orchestrator


def test_crud_is_four_requests(service):
    book = service.get_managing_object()

    service.configure(book, add=Client.from_dict({"name": "bob", "credit": 10.0}))
    assert service.inspect(service.locate(["book", "bob"]), get="credit") == 10.0

    service.configure(service.locate(["book", "bob"]), set={"params": {"credit": 20.0}})
    assert book.get("bob").credit == 20.0

    refused = service.configure(service.locate(["book", "bob"]),
                                set={"params": {"credit": -1.0}}, raise_on_error=False)
    assert refused.ok is False and book.get("bob").credit == 20.0

    service.configure(book, remove="bob")
    assert not book.has_item("bob")


def test_a_command_line_builds_its_flags_from_the_catalogue(service):
    accepts = service.describe_operations("discount")["discount"]["clients"]["accepts"]
    parser = argparse.ArgumentParser()
    for key in accepts:
        parser.add_argument(f"--{key}", type=float)

    given = {k: v for k, v in vars(parser.parse_args(["--rate", "0.5"])).items() if v is not None}

    assert accepts == ["rate"]
    assert service.discount(**given) == {"ada": 50.0}


def test_storage_moves_to_sql_without_the_domain_noticing(service, tmp_path):
    class SqlSave(Super):
        OPERATION = "save"

        def _save(self, obj, attributes):
            with sqlite3.connect(attributes["path"]) as db:
                db.execute("CREATE TABLE IF NOT EXISTS models (name TEXT PRIMARY KEY, data TEXT)")
                db.execute("INSERT OR REPLACE INTO models VALUES (?, ?)",
                           (obj.name, json.dumps(obj.to_dict())))
            return True

    class SqlLoad(Super):
        OPERATION = "load"

        def _load(self, obj, attributes):
            with sqlite3.connect(attributes["path"]) as db:
                (data,) = db.execute("SELECT data FROM models WHERE name = ?",
                                     (obj.name,)).fetchone()
            return type(obj).from_dict(json.loads(data))

    service.register_operation(SqlSave(service))
    service.register_operation(SqlLoad(service))
    book = service.get_managing_object()
    database = str(tmp_path / "book.db")

    service.save(book, path=database)

    assert service.load(book, path=database) == book


def test_the_domain_sits_behind_http(service):
    fastapi = pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")

    app = fastapi.FastAPI()

    @app.post("/request")
    def handle(body: dict):
        target = service.locate(body["path"]) if body.get("path") else None
        return dict(service.process_request({"operation": body["operation"], "obj": target,
                                             "attributes": body.get("attributes", {})}))

    @app.get("/operations")
    def operations():
        return service.describe_operations("discount")

    http = testclient.TestClient(app)

    updated = http.post("/request", json={"operation": "configure", "path": ["book", "ada"],
                                          "attributes": {"set": {"params": {"credit": 40.0}}}})
    assert updated.status_code == 200 and updated.json()["status"] is True

    refused = http.post("/request", json={"operation": "configure", "path": ["book", "ada"],
                                          "attributes": {"set": {"params": {"credit": -1.0}}}})
    assert refused.json()["status"] is False

    priced = http.post("/request", json={"operation": "discount", "attributes": {"rate": 0.25}})
    assert priced.json()["result"] == {"ada": 10.0}

    assert http.get("/operations").json()["discount"]["clients"]["accepts"] == ["rate"]
