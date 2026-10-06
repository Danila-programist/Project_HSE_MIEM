"""API regressions for shipment editing and access to participant documents."""

import pytest

from app.enums import DocumentKind, NodeType, Role, ShipmentStatus
from app.models import Shipment, ShipmentDocument, ShipmentEvent
from tests.conftest import login


@pytest.fixture()
def shipment_context(client, make_node, make_employee, make_shipment_type, make_document_type):
    origin = make_node(address="Москва, пункт отправления")
    destination = make_node(address="Москва, первоначальный пункт назначения")
    operator = make_employee(Role.OPERATOR, node=origin, full_name="Оператор отправления")
    shipment_type = make_shipment_type()
    document_type = make_document_type()
    login(client, *operator)
    return {
        "origin": origin,
        "destination": destination,
        "operator": operator,
        "document_type": document_type,
        "payload": {
            "sender": {"fullName": "Иван Иванов", "phone": "+79991234567"},
            "recipient": {"fullName": "Пётр Петров", "phone": "+79997654321"},
            "destinationNodeId": destination.id,
            "shipmentTypeId": shipment_type.id,
            "weightKg": 1.5,
            "lengthCm": 10,
            "widthCm": 20,
            "heightCm": 30,
            "description": "Книги",
        },
    }


@pytest.fixture()
def shipment(client, shipment_context):
    response = client.post("/api/v1/shipments", json=shipment_context["payload"])
    assert response.status_code == 201, response.text
    return response.json()


def _read_card(client, shipment):
    response = client.get(f"/api/v1/shipments/{shipment['id']}")
    assert response.status_code == 200, response.text
    return response.json()


def _invalid_reference(case, context, make_node):
    if case == "missing_type":
        return {"shipmentTypeId": 999999}
    if case == "missing_destination":
        destination_id = 999999
    elif case == "inactive_destination":
        destination_id = make_node(active=False).id
    elif case == "sorting_destination":
        destination_id = make_node(type_=NodeType.SORTING_CENTER).id
    else:
        assert case == "origin_destination"
        destination_id = context["origin"].id
    return {"destinationNodeId": destination_id}


INVALID_REFERENCES = [
    "missing_destination",
    "inactive_destination",
    "sorting_destination",
    "origin_destination",
    "missing_type",
]


def _assert_invalid_reference(response, patch):
    assert response.status_code == 400, response.text
    error = response.json()
    assert error["code"] == "VALIDATION_ERROR"
    assert [item["field"] for item in error["fieldErrors"]] == list(patch)


