## @file
# @brief Контракты запросов и ответов API на Pydantic.
#
# Входные модели проверяют обязательные поля и ограничения. Ответы используют camelCase; модели Page задают пагинацию.
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import NodeType, Operation, Role, ShipmentStatus

PHONE_PATTERN = r"^\+?[0-9\s\-()]{10,20}$"
TRACK_PATTERN = r"^[A-Z0-9]{16}$"


## @brief Краткая ссылка на узел.
#
# Используется внутри карточек и профилей; содержит только id, name и type.
class NodeRef(BaseModel):
    ## @brief Настройки чтения и проверки модели Pydantic.
    model_config = ConfigDict(from_attributes=True)
    ## @brief Уникальный идентификатор записи.
    id: int
    ## @brief Отображаемое название.
    name: str
    ## @brief Тип узла доставки.
    type: NodeType


## @brief Элемент справочника API.
#
# Передаёт стабильный код и отображаемое название вместе с идентификатором.
class DictionaryItem(BaseModel):
    ## @brief Настройки чтения и проверки модели Pydantic.
    model_config = ConfigDict(from_attributes=True)
    ## @brief Уникальный идентификатор записи.
    id: int
    ## @brief Машинный код.
    code: str
    ## @brief Отображаемое название.
    name: str


## @brief Общие метаданные страницы результатов.
#
# Базовая модель для UserPage, NodePage и ShipmentPage; нумерация страниц начинается с 1.
class Page(BaseModel):
    ## @brief Номер страницы, начиная с 1.
    page: int
    ## @brief Запрошенный размер страницы.
    size: int
    ## @brief Число записей, подходящих под фильтры.
    totalItems: int
    ## @brief Общее число страниц; 0 для пустой выборки.
    totalPages: int


## @brief Ошибка отдельного поля.
#
# Содержит путь к полю и пояснение причины ошибки.
class FieldError(BaseModel):
    ## @brief Путь к ошибочному полю.
    field: str
    ## @brief Сообщение для пользователя.
    message: str


## @brief Учётные данные для входа.
#
# Пароль передаётся для проверки, а не для сохранения в открытом виде.
class LoginRequest(BaseModel):
    ## @brief Уникальный логин сотрудника.
    login: str = Field(min_length=1, max_length=50)
    ## @brief Пароль, передаваемый для проверки или хеширования.
    password: str = Field(min_length=1, max_length=128)


## @brief Профиль авторизованного сотрудника.
#
# Ответ при входе и запросе текущего пользователя; хеш пароля не возвращается.
class UserProfile(BaseModel):
    ## @brief Уникальный идентификатор записи.
    id: int
    ## @brief Уникальный логин сотрудника.
    login: str
    ## @brief ФИО.
    fullName: str
    ## @brief Служебная роль сотрудника.
    role: Role
    ## @brief Связанный узел.
    node: Optional[NodeRef] = None


## @brief Административная карточка сотрудника.
#
# Дополняет сведения о сотруднике признаком блокировки.
class User(BaseModel):
    ## @brief Уникальный идентификатор записи.
    id: int
    ## @brief Уникальный логин сотрудника.
    login: str
    ## @brief ФИО.
    fullName: str
    ## @brief Служебная роль сотрудника.
    role: Role
    ## @brief Связанный узел.
    node: Optional[NodeRef] = None
    ## @brief Признак блокировки учётной записи.
    blocked: bool


## @brief Данные нового сотрудника.
#
# Проверяет формат логина и длину пароля; совместимость роли и узла проверяется обработчиком.
class UserCreate(BaseModel):
    ## @brief Уникальный логин сотрудника.
    login: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._\-]+$")
    ## @brief ФИО.
    fullName: str = Field(min_length=1, max_length=200)
    ## @brief Служебная роль сотрудника.
    role: Role
    ## @brief Идентификатор назначаемого узла или None.
    nodeId: Optional[int] = None
    ## @brief Пароль, передаваемый для проверки или хеширования.
    password: str = Field(min_length=8, max_length=128)


