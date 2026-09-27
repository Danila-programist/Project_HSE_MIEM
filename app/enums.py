## @file
# @brief Роли, типы узлов, состояния и операции доставки.
#
# Строковые значения используются в API и PostgreSQL ENUM. Словари переводят состояния и операции на русский язык.
from enum import Enum


## @brief Служебная роль сотрудника.
#
# Каждой учётной записи назначается одна роль; клиентская роль не требует записи сотрудника.
class Role(str, Enum):
    ## @brief Оператор пункта обслуживания.
    OPERATOR = "OPERATOR"
    ## @brief Сотрудник сортировочного центра.
    SORTING_EMPLOYEE = "SORTING_EMPLOYEE"
    ## @brief Администратор.
    ADMIN = "ADMIN"


## @brief Тип узла доставки.
#
# Различает пункт обслуживания и сортировочный центр.
class NodeType(str, Enum):
    ## @brief Пункт обслуживания.
    SERVICE_POINT = "SERVICE_POINT"
    ## @brief Сортировочный центр.
    SORTING_CENTER = "SORTING_CENTER"


## @brief Состояние отправления.
#
# ISSUED является конечным состоянием. Допустимые переходы реализованы в роутере операций.
class ShipmentStatus(str, Enum):
    ## @brief Отправление оформлено.
    CREATED = "CREATED"
    ## @brief Отправление принято.
    ACCEPTED = "ACCEPTED"
    ## @brief Отправление отправлено из узла.
    DISPATCHED = "DISPATCHED"
    ## @brief Отправление прибыло в промежуточный узел.
    ARRIVED = "ARRIVED"
    ## @brief Отправление готово к выдаче.
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    ## @brief Отправление выдано; конечное состояние.
    ISSUED = "ISSUED"


## @brief Вид события доставки.
#
# Описывает действие, приведшее к сохранённому состоянию.
class Operation(str, Enum):
    ## @brief Оформление отправления.
    CREATE = "CREATE"
    ## @brief Фактический приём.
    ACCEPT = "ACCEPT"
    ## @brief Отправка в следующий узел.
    DISPATCH = "DISPATCH"
    ## @brief Регистрация прибытия.
    ARRIVE = "ARRIVE"
    ## @brief Выдача получателю.
    ISSUE = "ISSUE"


## @brief Принадлежность документа участнику.
#
# Разделяет реквизиты отправителя при приёме и получателя при выдаче.
class DocumentKind(str, Enum):
    ## @brief Документ отправителя.
    SENDER = "SENDER"
    ## @brief Документ получателя.
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