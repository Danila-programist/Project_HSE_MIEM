from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser
from ..enums import DocumentKind, NodeType, Operation, Role, ShipmentStatus
from ..errors import conflict, forbidden, not_found, validation_error
from ..models import Node, Shipment, ShipmentDocument, ShipmentEvent, ShipmentType
from ..schemas import (
    Requisites,
    ShipmentCard,
    ShipmentCreate,
    ShipmentEvent as ShipmentEventSchema,
    ShipmentPage,
    ShipmentUpdate,
)
from ..serializers import (
    recorded_document,
    shipment_card,
    shipment_event,
    shipment_list_item,
)
from ..utils import generate_track_number, normalize_track_number

router = APIRouter(tags=["Отправления"])


def _accessible(shipment: Shipment, node_id: int) -> bool:
    return node_id in {
        shipment.origin_node_id,
        shipment.current_node_id,
        shipment.next_node_id,
    }


def _load_shipment(db: Session, shipment_id: int) -> Shipment:
    s = db.get(Shipment, shipment_id)
    if s is None:
        raise not_found()
    return s


@router.get("/shipments", response_model=ShipmentPage)
def list_shipments(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    trackNumber: str | None = None,
    status: ShipmentStatus | None = None,
    direction: str = Query("ALL", pattern="^(ALL|AT_NODE|INCOMING)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    if user.role not in (Role.OPERATOR, Role.SORTING_EMPLOYEE):
        raise forbidden()
    if user.node_id is None:
        raise forbidden()

    node_id = user.node_id
    at_node = and_(
        Shipment.current_node_id == node_id,
        Shipment.status.notin_([ShipmentStatus.ISSUED, ShipmentStatus.DISPATCHED]),
    )
    incoming = and_(
        Shipment.next_node_id == node_id,
        Shipment.status == ShipmentStatus.DISPATCHED,
    )

    stmt = select(Shipment).where(Shipment.status != ShipmentStatus.ISSUED)

    if direction == "AT_NODE":
        stmt = stmt.where(at_node)
    elif direction == "INCOMING":
        stmt = stmt.where(incoming)
    else:
        stmt = stmt.where(or_(at_node, incoming))

    if status is not None:
        stmt = stmt.where(Shipment.status == status)

    if trackNumber:
        stmt = stmt.where(Shipment.track_number == normalize_track_number(trackNumber))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        db.execute(stmt.order_by(Shipment.created_at.desc(), Shipment.id.desc()).offset((page - 1) * size).limit(size))
        .scalars()
        .all()
    )

    return ShipmentPage(
        page=page,
        size=size,
        totalItems=total,
        totalPages=(total + size - 1) // size if size else 0,
        items=[shipment_list_item(s) for s in rows],
    )


@router.post("/shipments", response_model=ShipmentCard, status_code=201)
def create_shipment(
    payload: ShipmentCreate,
    response: Response,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if user.role != Role.OPERATOR:
        raise forbidden()
    origin = db.get(Node, user.node_id) if user.node_id else None
    if origin is None or not origin.active or origin.type != NodeType.SERVICE_POINT:
        raise forbidden("Пункт приёма недоступен")

    dest = db.get(Node, payload.destinationNodeId)
    if dest is None or not dest.active or dest.type != NodeType.SERVICE_POINT:
        raise validation_error(
            "Пункт назначения должен быть активным пунктом обслуживания",
            [{"field": "destinationNodeId", "message": "Недопустимый пункт назначения"}],
        )
    if dest.id == origin.id:
        raise validation_error(
            "Пункт назначения должен отличаться от пункта приёма",
            [{"field": "destinationNodeId", "message": "Выберите другой пункт назначения"}],
        )

    stype = db.get(ShipmentType, payload.shipmentTypeId)
    if stype is None:
        raise validation_error(
            "Неизвестный тип отправления",
            [{"field": "shipmentTypeId", "message": "Тип не найден"}],
        )

    for attempt in range(8):
        track = generate_track_number()
        shipment = Shipment(
            track_number=track,
            status=ShipmentStatus.CREATED,
            shipment_type_id=stype.id,
            origin_node_id=origin.id,
            destination_node_id=dest.id,
            current_node_id=origin.id,
            next_node_id=None,
            delivery_address=dest.address,
            sender_full_name=payload.sender.fullName,
            sender_phone=payload.sender.phone,
            recipient_full_name=payload.recipient.fullName,
            recipient_phone=payload.recipient.phone,
            weight_kg=payload.weightKg,
            length_cm=payload.lengthCm,
            width_cm=payload.widthCm,
            height_cm=payload.heightCm,
            description=payload.description,
        )
        db.add(shipment)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            continue
        break
    else:
        raise conflict("INTERNAL_ERROR", "Не удалось сгенерировать трек-номер")

    db.add(
        ShipmentEvent(
            shipment_id=shipment.id,
            operation=Operation.CREATE,
            resulting_status=ShipmentStatus.CREATED,
            node_id=origin.id,
            next_node_id=None,
            employee_id=user.id,
        )
    )
    db.commit()
    db.refresh(shipment)

    response.headers["Location"] = f"/api/v1/shipments/{shipment.id}"
    return shipment_card(shipment, for_operator=True)


@router.get("/shipments/{shipmentId}", response_model=ShipmentCard)
def get_shipment(shipmentId: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    if user.role not in (Role.OPERATOR, Role.SORTING_EMPLOYEE) or user.node_id is None:
        raise forbidden()
    s = _load_shipment(db, shipmentId)
    if not _accessible(s, user.node_id):
        raise forbidden()
    return shipment_card(s, for_operator=(user.role == Role.OPERATOR))


@router.patch("/shipments/{shipmentId}", response_model=ShipmentCard)
def update_shipment(
    shipmentId: int,
    payload: ShipmentUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if user.role != Role.OPERATOR or user.node_id is None:
        raise forbidden()
    s = db.execute(select(Shipment).where(Shipment.id == shipmentId).with_for_update()).scalar_one_or_none()
    if s is None:
        raise not_found()
    if s.origin_node_id != user.node_id:
        raise forbidden()
    if s.status != ShipmentStatus.CREATED:
        raise conflict("INVALID_TRANSITION", "Изменение невозможно: отправление уже принято")

    data = payload.model_dump(exclude_unset=True)

    if "destinationNodeId" in data and data["destinationNodeId"] is not None:
        dest = db.get(Node, data["destinationNodeId"])
        if dest is None or not dest.active or dest.type != NodeType.SERVICE_POINT:
            raise validation_error(
                "Недопустимый пункт назначения",
                [{"field": "destinationNodeId", "message": "Пункт назначения недоступен"}],
            )
        if dest.id == s.origin_node_id:
            raise validation_error(
                "Пункт назначения должен отличаться от пункта приёма",
                [{"field": "destinationNodeId", "message": "Выберите другой пункт"}],
            )
        s.destination_node_id = dest.id
        s.delivery_address = dest.address

    if "shipmentTypeId" in data and data["shipmentTypeId"] is not None:
        st = db.get(ShipmentType, data["shipmentTypeId"])
        if st is None:
            raise validation_error("Неизвестный тип", [{"field": "shipmentTypeId", "message": "Не найден"}])
        s.shipment_type_id = st.id

    if "sender" in data and data["sender"] is not None:
        s.sender_full_name = data["sender"]["fullName"]
        s.sender_phone = data["sender"]["phone"]
    if "recipient" in data and data["recipient"] is not None:
        s.recipient_full_name = data["recipient"]["fullName"]
        s.recipient_phone = data["recipient"]["phone"]

    for f, col in (
        ("weightKg", "weight_kg"),
        ("lengthCm", "length_cm"),
        ("widthCm", "width_cm"),
        ("heightCm", "height_cm"),
    ):
        if f in data and data[f] is not None:
            setattr(s, col, data[f])

    if "description" in data:
        s.description = data["description"]

    db.commit()
    db.refresh(s)
    return shipment_card(s, for_operator=True)


@router.get("/shipments/{shipmentId}/history", response_model=list[ShipmentEventSchema])
def get_shipment_history(shipmentId: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    if user.role not in (Role.OPERATOR, Role.SORTING_EMPLOYEE) or user.node_id is None:
        raise forbidden()
    s = _load_shipment(db, shipmentId)
    if not _accessible(s, user.node_id):
        raise forbidden()

    rows = (
        db.execute(
            select(ShipmentEvent)
            .where(ShipmentEvent.shipment_id == s.id)
            .order_by(ShipmentEvent.occurred_at.asc(), ShipmentEvent.id.asc())
        )
        .scalars()
        .all()
    )
    return [shipment_event(e) for e in rows]


@router.get("/shipments/{shipmentId}/requisites", response_model=Requisites)
def get_requisites(shipmentId: int, response: Response, user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    if user.role != Role.OPERATOR or user.node_id is None:
        raise forbidden()
    s = _load_shipment(db, shipmentId)

    is_origin = s.origin_node_id == user.node_id
    is_destination = s.destination_node_id == user.node_id
    if not (is_origin or is_destination):
        raise forbidden()

    docs = {
        d.kind: d
        for d in db.execute(select(ShipmentDocument).where(ShipmentDocument.shipment_id == s.id)).scalars().all()
    }

    result = Requisites()
    if is_origin and DocumentKind.SENDER in docs and s.status != ShipmentStatus.CREATED:
        result.sender = recorded_document(docs[DocumentKind.SENDER])
    if is_destination and DocumentKind.RECIPIENT in docs and s.status == ShipmentStatus.ISSUED:
        result.recipient = recorded_document(docs[DocumentKind.RECIPIENT])

    if result.sender is None and result.recipient is None:
        raise forbidden()

    response.headers["Cache-Control"] = "no-store"
    return result