## @brief Частичное изменение сотрудника.
#
# Неизвестные поля запрещены; наличие полей определяется через exclude_unset.
class UserUpdate(BaseModel):
    ## @brief Настройки чтения и проверки модели Pydantic.
    model_config = ConfigDict(extra="forbid")
    ## @brief Уникальный логин сотрудника.
    login: Optional[str] = Field(default=None, min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._\-]+$")
    ## @brief ФИО.
    fullName: Optional[str] = Field(default=None, min_length=1, max_length=200)
    ## @brief Служебная роль сотрудника.
    role: Optional[Role] = None
    ## @brief Идентификатор назначаемого узла или None.
    nodeId: Optional[int] = None


## @brief Запрос установки нового пароля.
#
# Ограничивает длину пароля диапазоном от 8 до 128 символов.
class PasswordSet(BaseModel):
    ## @brief Новый пароль длиной 8–128 символов.
    newPassword: str = Field(min_length=8, max_length=128)


## @brief Страница сотрудников.
#
# Наследует schemas.Page: page, size, totalItems и totalPages. Добавляет items со списком User.
class UserPage(Page):
    ## @brief Элементы текущей страницы.
    items: list[User]


## @brief Полная карточка узла API.
#
# Передаёт имя, тип, адрес и активность; отделена от ORM-модели хранения.
class Node(BaseModel):
    ## @brief Настройки чтения и проверки модели Pydantic.
    model_config = ConfigDict(from_attributes=True)
    ## @brief Уникальный идентификатор записи.
    id: int
    ## @brief Отображаемое название.
    name: str
    ## @brief Тип узла доставки.
    type: NodeType
    ## @brief Адрес узла.
    address: str
    ## @brief Доступен ли узел для выбора в новых операциях.
    active: bool


## @brief Данные для создания узла.
#
# Название, тип и адрес обязательны; активность назначает обработчик.
class NodeCreate(BaseModel):
    ## @brief Отображаемое название.
    name: str = Field(min_length=1, max_length=200)
    ## @brief Тип узла доставки.
    type: NodeType
    ## @brief Адрес узла.
    address: str = Field(min_length=1, max_length=500)


## @brief Частичное изменение узла.
#
# Неизвестные поля запрещены; обработчик проверяет допустимость изменения.
class NodeUpdate(BaseModel):
    ## @brief Настройки чтения и проверки модели Pydantic.
    model_config = ConfigDict(extra="forbid")
    ## @brief Отображаемое название.
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    ## @brief Тип узла доставки.
    type: Optional[NodeType] = None
    ## @brief Адрес узла.
    address: Optional[str] = Field(default=None, min_length=1, max_length=500)


## @brief Страница узлов доставки.
#
# Наследует метаданные schemas.Page и добавляет список Node.
class NodePage(Page):
    ## @brief Элементы текущей страницы.
    items: list[Node]


## @brief Контактные данные участника отправления.
#
# Проверяет непустое ФИО и формат телефона; не создаёт учётную запись.
class Participant(BaseModel):
    ## @brief ФИО.
    fullName: str = Field(min_length=1, max_length=200)
    ## @brief Телефон в допустимом формате.
    phone: str = Field(pattern=PHONE_PATTERN)


## @brief Вводимые реквизиты документа.
#
# Тип и номер обязательны; серия необязательна. Наличие типа проверяет обработчик.
class ParticipantDocument(BaseModel):
    ## @brief Идентификатор типа документа.
    documentTypeId: int
    ## @brief Серия документа при наличии.
    series: Optional[str] = Field(default=None, max_length=20)
    ## @brief Номер документа.
    number: str = Field(min_length=1, max_length=30)


