import pytest

from app.enums import NodeType, Role
from tests.conftest import login


@pytest.fixture()
def topology(make_node, make_employee, make_shipment_type, make_document_type):
    origin = make_node(type_=NodeType.SERVICE_POINT, name="Пункт А")
    hub = make_node(type_=NodeType.SORTING_CENTER, name="Сортцентр")
    destination = make_node(type_=NodeType.SERVICE_POINT, name="Пункт Б")

    origin_operator, origin_password = make_employee(Role.OPERATOR, node=origin, login="op_origin")
    hub_sorter, hub_password = make_employee(Role.SORTING_EMPLOYEE, node=hub, login="sorter_hub")
    dest_operator, dest_password = make_employee(Role.OPERATOR, node=destination, login="op_dest")

    stype = make_shipment_type()
    doc_type = make_document_type()

    return {
        "origin": origin,
        "hub": hub,
        "destination": destination,
        "origin_operator": (origin_operator, origin_password),
        "hub_sorter": (hub_sorter, hub_password),
        "dest_operator": (dest_operator, dest_password),
        "shipment_type": stype,
        "document_type": doc_type,
    }


def _create_shipment(client, topology):
    payload = {
        "sender": {"fullName": "Иван Иванов", "phone": "+79991234567"},
        "recipient": {"fullName": "Пётр Петров", "phone": "+79997654321"},
        "destinationNodeId": topology["destination"].id,
        "shipmentTypeId": topology["shipment_type"].id,
        "weightKg": 1.5,
        "lengthCm": 10,
        "widthCm": 10,
        "heightCm": 10,
    }
    resp = client.post("/api/v1/shipments", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_full_lifecycle_happy_path(client, topology):
    employee, password = topology["origin_operator"]
    login(client, employee, password)
    shipment = _create_shipment(client, topology)
    shipment_id = shipment["id"]
    assert shipment["status"] == "CREATED"

    accept_resp = client.post(
        f"/api/v1/shipments/{shipment_id}/accept",
        json={"senderDocument": {"documentTypeId": topology["document_type"].id, "number": "1234 567890"}},
    )
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "ACCEPTED"

    dispatch_resp = client.post(
        f"/api/v1/shipments/{shipment_id}/dispatch",
        json={"nextNodeId": topology["hub"].id},
    )
    assert dispatch_resp.status_code == 200
    assert dispatch_resp.json()["status"] == "DISPATCHED"

    hub_employee, hub_password = topology["hub_sorter"]
    login(client, hub_employee, hub_password)

    arrive_hub_resp = client.post(f"/api/v1/shipments/{shipment_id}/arrive")
    assert arrive_hub_resp.status_code == 200
    assert arrive_hub_resp.json()["status"] == "ARRIVED"

    dispatch_to_dest_resp = client.post(
        f"/api/v1/shipments/{shipment_id}/dispatch",
        json={"nextNodeId": topology["destination"].id},
    )
    assert dispatch_to_dest_resp.status_code == 200
    assert dispatch_to_dest_resp.json()["status"] == "DISPATCHED"

    dest_employee, dest_password = topology["dest_operator"]
    login(client, dest_employee, dest_password)

    arrive_dest_resp = client.post(f"/api/v1/shipments/{shipment_id}/arrive")
    assert arrive_dest_resp.status_code == 200
    assert arrive_dest_resp.json()["status"] == "READY_FOR_PICKUP"

    issue_resp = client.post(
        f"/api/v1/shipments/{shipment_id}/issue",
        json={"recipientDocument": {"documentTypeId": topology["document_type"].id, "number": "9876 543210"}},
    )
    assert issue_resp.status_code == 200
    assert issue_resp.json()["status"] == "ISSUED"

    history_resp = client.get(f"/api/v1/shipments/{shipment_id}/history")
    assert history_resp.status_code == 200
    operations = [e["operation"] for e in history_resp.json()]
    assert operations == ["CREATE", "ACCEPT", "DISPATCH", "ARRIVE", "DISPATCH", "ARRIVE", "ISSUE"]


def test_accept_wrong_role_is_forbidden(client, topology):
    origin_employee, origin_password = topology["origin_operator"]
    login(client, origin_employee, origin_password)
    shipment = _create_shipment(client, topology)

    hub_employee, hub_password = topology["hub_sorter"]
    login(client, hub_employee, hub_password)

    resp = client.post(
        f"/api/v1/shipments/{shipment['id']}/accept",
        json={"senderDocument": {"documentTypeId": topology["document_type"].id, "number": "1234"}},
    )
    assert resp.status_code == 403


def test_accept_twice_is_conflict(client, topology):
    employee, password = topology["origin_operator"]
    login(client, employee, password)
    shipment = _create_shipment(client, topology)
    doc_payload = {"senderDocument": {"documentTypeId": topology["document_type"].id, "number": "1234"}}

    first = client.post(f"/api/v1/shipments/{shipment['id']}/accept", json=doc_payload)
    assert first.status_code == 200

    second = client.post(f"/api/v1/shipments/{shipment['id']}/accept", json=doc_payload)
    assert second.status_code == 409
    assert second.json()["code"] == "INVALID_TRANSITION"


def test_dispatch_from_non_origin_node_is_forbidden(client, topology, make_node, make_employee):
    employee, password = topology["origin_operator"]
    login(client, employee, password)
    shipment = _create_shipment(client, topology)
    client.post(
        f"/api/v1/shipments/{shipment['id']}/accept",
        json={"senderDocument": {"documentTypeId": topology["document_type"].id, "number": "1234"}},
    )

    other_node = make_node(type_=NodeType.SERVICE_POINT, name="Другой пункт")
    other_operator, other_password = make_employee(Role.OPERATOR, node=other_node, login="op_other")
    login(client, other_operator, other_password)

    resp = client.post(
        f"/api/v1/shipments/{shipment['id']}/dispatch",
        json={"nextNodeId": topology["hub"].id},
    )
    assert resp.status_code == 403


def test_dispatch_to_invalid_next_node_is_rejected(client, topology):
    employee, password = topology["origin_operator"]
    login(client, employee, password)
    shipment = _create_shipment(client, topology)
    client.post(
        f"/api/v1/shipments/{shipment['id']}/accept",
        json={"senderDocument": {"documentTypeId": topology["document_type"].id, "number": "1234"}},
    )

    resp = client.post(
        f"/api/v1/shipments/{shipment['id']}/dispatch",
        json={"nextNodeId": topology["origin"].id},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_arrive_at_wrong_node_is_forbidden(client, topology):
    employee, password = topology["origin_operator"]
    login(client, employee, password)
    shipment = _create_shipment(client, topology)
    client.post(
        f"/api/v1/shipments/{shipment['id']}/accept",
        json={"senderDocument": {"documentTypeId": topology["document_type"].id, "number": "1234"}},
    )
    client.post(f"/api/v1/shipments/{shipment['id']}/dispatch", json={"nextNodeId": topology["hub"].id})

    dest_employee, dest_password = topology["dest_operator"]
    login(client, dest_employee, dest_password)

    resp = client.post(f"/api/v1/shipments/{shipment['id']}/arrive")
    assert resp.status_code == 403


def test_issue_before_ready_for_pickup_is_conflict(client, topology):
    employee, password = topology["origin_operator"]
    login(client, employee, password)
    shipment = _create_shipment(client, topology)

    resp = client.post(
        f"/api/v1/shipments/{shipment['id']}/issue",
        json={"recipientDocument": {"documentTypeId": topology["document_type"].id, "number": "1234"}},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_TRANSITION"


def test_issue_at_wrong_destination_is_forbidden(client, topology, make_node, make_employee):
    employee, password = topology["origin_operator"]
    login(client, employee, password)
    shipment = _create_shipment(client, topology)
    client.post(
        f"/api/v1/shipments/{shipment['id']}/accept",
        json={"senderDocument": {"documentTypeId": topology["document_type"].id, "number": "1234"}},
    )
    client.post(f"/api/v1/shipments/{shipment['id']}/dispatch", json={"nextNodeId": topology["destination"].id})

    dest_employee, dest_password = topology["dest_operator"]
    login(client, dest_employee, dest_password)
    client.post(f"/api/v1/shipments/{shipment['id']}/arrive")

    other_node = make_node(type_=NodeType.SERVICE_POINT, name="Третий пункт")
    other_operator, other_password = make_employee(Role.OPERATOR, node=other_node, login="op_third")
    login(client, other_operator, other_password)

    resp = client.post(
        f"/api/v1/shipments/{shipment['id']}/issue",
        json={"recipientDocument": {"documentTypeId": topology["document_type"].id, "number": "1234"}},
    )
    assert resp.status_code == 403