def _accept(client, shipment, context):
    response = client.post(
        f"/api/v1/shipments/{shipment['id']}/accept",
        json={
            "senderDocument": {
                "documentTypeId": context["document_type"].id,
                "series": "4012",
                "number": "112233",
            }
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _seed_documents(db_session, shipment, context, status):
    """Keep both documents present to exercise permissions independently of missing data."""
    stored = db_session.get(Shipment, shipment["id"])
    stored.status = status
    for kind in (DocumentKind.SENDER, DocumentKind.RECIPIENT):
        db_session.add(
            ShipmentDocument(
                shipment_id=stored.id,
                kind=kind,
                document_type_id=context["document_type"].id,
                number=f"{kind.value}-123456",
                recorded_by_id=context["operator"][0].id,
            )
        )
    db_session.flush()


def test_patch_updates_all_fields_and_destination_address(
    client, shipment, shipment_context, make_node, make_shipment_type
):
    destination = make_node(address="Санкт-Петербург, новый пункт назначения")
    shipment_type = make_shipment_type(name="Документы")
    payload = {
        "sender": {"fullName": "Анна Сидорова", "phone": "+79990001122"},
        "recipient": {"fullName": "Олег Смирнов", "phone": "+79993334455"},
        "destinationNodeId": destination.id,
        "shipmentTypeId": shipment_type.id,
        "weightKg": 2.75,
        "lengthCm": 11.5,
        "widthCm": 22.5,
        "heightCm": 33.5,
        "description": "Исправленное описание",
    }
    response = client.patch(f"/api/v1/shipments/{shipment['id']}", json=payload)
    assert response.status_code == 200, response.text
    updated = response.json()
    for field in (
        "sender",
        "recipient",
        "weightKg",
        "lengthCm",
        "widthCm",
        "heightCm",
        "description",
    ):
        assert updated[field] == payload[field]
    assert updated["destinationNode"]["id"] == destination.id
    assert updated["deliveryAddress"] == destination.address
    assert updated["shipmentType"] == {
        "id": shipment_type.id,
        "code": shipment_type.code,
        "name": shipment_type.name,
    }
    for field in ("id", "trackNumber", "status", "originNode", "currentNode", "createdAt"):
        assert updated[field] == shipment[field]
    assert updated["originNode"]["id"] == shipment_context["origin"].id
    assert _read_card(client, shipment) == updated


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="omitted"),
        pytest.param({"weightKg": 3.25}, id="partial"),
        pytest.param(
            {
                "sender": None,
                "recipient": None,
                "destinationNodeId": None,
                "shipmentTypeId": None,
                "weightKg": None,
                "lengthCm": None,
                "widthCm": None,
                "heightCm": None,
            },
            id="explicit-null",
        ),
    ],
)
def test_patch_omitted_and_null_fields_preserve_existing_values(client, shipment, payload):
    response = client.patch(f"/api/v1/shipments/{shipment['id']}", json=payload)
    assert response.status_code == 200, response.text
    expected = dict(shipment)
    if payload.get("weightKg") is not None:
        expected["weightKg"] = payload["weightKg"]
    assert response.json() == expected
    assert _read_card(client, shipment) == expected


@pytest.mark.parametrize("description", [None, ""])
def test_patch_can_clear_description_explicitly(client, shipment, description):
    response = client.patch(
        f"/api/v1/shipments/{shipment['id']}", json={"description": description}
    )
    assert response.status_code == 200, response.text
    expected = {**shipment, "description": description}
    assert response.json() == expected
    assert _read_card(client, shipment) == expected


@pytest.mark.parametrize("case", INVALID_REFERENCES)
def test_patch_rejects_invalid_destination_or_type(
    client, shipment, shipment_context, make_node, case
):
    payload = _invalid_reference(case, shipment_context, make_node)
    response = client.patch(f"/api/v1/shipments/{shipment['id']}", json=payload)
    _assert_invalid_reference(response, payload)
    assert _read_card(client, shipment) == shipment


@pytest.mark.parametrize("case", INVALID_REFERENCES)
def test_create_rejects_invalid_destination_or_type(
    client, db_session, shipment_context, make_node, case
):
    invalid = _invalid_reference(case, shipment_context, make_node)
    payload = {**shipment_context["payload"], **invalid}
    response = client.post("/api/v1/shipments", json=payload)
    _assert_invalid_reference(response, invalid)
    assert db_session.query(Shipment).count() == 0
    assert db_session.query(ShipmentEvent).count() == 0


@pytest.mark.parametrize(
    ("role", "node_key"),
    [
        (Role.SORTING_EMPLOYEE, "origin"),
        (Role.ADMIN, None),
        (Role.OPERATOR, "destination"),
        (Role.OPERATOR, None),
    ],
)
def test_patch_requires_origin_operator(
    client, db_session, shipment, shipment_context, make_employee, role, node_key
):
    node = shipment_context[node_key] if node_key else None
    login(client, *make_employee(role, node=node))
    response = client.patch(
        f"/api/v1/shipments/{shipment['id']}", json={"description": "Чужое изменение"}
    )
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
    assert db_session.get(Shipment, shipment["id"]).description == shipment["description"]