## @brief Запрос оформления отправления.
#
# Содержит участников, назначение, тип, положительные массу и габариты; пункт приёма определяется по оператору.
class ShipmentCreate(BaseModel):
    ## @brief Сведения об отправителе.
    sender: Participant
    ## @brief Сведения о получателе.
    recipient: Participant
    ## @brief Идентификатор пункта назначения.
    destinationNodeId: int
    ## @brief Идентификатор типа отправления.
    shipmentTypeId: int
    ## @brief Масса в килограммах.
    weightKg: float = Field(gt=0, le=1000)
    ## @brief Длина в сантиметрах.
    lengthCm: float = Field(gt=0, le=1000)
    ## @brief Ширина в сантиметрах.
    widthCm: float = Field(gt=0, le=1000)
    ## @brief Высота в сантиметрах.
    heightCm: float = Field(gt=0, le=1000)
    ## @brief Необязательное описание содержимого до 200 символов.
    description: Optional[str] = Field(default=None, max_length=200)


## @brief Частичное исправление отправления.
#
# Допускается только до приёма; отсутствующие поля не изменяются, description можно очистить значением None.
class ShipmentUpdate(BaseModel):
    ## @brief Настройки чтения и проверки модели Pydantic.
    model_config = ConfigDict(extra="forbid")
    ## @brief Сведения об отправителе.
    sender: Optional[Participant] = None
    ## @brief Сведения о получателе.
    recipient: Optional[Participant] = None
    ## @brief Идентификатор пункта назначения.
    destinationNodeId: Optional[int] = None
    ## @brief Идентификатор типа отправления.
    shipmentTypeId: Optional[int] = None
    ## @brief Масса в килограммах.
    weightKg: Optional[float] = Field(default=None, gt=0, le=1000)
    ## @brief Длина в сантиметрах.
    lengthCm: Optional[float] = Field(default=None, gt=0, le=1000)
    ## @brief Ширина в сантиметрах.
    widthCm: Optional[float] = Field(default=None, gt=0, le=1000)
    ## @brief Высота в сантиметрах.
    heightCm: Optional[float] = Field(default=None, gt=0, le=1000)
    ## @brief Необязательное описание содержимого до 200 символов.
    description: Optional[str] = Field(default=None, max_length=200)


## @brief Подробная карточка отправления.
#
# Включает параметры, узлы и даты. Поля sender и recipient заполняются только для оператора.
class ShipmentCard(BaseModel):
    ## @brief Уникальный идентификатор записи.
    id: int
    ## @brief Трек-номер отправления.
    trackNumber: str
    ## @brief Текущее состояние отправления.
    status: ShipmentStatus
    ## @brief Русское название текущего состояния.
    statusName: str
    ## @brief Пункт приёма.
    originNode: NodeRef
    ## @brief Пункт назначения.
    destinationNode: NodeRef
    ## @brief Последний зарегистрированный узел.
    currentNode: NodeRef
    ## @brief Следующий узел либо None.
    nextNode: Optional[NodeRef] = None
    ## @brief Адрес доставки в пункт обслуживания.
    deliveryAddress: str
    ## @brief Тип отправления.
    shipmentType: DictionaryItem
    ## @brief Масса в килограммах.
    weightKg: float
    ## @brief Длина в сантиметрах.
    lengthCm: float
    ## @brief Ширина в сантиметрах.
    widthCm: float
    ## @brief Высота в сантиметрах.
    heightCm: float
    ## @brief Необязательное описание содержимого до 200 символов.
    description: Optional[str] = None
    ## @brief Время создания.
    createdAt: datetime
    ## @brief Время фактического приёма или None.
    acceptedAt: Optional[datetime] = None
    ## @brief Время фактической выдачи или None.
    issuedAt: Optional[datetime] = None
    ## @brief Сведения об отправителе.
    sender: Optional[Participant] = None
    ## @brief Сведения о получателе.
    recipient: Optional[Participant] = None


## @brief Элемент рабочего списка отправлений.
#
# Краткое представление без ФИО, телефонов и реквизитов документов.
class ShipmentListItem(BaseModel):
    ## @brief Уникальный идентификатор записи.
    id: int
    ## @brief Трек-номер отправления.
    trackNumber: str
    ## @brief Текущее состояние отправления.
    status: ShipmentStatus
    ## @brief Русское название текущего состояния.
    statusName: str
    ## @brief Пункт приёма.
    originNode: NodeRef
    ## @brief Пункт назначения.
    destinationNode: NodeRef
    ## @brief Последний зарегистрированный узел.
    currentNode: NodeRef
    ## @brief Следующий узел либо None.
    nextNode: Optional[NodeRef] = None
    ## @brief Время создания.
    createdAt: datetime


