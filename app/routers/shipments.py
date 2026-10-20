## @file
# @brief Оформление, редактирование и чтение отправлений.
#
# Доступ ограничен ролью и связанным узлом. Исходные сведения изменяются только
# до фактического приёма.
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
    ShipmentPage,
    ShipmentUpdate,
)
from ..schemas import (
    ShipmentEvent as ShipmentEventSchema,
)
from ..serializers import (
    recorded_document,
    shipment_card,
    shipment_event,
    shipment_list_item,
)
from ..utils import generate_track_number, normalize_track_number

router = APIRouter(tags=["Отправления"])


## @brief Проверяет связь узла с карточкой отправления.
#
# Доступ дают пункт приёма, текущий или следующий узел; пункт назначения сам по себе
# не включён в эту проверку.
#
# @param shipment ORM-запись отправления.
# @param node_id Идентификатор узла или None.
# @return True, если узел входит в разрешённый набор.
def _accessible(shipment: Shipment, node_id: int) -> bool:
    return node_id in {
        shipment.origin_node_id,
        shipment.current_node_id,
        shipment.next_node_id,
    }


## @brief Загружает отправление без блокировки.
#
# Использует первичный ключ; не выполняет проверку роли и узла.
#
# @param db Сессия SQLAlchemy текущего запроса.
# @param shipment_id Идентификатор отправления.
# @return ORM-объект Shipment.
# @exception errors.APIError 404 при отсутствии отправления.
def _load_shipment(db: Session, shipment_id: int) -> Shipment:
    s = db.get(Shipment, shipment_id)
    if s is None:
        raise not_found()
    return s


## @brief Проверяет пункт назначения при оформлении или исправлении отправления.
#
# Сохраняет отдельные тексты ошибок двух операций; пункт должен быть активным
# пунктом обслуживания и отличаться от пункта приёма.
#
# @param db Сессия SQLAlchemy текущего запроса.
# @param node_id Идентификатор выбранного пункта назначения.
# @param origin_id Идентификатор пункта приёма.
# @param editing Использовать сообщения исправления карточки.
# @return Проверенный узел назначения.
# @exception errors.APIError 400 при недоступном или совпадающем пункте.
def _destination_node(db: Session, node_id: int, origin_id: int, *, editing: bool = False) -> Node:
    node = db.get(Node, node_id)
    if node is None or not node.active or node.type != NodeType.SERVICE_POINT:
        message = (
            "Недопустимый пункт назначения"
            if editing
            else "Пункт назначения должен быть активным пунктом обслуживания"
        )
        field_message = (
            "Пункт назначения недоступен" if editing else "Недопустимый пункт назначения"
        )
        raise validation_error(message, [{"field": "destinationNodeId", "message": field_message}])
    if node.id == origin_id:
        field_message = "Выберите другой пункт" if editing else "Выберите другой пункт назначения"
        raise validation_error(
            "Пункт назначения должен отличаться от пункта приёма",
            [{"field": "destinationNodeId", "message": field_message}],
        )
    return node


## @brief Проверяет выбранный тип отправления.
#
# Использует сообщения оформления либо исправления карточки.
#
# @param db Сессия SQLAlchemy текущего запроса.
# @param type_id Идентификатор типа отправления.
# @param editing Использовать сообщения исправления карточки.
# @return Тип отправления из справочника.
# @exception errors.APIError 400 при неизвестном типе.
def _shipment_type(db: Session, type_id: int, *, editing: bool = False) -> ShipmentType:
    shipment_type = db.get(ShipmentType, type_id)
    if shipment_type is None:
        raise validation_error(
            "Неизвестный тип" if editing else "Неизвестный тип отправления",
            [{"field": "shipmentTypeId", "message": "Не найден" if editing else "Тип не найден"}],
        )
    return shipment_type


