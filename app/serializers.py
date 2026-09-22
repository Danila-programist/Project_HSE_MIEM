from .enums import OPERATION_NAMES, STATUS_NAMES
from .models import Employee, Node, Shipment, ShipmentDocument, ShipmentEvent
from .schemas import (
    DictionaryItem,
    NodeRef,
    Participant,
    PublicEvent,
    PublicTracking,
    RecordedDocument,
    ShipmentCard,
    ShipmentEvent as ShipmentEventSchema,
    ShipmentEventEmployee,
    ShipmentListItem,
)


def node_ref(node: Node) -> NodeRef:
    return NodeRef(id=node.id, name=node.name, type=node.type)


def dict_item(obj) -> DictionaryItem:
    return DictionaryItem(id=obj.id, code=obj.code, name=obj.name)


def _base_card(shipment: Shipment) -> dict:
    return dict(
        id=shipment.id,
        trackNumber=shipment.track_number,
        status=shipment.status,
        statusName=STATUS_NAMES[shipment.status],
        originNode=node_ref(shipment.origin_node),
        destinationNode=node_ref(shipment.destination_node),
        currentNode=node_ref(shipment.current_node),
        nextNode=node_ref(shipment.next_node) if shipment.next_node else None,
        deliveryAddress=shipment.delivery_address,
        shipmentType=dict_item(shipment.shipment_type),
        weightKg=float(shipment.weight_kg),
        lengthCm=float(shipment.length_cm),
        widthCm=float(shipment.width_cm),
        heightCm=float(shipment.height_cm),
        description=shipment.description,
        createdAt=shipment.created_at,
        acceptedAt=shipment.accepted_at,
        issuedAt=shipment.issued_at,
    )


def shipment_card(shipment: Shipment, for_operator: bool) -> ShipmentCard:
    data = _base_card(shipment)
    if for_operator:
        data["sender"] = Participant(fullName=shipment.sender_full_name, phone=shipment.sender_phone)
        data["recipient"] = Participant(
            fullName=shipment.recipient_full_name, phone=shipment.recipient_phone
        )
    else:
        data["sender"] = None
        data["recipient"] = None
    return ShipmentCard(**data)


def shipment_list_item(shipment: Shipment) -> ShipmentListItem:
    return ShipmentListItem(
        id=shipment.id,
        trackNumber=shipment.track_number,
        status=shipment.status,
        statusName=STATUS_NAMES[shipment.status],
        originNode=node_ref(shipment.origin_node),
        destinationNode=node_ref(shipment.destination_node),
        currentNode=node_ref(shipment.current_node),
        nextNode=node_ref(shipment.next_node) if shipment.next_node else None,
        createdAt=shipment.created_at,
    )


def shipment_event(event: ShipmentEvent) -> ShipmentEventSchema:
    return ShipmentEventSchema(
        id=event.id,
        operation=event.operation,
        operationName=OPERATION_NAMES[event.operation],
        resultingStatus=event.resulting_status,
        resultingStatusName=STATUS_NAMES[event.resulting_status],
        node=node_ref(event.node),
        nextNode=node_ref(event.next_node) if event.next_node else None,
        occurredAt=event.occurred_at,
        employee=ShipmentEventEmployee(id=event.employee.id, fullName=event.employee.full_name),
    )


def recorded_document(doc: ShipmentDocument) -> RecordedDocument:
    return RecordedDocument(
        documentType=dict_item(doc.document_type),
        series=doc.series,
        number=doc.number,
        recordedAt=doc.recorded_at,
        recordedBy=doc.recorded_by.full_name,
    )


def public_tracking(shipment: Shipment, events: list[ShipmentEvent]) -> PublicTracking:
    return PublicTracking(
        trackNumber=shipment.track_number,
        status=shipment.status,
        statusName=STATUS_NAMES[shipment.status],
        currentNodeName=shipment.current_node.name,
        nextNodeName=shipment.next_node.name if shipment.next_node else None,
        events=[
            PublicEvent(
                occurredAt=e.occurred_at,
                statusName=STATUS_NAMES[e.resulting_status],
                nodeName=e.node.name,
                nextNodeName=e.next_node.name if e.next_node else None,
            )
            for e in events
        ],
    )


def employee_to_user_payload(emp: Employee) -> dict:
    return dict(
        id=emp.id,
        login=emp.login,
        fullName=emp.full_name,
        role=emp.role,
        node=node_ref(emp.node) if emp.node else None,
        blocked=emp.blocked,
    )