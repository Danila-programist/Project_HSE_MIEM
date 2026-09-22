from enum import Enum


class Role(str, Enum):
    OPERATOR = "OPERATOR"
    SORTING_EMPLOYEE = "SORTING_EMPLOYEE"
    ADMIN = "ADMIN"


class NodeType(str, Enum):
    SERVICE_POINT = "SERVICE_POINT"
    SORTING_CENTER = "SORTING_CENTER"


class ShipmentStatus(str, Enum):
    CREATED = "CREATED"
    ACCEPTED = "ACCEPTED"
    DISPATCHED = "DISPATCHED"
    ARRIVED = "ARRIVED"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    ISSUED = "ISSUED"


class Operation(str, Enum):
    CREATE = "CREATE"
    ACCEPT = "ACCEPT"
    DISPATCH = "DISPATCH"
    ARRIVE = "ARRIVE"
    ISSUE = "ISSUE"


class DocumentKind(str, Enum):
    SENDER = "SENDER"
    RECIPIENT = "RECIPIENT"


STATUS_NAMES: dict[ShipmentStatus, str] = {
    ShipmentStatus.CREATED: "Оформлено",
    ShipmentStatus.ACCEPTED: "Принято",
    ShipmentStatus.DISPATCHED: "Отправлено из узла",
    ShipmentStatus.ARRIVED: "Прибыло в узел",
    ShipmentStatus.READY_FOR_PICKUP: "Готово к выдаче",
    ShipmentStatus.ISSUED: "Выдано",
}

OPERATION_NAMES: dict[Operation, str] = {
    Operation.CREATE: "Оформление",
    Operation.ACCEPT: "Приём",
    Operation.DISPATCH: "Отправка",
    Operation.ARRIVE: "Прибытие",
    Operation.ISSUE: "Выдача",
}