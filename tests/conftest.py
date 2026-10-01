import itertools

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.enums import NodeType
from app.main import app
from app.models import DocumentType, Employee, Node, ShipmentType
from app.security import hash_password
from tests.fake_db import FakeSession

_counter = itertools.count(1)


@pytest.fixture()
def db_session():
    """Фейковая сессия в памяти: каждый тест получает пустое хранилище."""
    session = FakeSession()
    yield session
    session.close()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def make_node(db_session):
    def _make(type_=NodeType.SERVICE_POINT, name=None, address="Тестовый адрес", active=True):
        n = next(_counter)
        node = Node(
            name=name or f"Узел {n}",
            type=type_,
            address=address,
            active=active,
        )
        db_session.add(node)
        db_session.flush()
        return node

    return _make


@pytest.fixture()
def make_employee(db_session):
    def _make(role, node=None, login=None, password="secret123", blocked=False, full_name="Тестовый сотрудник"):
        n = next(_counter)
        emp = Employee(
            login=login or f"user{n}",
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
            node_id=node.id if node else None,
            blocked=blocked,
        )
        db_session.add(emp)
        db_session.flush()
        return emp, password

    return _make


@pytest.fixture()
def make_shipment_type(db_session):
    def _make(code=None, name="Посылка"):
        n = next(_counter)
        st = ShipmentType(code=code or f"TYPE{n}", name=name)
        db_session.add(st)
        db_session.flush()
        return st

    return _make


@pytest.fixture()
def make_document_type(db_session):
    def _make(code=None, name="Паспорт"):
        n = next(_counter)
        dt = DocumentType(code=code or f"DOC{n}", name=name)
        db_session.add(dt)
        db_session.flush()
        return dt

    return _make


def login(client, employee, password):
    resp = client.post("/api/v1/auth/login", json={"login": employee.login, "password": password})
    assert resp.status_code == 200, resp.text
