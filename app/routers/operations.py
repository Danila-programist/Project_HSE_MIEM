from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser
from ..enums import DocumentKind, NodeType, Operation, Role, ShipmentStatus
from ..errors import conflict, forbidden, not_found, validation_error
from ..models import DocumentType, Node, Shipment, ShipmentDocument, ShipmentEvent
from ..schemas import AcceptRequest, DispatchRequest, IssueRequest, ShipmentCard
from ..serializers import shipment_card

router = APIRouter(tags=["Операции"])


def _lock(db: Session, shipment_id: int) -> Shipment:
    s = db.execute(select(Shipment).where(Shipment.id == shipment_id).with_for_update()).scalar_one_or_none()
    if s is None:
        raise not_found()
    return s


def _validate_document(db: Session, doc_in) -> DocumentType:
    dt = db.get(DocumentType, doc_in.documentTypeId)
    if dt is None:
        raise validation_error(
            "Неизвестный тип документа",
            [{"field": "documentTypeId", "message": "Тип документа не найден"}],
        )
    if not doc_in.number or not doc_in.number.strip():
        raise validation_error(
            "Укажите номер документа",
            [{"field": "number", "message": "Обязательное поле"}],
        )
    return dt


@router.post("/shipments/{shipmentId}/accept", response_model=ShipmentCard)
def accept_shipment(
    shipmentId: int, payload: AcceptRequest, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
):
    if user.role != Role.OPERATOR or user.node_id is None:
        raise forbidden()
    s = _lock(db, shipmentId)
    if s.status != ShipmentStatus.CREATED:
        raise conflict("INVALID_TRANSITION", "Недопустимый переход состояния")
    if s.origin_node_id != user.node_id:
        raise forbidden()

    dt = _validate_document(db, payload.senderDocument)

    now = datetime.now(timezone.utc)
    db.add(
        ShipmentDocument(
            shipment_id=s.id,
            kind=DocumentKind.SENDER,
            document_type_id=dt.id,
            series=payload.senderDocument.series,
            number=payload.senderDocument.number,
            recorded_at=now,
            recorded_by_id=user.id,
        )
    )
    s.status = ShipmentStatus.ACCEPTED
    s.accepted_at = now
    db.add(
        ShipmentEvent(
            shipment_id=s.id,
            operation=Operation.ACCEPT,
            resulting_status=ShipmentStatus.ACCEPTED,
            node_id=s.current_node_id,
            employee_id=user.id,
        )
    )
    db.commit()
    db.refresh(s)
    return shipment_card(s, for_operator=True)


@router.post("/shipments/{shipmentId}/dispatch", response_model=ShipmentCard)
def dispatch_shipment(
    shipmentId: int, payload: DispatchRequest, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
):
    s = _lock(db, shipmentId)

    if s.status == ShipmentStatus.ACCEPTED:
        if user.role != Role.OPERATOR or user.node_id != s.origin_node_id:
            raise forbidden()
    elif s.status == ShipmentStatus.ARRIVED:
        if user.role != Role.SORTING_EMPLOYEE or user.node_id != s.current_node_id:
            raise forbidden()
    else:
        raise conflict("INVALID_TRANSITION", "Недопустимый переход состояния")

    next_node = db.get(Node, payload.nextNodeId)
    if next_node is None or not next_node.active:
        raise validation_error(
            "Следующий узел должен быть активным",
            [{"field": "nextNodeId", "message": "Узел недоступен"}],
        )
    if next_node.id == s.current_node_id:
        raise validation_error(
            "Следующий узел должен отличаться от текущего",
            [{"field": "nextNodeId", "message": "Выберите другой узел"}],
        )
    if not (next_node.type == NodeType.SORTING_CENTER or next_node.id == s.destination_node_id):
        raise validation_error(
            "Следующим узлом может быть сортировочный центр или пункт назначения",
            [{"field": "nextNodeId", "message": "Недопустимый узел"}],
        )

    s.next_node_id = next_node.id
    s.status = ShipmentStatus.DISPATCHED
    db.add(
        ShipmentEvent(
            shipment_id=s.id,
            operation=Operation.DISPATCH,
            resulting_status=ShipmentStatus.DISPATCHED,
            node_id=s.current_node_id,
            next_node_id=next_node.id,
            employee_id=user.id,
        )
    )
    db.commit()
    db.refresh(s)
    return shipment_card(s, for_operator=(user.role == Role.OPERATOR))


@router.post("/shipments/{shipmentId}/arrive", response_model=ShipmentCard)
def arrive_shipment(shipmentId: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    if user.role not in (Role.OPERATOR, Role.SORTING_EMPLOYEE) or user.node_id is None:
        raise forbidden()
    s = _lock(db, shipmentId)
    if s.status != ShipmentStatus.DISPATCHED:
        raise conflict("INVALID_TRANSITION", "Недопустимый переход состояния")
    if s.next_node_id != user.node_id:
        raise forbidden()

    new_status = (
        ShipmentStatus.READY_FOR_PICKUP if s.destination_node_id == user.node_id else ShipmentStatus.ARRIVED
    )
    s.current_node_id = user.node_id
    s.next_node_id = None
    s.status = new_status
    db.add(
        ShipmentEvent(
            shipment_id=s.id,
            operation=Operation.ARRIVE,
            resulting_status=new_status,
            node_id=user.node_id,
            employee_id=user.id,
        )
    )
    db.commit()
    db.refresh(s)
    return shipment_card(s, for_operator=(user.role == Role.OPERATOR))


@router.post("/shipments/{shipmentId}/issue", response_model=ShipmentCard)
def issue_shipment(
    shipmentId: int, payload: IssueRequest, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
):
    if user.role != Role.OPERATOR or user.node_id is None:
        raise forbidden()
    s = _lock(db, shipmentId)
    if s.status != ShipmentStatus.READY_FOR_PICKUP:
        raise conflict("INVALID_TRANSITION", "Отправление уже выдано; дальнейшие операции невозможны")
    if s.destination_node_id != user.node_id:
        raise forbidden()

    dt = _validate_document(db, payload.recipientDocument)

    now = datetime.now(timezone.utc)
    db.add(
        ShipmentDocument(
            shipment_id=s.id,
            kind=DocumentKind.RECIPIENT,
            document_type_id=dt.id,
            series=payload.recipientDocument.series,
            number=payload.recipientDocument.number,
            recorded_at=now,
            recorded_by_id=user.id,
        )
    )
    s.status = ShipmentStatus.ISSUED
    s.issued_at = now
    db.add(
        ShipmentEvent(
            shipment_id=s.id,
            operation=Operation.ISSUE,
            resulting_status=ShipmentStatus.ISSUED,
            node_id=s.destination_node_id,
            employee_id=user.id,
        )
    )
    db.commit()
    db.refresh(s)
    return shipment_card(s, for_operator=True)