## @brief Сохраняет новое отправление с уникальным трек-номером без commit.
#
# После IntegrityError откатывает попытку и создаёт новую запись с новым номером.
# Событие оформления и подтверждение транзакции остаются в обработчике.
#
# @param db Сессия SQLAlchemy текущего запроса.
# @param payload Проверенные данные нового отправления.
# @param origin Пункт приёма.
# @param destination Проверенный пункт назначения.
# @param shipment_type Проверенный тип отправления.
# @return Отправление после успешного flush.
# @exception errors.APIError 409 после восьми неудачных попыток.
def _create_with_track_number(
    db: Session,
    payload: ShipmentCreate,
    origin: Node,
    destination: Node,
    shipment_type: ShipmentType,
) -> Shipment:
    for _ in range(8):
        shipment = Shipment(
            track_number=generate_track_number(),
            status=ShipmentStatus.CREATED,
            shipment_type_id=shipment_type.id,
            origin_node_id=origin.id,
            destination_node_id=destination.id,
            current_node_id=origin.id,
            next_node_id=None,
            delivery_address=destination.address,
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
        return shipment
    raise conflict("INTERNAL_ERROR", "Не удалось сгенерировать трек-номер")


## @brief Применяет исправления контактов, параметров и описания отправления.
#
# Отсутствующие поля и None пропускаются, кроме description: явный None очищает его.
# Назначение и тип отправления проверяет и меняет вызывающий обработчик.
#
# @param shipment Изменяемая ORM-запись отправления.
# @param data Только переданные поля из ShipmentUpdate.
# @note Возвращает None; изменяет поля без обращения к БД.
def _apply_shipment_details(shipment: Shipment, data: dict) -> None:
    for participant in ("sender", "recipient"):
        values = data.get(participant)
        if values is not None:
            setattr(shipment, f"{participant}_full_name", values["fullName"])
            setattr(shipment, f"{participant}_phone", values["phone"])

    for field, column in (
        ("weightKg", "weight_kg"),
        ("lengthCm", "length_cm"),
        ("widthCm", "width_cm"),
        ("heightCm", "height_cm"),
    ):
        value = data.get(field)
        if value is not None:
            setattr(shipment, column, value)

    if "description" in data:
        shipment.description = data["description"]


## @brief Отбирает реквизиты участников по статусу и связанному пункту.
#
# Документ отправителя виден пункту приёма после приёма, документ получателя —
# пункту назначения после выдачи. Пустой результат проверяет обработчик.
#
# @param shipment ORM-запись отправления.
# @param documents Документы, сгруппированные по DocumentKind.
# @param is_origin Сотрудник относится к пункту приёма.
# @param is_destination Сотрудник относится к пункту назначения.
# @return Доступные реквизиты либо пустая модель Requisites.
def _visible_requisites(
    shipment: Shipment,
    documents: dict[DocumentKind, ShipmentDocument],
    *,
    is_origin: bool,
    is_destination: bool,
) -> Requisites:
    result = Requisites()
    if is_origin and DocumentKind.SENDER in documents and shipment.status != ShipmentStatus.CREATED:
        result.sender = recorded_document(documents[DocumentKind.SENDER])
    if (
        is_destination
        and DocumentKind.RECIPIENT in documents
        and shipment.status == ShipmentStatus.ISSUED
    ):
        result.recipient = recorded_document(documents[DocumentKind.RECIPIENT])
    return result


## @brief Возвращает рабочий список отправлений узла.
#
# Показывает находящиеся в узле или входящие отправления. Выданные исключены;
# поиск по трек-номеру точный после нормализации.
#
# @param user Текущий сотрудник.
# @param db Сессия SQLAlchemy текущего запроса.
# @param trackNumber Трек-номер для точного поиска.
# @param status Фильтр по состоянию либо None.
# @param direction ALL, AT_NODE или INCOMING относительно узла сотрудника.
# @param page Номер страницы, начиная с 1.
# @param size Максимальное число элементов страницы (1–100 в API).
# @return ShipmentPage с карточками списка и пагинацией.
# @exception errors.APIError 403 при неподходящей роли или отсутствии назначенного узла.
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
        db.execute(
            stmt.order_by(Shipment.created_at.desc(), Shipment.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
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


## @brief Оформляет отправление и присваивает трек-номер.
#
# Оператор активного пункта выбирает другой активный пункт назначения. Создание
# записи и события CREATE подтверждается совместно; коллизия номера повторяется
# до восьми попыток.
#
# @param payload Проверенная Pydantic-модель тела запроса.
# @param response HTTP-ответ для установки заголовков или cookie.
# @param user Текущий сотрудник.
# @param db Сессия SQLAlchemy текущего запроса.
# @return ShipmentCard в состоянии CREATED; HTTP 201 и Location.
# @exception errors.APIError 403 при недоступном пункте приёма; 400 при неверных
# справочниках; 409 при исчерпании попыток генерации номера.
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

    dest = _destination_node(db, payload.destinationNodeId, origin.id)
    stype = _shipment_type(db, payload.shipmentTypeId)
    shipment = _create_with_track_number(db, payload, origin, dest, stype)

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


## @brief Возвращает доступную сотруднику карточку.
#
# Разрешает оператора и сортировщика связанного узла; состав персональных данных определяется ролью.
#
# @param shipmentId Идентификатор отправления.
# @param user Текущий сотрудник.
# @param db Сессия SQLAlchemy текущего запроса.
# @return ShipmentCard.
# @exception errors.APIError 403 при отсутствии доступа; 404 при отсутствии отправления.
@router.get("/shipments/{shipmentId}", response_model=ShipmentCard)
def get_shipment(shipmentId: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    if user.role not in (Role.OPERATOR, Role.SORTING_EMPLOYEE) or user.node_id is None:
        raise forbidden()
    s = _load_shipment(db, shipmentId)
    if not _accessible(s, user.node_id):
        raise forbidden()
    return shipment_card(s, for_operator=(user.role == Role.OPERATOR))


## @brief Исправляет исходные данные до приёма.
#
# Только оператор пункта приёма может менять CREATED. При смене назначения адрес
# копируется из нового пункта.
#
# @param shipmentId Идентификатор отправления.
# @param payload Проверенная Pydantic-модель тела запроса.
# @param user Текущий сотрудник.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Обновлённая ShipmentCard.
# @exception errors.APIError 403 при отсутствии доступа; 404 при отсутствии;
# 409 после приёма; 400 при неверных справочниках.
@router.patch("/shipments/{shipmentId}", response_model=ShipmentCard)
def update_shipment(
    shipmentId: int,
    payload: ShipmentUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if user.role != Role.OPERATOR or user.node_id is None:
        raise forbidden()
    # Joined relationships include nullable outer joins; lock only the shipment row.
    s = db.execute(
        select(Shipment).where(Shipment.id == shipmentId).with_for_update(of=Shipment)
    ).scalar_one_or_none()
    if s is None:
        raise not_found()
    if s.origin_node_id != user.node_id:
        raise forbidden()
    if s.status != ShipmentStatus.CREATED:
        raise conflict("INVALID_TRANSITION", "Изменение невозможно: отправление уже принято")

    data = payload.model_dump(exclude_unset=True)

    if data.get("destinationNodeId") is not None:
        dest = _destination_node(db, data["destinationNodeId"], s.origin_node_id, editing=True)
        s.destination_node_id = dest.id
        s.delivery_address = dest.address

    if data.get("shipmentTypeId") is not None:
        st = _shipment_type(db, data["shipmentTypeId"], editing=True)
        s.shipment_type_id = st.id

    _apply_shipment_details(s, data)

    db.commit()
    db.refresh(s)
    return shipment_card(s, for_operator=True)


## @brief Возвращает служебную историю отправления.
#
# Проверяет доступ к карточке; сортирует события по времени и идентификатору,
# включает сведения об исполнителе.
#
# @param shipmentId Идентификатор отправления.
# @param user Текущий сотрудник.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Список ShipmentEvent из schemas.
# @exception errors.APIError 403 при отсутствии доступа; 404 при отсутствии отправления.
@router.get("/shipments/{shipmentId}/history", response_model=list[ShipmentEventSchema])
def get_shipment_history(
    shipmentId: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
):
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


## @brief Возвращает доступные оператору реквизиты.
#
# Пункт приёма видит документ отправителя после приёма; пункт назначения — документ
# получателя после выдачи. Устанавливает Cache-Control: no-store.
#
# @param shipmentId Идентификатор отправления.
# @param response HTTP-ответ для установки заголовков или cookie.
# @param user Текущий сотрудник.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Requisites с разрешёнными документами.
# @exception errors.APIError 403 при отсутствии прав или доступных документов;
# 404 при отсутствии отправления.
@router.get("/shipments/{shipmentId}/requisites", response_model=Requisites)
def get_requisites(
    shipmentId: int, response: Response, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
):
    if user.role != Role.OPERATOR or user.node_id is None:
        raise forbidden()
    s = _load_shipment(db, shipmentId)

    is_origin = s.origin_node_id == user.node_id
    is_destination = s.destination_node_id == user.node_id
    if not (is_origin or is_destination):
        raise forbidden()

    docs = {
        d.kind: d
        for d in db.execute(select(ShipmentDocument).where(ShipmentDocument.shipment_id == s.id))
        .scalars()
        .all()
    }

    result = _visible_requisites(s, docs, is_origin=is_origin, is_destination=is_destination)

    if result.sender is None and result.recipient is None:
        raise forbidden()

    response.headers["Cache-Control"] = "no-store"
    return result