def test_patch_after_accept_is_conflict_and_leaves_card_unchanged(
    client, shipment, shipment_context
):
    accepted = _accept(client, shipment, shipment_context)
    response = client.patch(
        f"/api/v1/shipments/{shipment['id']}", json={"description": "Позднее изменение"}
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "INVALID_TRANSITION"
    assert _read_card(client, shipment) == accepted


def test_requisites_follow_lifecycle_and_do_not_reveal_other_participant(
    client, shipment, shipment_context, make_employee
):
    base_url = f"/api/v1/shipments/{shipment['id']}"
    assert client.get(f"{base_url}/requisites").status_code == 403
    _accept(client, shipment, shipment_context)

    response = client.get(f"{base_url}/requisites")
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    sender = response.json()["sender"]
    assert sender["number"] == "112233"
    assert sender["series"] == "4012"
    assert sender["documentType"]["id"] == shipment_context["document_type"].id
    assert sender["recordedBy"] == shipment_context["operator"][0].full_name
    assert sender["recordedAt"]
    assert response.json()["recipient"] is None

    response = client.post(
        f"{base_url}/dispatch", json={"nextNodeId": shipment_context["destination"].id}
    )
    assert response.status_code == 200, response.text
    destination_operator = make_employee(
        Role.OPERATOR, node=shipment_context["destination"], full_name="Оператор выдачи"
    )
    login(client, *destination_operator)
    assert client.get(f"{base_url}/requisites").status_code == 403
    response = client.post(f"{base_url}/arrive")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY_FOR_PICKUP"
    assert client.get(f"{base_url}/requisites").status_code == 403

    response = client.post(
        f"{base_url}/issue",
        json={
            "recipientDocument": {
                "documentTypeId": shipment_context["document_type"].id,
                "series": "5013",
                "number": "445566",
            }
        },
    )
    assert response.status_code == 200, response.text
    response = client.get(f"{base_url}/requisites")
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["sender"] is None
    recipient = response.json()["recipient"]
    assert recipient["number"] == "445566"
    assert recipient["series"] == "5013"
    assert recipient["documentType"]["id"] == shipment_context["document_type"].id
    assert recipient["recordedBy"] == destination_operator[0].full_name
    assert recipient["recordedAt"]

    login(client, *shipment_context["operator"])
    response = client.get(f"{base_url}/requisites")
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"sender": sender, "recipient": None}


@pytest.mark.parametrize(
    ("role", "node_key"),
    [
        (Role.SORTING_EMPLOYEE, "origin"),
        (Role.ADMIN, None),
        (Role.OPERATOR, "unrelated"),
        (Role.OPERATOR, None),
    ],
)
def test_requisites_reject_unrelated_nodes_and_nonoperators(
    client, db_session, shipment, shipment_context, make_node, make_employee, role, node_key
):
    _seed_documents(db_session, shipment, shipment_context, ShipmentStatus.ISSUED)
    if node_key == "unrelated":
        node = make_node()
    else:
        node = shipment_context[node_key] if node_key else None
    login(client, *make_employee(role, node=node))
    response = client.get(f"/api/v1/shipments/{shipment['id']}/requisites")
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
    assert "sender" not in response.json()
    assert "recipient" not in response.json()


@pytest.mark.parametrize(
    ("node_key", "status"),
    [
        ("origin", ShipmentStatus.CREATED),
        ("destination", ShipmentStatus.CREATED),
        ("destination", ShipmentStatus.ACCEPTED),
        ("destination", ShipmentStatus.READY_FOR_PICKUP),
    ],
)
def test_requisites_require_correct_status_even_if_documents_exist(
    client, db_session, shipment, shipment_context, make_employee, node_key, status
):
    _seed_documents(db_session, shipment, shipment_context, status)
    if node_key != "origin":
        login(client, *make_employee(Role.OPERATOR, node=shipment_context[node_key]))
    response = client.get(f"/api/v1/shipments/{shipment['id']}/requisites")
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
