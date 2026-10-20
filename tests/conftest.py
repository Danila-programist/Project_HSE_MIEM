import itertools
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db import Base, get_db
from app.enums import NodeType
from app.main import app
from app.models import DocumentType, Employee, Node, ShipmentType
from app.security import hash_password
from tests.fake_db import FakeSession

_counter = itertools.count(1)


@pytest.fixture(scope="session")
def postgres_engine():
    """При явном TEST_DATABASE_URL создаёт отдельную схему на весь запуск."""
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        yield None
        return

    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("TEST_DATABASE_URL must point to PostgreSQL")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")

    schema_name = f"pytest_{uuid4().hex}"
    admin_engine = create_engine(url)
    test_engine = None
    schema_created = False
    try:
        with admin_engine.begin() as connection:
            connection.execute(CreateSchema(schema_name))
        schema_created = True

        # Every connection, including those used by locking tests, sees only
        # this run's tables and enum types; public is deliberately excluded.
        test_engine = create_engine(
            url, connect_args={"options": f"-csearch_path={schema_name}"}
        )
        Base.metadata.create_all(test_engine)
        yield test_engine
    finally:
        if test_engine is not None:
            test_engine.dispose()
        try:
            if schema_created:
                with admin_engine.begin() as connection:
                    connection.execute(DropSchema(schema_name, cascade=True))
        finally:
            admin_engine.dispose()


@pytest.fixture()
def db_session(postgres_engine):
    """Пустое хранилище на тест: FakeSession либо транзакция PostgreSQL."""
    if postgres_engine is None:
        session = FakeSession()
        try:
            yield session
        finally:
            session.close()
        return

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
            autoflush=False,
        )
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


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