## @brief Страница отправлений.
#
# Наследует schemas.Page и добавляет список ShipmentListItem.
class ShipmentPage(Page):
    ## @brief Элементы текущей страницы.
    items: list[ShipmentListItem]


## @brief Исполнитель события.
#
# Краткое представление сотрудника в служебной истории.
class ShipmentEventEmployee(BaseModel):
    ## @brief Уникальный идентификатор записи.
    id: int
    ## @brief ФИО.
    fullName: str


## @brief Событие истории доставки.
#
# Содержит операцию, итоговый статус, узлы, время и исполнителя.
class ShipmentEvent(BaseModel):
    ## @brief Уникальный идентификатор записи.
    id: int
    ## @brief Выполненная операция доставки.
    operation: Operation
    ## @brief Русское название операции.
    operationName: str
    ## @brief Состояние после операции.
    resultingStatus: ShipmentStatus
    ## @brief Русское название итогового состояния.
    resultingStatusName: str
    ## @brief Связанный узел.
    node: NodeRef
    ## @brief Следующий узел либо None.
    nextNode: Optional[NodeRef] = None
    ## @brief Время события.
    occurredAt: datetime
    ## @brief Исполнитель операции.
    employee: ShipmentEventEmployee


## @brief Сохранённые реквизиты документа.
#
# Включает сведения о документе и о том, кто и когда их записал.
class RecordedDocument(BaseModel):
    ## @brief Тип документа.
    documentType: DictionaryItem
    ## @brief Серия документа при наличии.
    series: Optional[str] = None
    ## @brief Номер документа.
    number: str
    ## @brief Время фиксации реквизитов.
    recordedAt: datetime
    ## @brief ФИО записавшего сотрудника.
    recordedBy: str


## @brief Доступные оператору документы участников.
#
# Недоступный документ представлен None; права проверяются обработчиком.
class Requisites(BaseModel):
    ## @brief Разрешённые реквизиты документа участника либо None.
    sender: Optional[RecordedDocument] = None
    ## @brief Разрешённые реквизиты документа участника либо None.
    recipient: Optional[RecordedDocument] = None


## @brief Запрос приёма отправления.
#
# Содержит документ отправителя, который сохраняется вместе с операцией.
class AcceptRequest(BaseModel):
    ## @brief Реквизиты документа отправителя.
    senderDocument: ParticipantDocument


## @brief Запрос отправки в следующий узел.
#
# Передаёт выбранный сотрудником узел; допустимость проверяет обработчик.
class DispatchRequest(BaseModel):
    ## @brief Идентификатор выбранного следующего узла.
    nextNodeId: int


## @brief Запрос выдачи отправления.
#
# Содержит документ получателя для фиксации выдачи.
class IssueRequest(BaseModel):
    ## @brief Реквизиты документа получателя.
    recipientDocument: ParticipantDocument


## @brief Событие публичного отслеживания.
#
# Не содержит идентификатора или имени сотрудника.
class PublicEvent(BaseModel):
    ## @brief Время события.
    occurredAt: datetime
    ## @brief Русское название текущего состояния.
    statusName: str
    ## @brief Название узла события.
    nodeName: str
    ## @brief Название следующего узла или None.
    nextNodeName: Optional[str] = None


## @brief Публичный результат поиска по трек-номеру.
#
# Содержит статус, названия узлов и историю без персональных данных.
class PublicTracking(BaseModel):
    ## @brief Трек-номер отправления.
    trackNumber: str
    ## @brief Текущее состояние отправления.
    status: ShipmentStatus
    ## @brief Русское название текущего состояния.
    statusName: str
    ## @brief Название последнего зарегистрированного узла.
    currentNodeName: str
    ## @brief Название следующего узла или None.
    nextNodeName: Optional[str] = None
    ## @brief Хронологический список публичных событий.
    events: list[PublicEvent]