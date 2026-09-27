## @file
# @brief Преобразование ORM-записей в модели ответа.
#
# Формирует карточки, историю и публичное отслеживание; ограничивает передачу данных участников сортировщикам и клиентам.
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


## @brief Формирует краткую ссылку на узел.
#
# Переносит идентификатор, название и тип без адреса и признака активности.
#
# @param node ORM-запись узла.
# @return Модель NodeRef.
def node_ref(node: Node) -> NodeRef:
    return NodeRef(id=node.id, name=node.name, type=node.type)


## @brief Формирует элемент справочника.
#
# Читает атрибуты id, code и name ORM-объекта.
#
# @param obj Запись справочника с id, code и name.
# @return Модель DictionaryItem.
def dict_item(obj) -> DictionaryItem:
    return DictionaryItem(id=obj.id, code=obj.code, name=obj.name)


## @brief Собирает общую часть карточки отправления.
#
# Добавляет узлы, параметры и даты без ФИО и телефонов участников; Decimal преобразует в float.
#
# @param shipment ORM-запись отправления.
# @return Словарь полей карточки.
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


## @brief Формирует карточку с учётом роли читателя.
#
# Для оператора включает отправителя и получателя, для остальных оставляет эти поля равными None.
#
# @param shipment ORM-запись отправления.
# @param for_operator Включать ли ФИО и телефоны участников.
# @return Модель ShipmentCard.
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


## @brief Формирует строку рабочего списка.
#
# Включает статус, узлы и время создания без персональных данных.
#
# @param shipment ORM-запись отправления.
# @return Модель ShipmentListItem.
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


## @brief Формирует служебное представление события.
#
# Добавляет русские названия операции и статуса, связанные узлы и сотрудника.
#
# @param event ORM-запись события доставки.
# @return Модель ShipmentEvent из schemas.
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


## @brief Формирует реквизиты записанного документа.
#
# Включает тип, серию, номер, время и имя записавшего сотрудника. Проверка прав выполняется вызывающим обработчиком.
#
# @param doc ORM-запись документа участника.
# @return Модель RecordedDocument.
def recorded_document(doc: ShipmentDocument) -> RecordedDocument:
    return RecordedDocument(
        documentType=dict_item(doc.document_type),
        series=doc.series,
        number=doc.number,
        recordedAt=doc.recorded_at,
        recordedBy=doc.recorded_by.full_name,
    )


## @brief Формирует публичный результат отслеживания.
#
# Исключает сведения об участниках и сотрудниках. Порядок переданных событий сохраняется.
#
# @param shipment ORM-запись отправления.
# @param events События в требуемом порядке вывода.
# @return Модель PublicTracking.
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


## @brief Собирает административные сведения о сотруднике.
#
# Включает роль, узел и блокировку, но не хеш пароля.
#
# @param emp ORM-запись сотрудника.
# @return Словарь полей модели User.
def employee_to_user_payload(emp: Employee) -> dict:
    return dict(
        id=emp.id,
        login=emp.login,
        fullName=emp.full_name,
        role=emp.role,
        node=node_ref(emp.node) if emp.node else None,
        blocked=emp.blocked,
    )