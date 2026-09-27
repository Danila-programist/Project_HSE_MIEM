## @file
# @brief Модели хранения данных SQLAlchemy.
#
# Описывает таблицы, внешние ключи и ORM-связи. Схема создаётся миграцией alembic/versions/0001_initial.py.
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .enums import DocumentKind, NodeType, Operation, Role, ShipmentStatus

_node_type = PGEnum(NodeType, name="node_type", values_callable=lambda e: [x.value for x in e])
_role = PGEnum(Role, name="employee_role", values_callable=lambda e: [x.value for x in e])
_status = PGEnum(ShipmentStatus, name="shipment_status", values_callable=lambda e: [x.value for x in e])
_operation = PGEnum(Operation, name="shipment_operation", values_callable=lambda e: [x.value for x in e])
_doc_kind = PGEnum(DocumentKind, name="document_kind", values_callable=lambda e: [x.value for x in e])


## @brief Узел доставки.
#
# Хранит название, тип, адрес и признак активности. История сохраняется при деактивации.
class Node(Base):
    ## @brief Имя таблицы PostgreSQL.
    __tablename__ = "nodes"

    ## @brief Уникальный идентификатор записи.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ## @brief Отображаемое название.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ## @brief Тип узла доставки.
    type: Mapped[NodeType] = mapped_column(_node_type, nullable=False)
    ## @brief Адрес узла.
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    ## @brief Доступен ли узел для выбора в новых операциях.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


## @brief Учётная запись сотрудника.
#
# Хранит уникальный логин, хеш пароля, роль и необязательную связь с узлом. Блокировка проверяется на служебных запросах.
class Employee(Base):
    ## @brief Имя таблицы PostgreSQL.
    __tablename__ = "employees"

    ## @brief Уникальный идентификатор записи.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ## @brief Уникальный логин сотрудника.
    login: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    ## @brief Хеш пароля bcrypt.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ## @brief ФИО сотрудника.
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    ## @brief Служебная роль сотрудника.
    role: Mapped[Role] = mapped_column(_role, nullable=False)
    ## @brief Идентификатор связанного узла.
    node_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=True)
    ## @brief Признак блокировки учётной записи.
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    ## @brief Время создания записи с часовым поясом.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ## @brief Связанный узел.
    node: Mapped[Optional[Node]] = relationship("Node", lazy="joined")


## @brief Серверная сессия сотрудника.
#
# Связывает случайный токен cookie с сотрудником и временем истечения.
class UserSession(Base):
    ## @brief Имя таблицы PostgreSQL.
    __tablename__ = "sessions"

    ## @brief Случайный токен сессии, передаваемый в cookie.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ## @brief Идентификатор сотрудника.
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"), nullable=False)
    ## @brief Время создания записи с часовым поясом.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ## @brief Срок истечения сессии.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


## @brief Тип отправления в справочнике.
#
# Начальные значения создаются миграцией; используются при оформлении.
class ShipmentType(Base):
    ## @brief Имя таблицы PostgreSQL.
    __tablename__ = "shipment_types"

    ## @brief Уникальный идентификатор записи.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ## @brief Машинный код.
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    ## @brief Отображаемое название.
    name: Mapped[str] = mapped_column(String(200), nullable=False)


## @brief Тип удостоверяющего документа.
#
# Используется для реквизитов отправителя и получателя.
class DocumentType(Base):
    ## @brief Имя таблицы PostgreSQL.
    __tablename__ = "document_types"

    ## @brief Уникальный идентификатор записи.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ## @brief Машинный код.
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    ## @brief Отображаемое название.
    name: Mapped[str] = mapped_column(String(200), nullable=False)


## @brief Отправление и его текущее состояние.
#
# Хранит параметры, данные участников, четыре ссылки на узлы и даты. История и документы вынесены в отдельные таблицы.
class Shipment(Base):
    ## @brief Имя таблицы PostgreSQL.
    __tablename__ = "shipments"

    ## @brief Уникальный идентификатор записи.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ## @brief Уникальный трек-номер из 16 символов.
    track_number: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    ## @brief Текущее состояние отправления.
    status: Mapped[ShipmentStatus] = mapped_column(_status, nullable=False)
    ## @brief Идентификатор типа отправления.
    shipment_type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shipment_types.id"), nullable=False)
    ## @brief Идентификатор пункта приёма.
    origin_node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=False)
    ## @brief Идентификатор пункта назначения.
    destination_node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=False)
    ## @brief Идентификатор последнего зарегистрированного узла.
    current_node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=False)
    ## @brief Идентификатор следующего узла; None, если не назначен.
    next_node_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=True)
    ## @brief Адрес пункта назначения на момент оформления или исправления.
    delivery_address: Mapped[str] = mapped_column(String(500), nullable=False)

    ## @brief ФИО отправителя.
    sender_full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    ## @brief Телефон отправителя.
    sender_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    ## @brief ФИО получателя.
    recipient_full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    ## @brief Телефон получателя.
    recipient_phone: Mapped[str] = mapped_column(String(20), nullable=False)

    ## @brief Масса в килограммах.
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    ## @brief Длина в сантиметрах.
    length_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    ## @brief Ширина в сантиметрах.
    width_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    ## @brief Высота в сантиметрах.
    height_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    ## @brief Необязательное описание содержимого до 200 символов.
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    ## @brief Время создания записи с часовым поясом.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ## @brief Время приёма либо None до приёма.
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ## @brief Время выдачи либо None до выдачи.
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    ## @brief Связанный тип отправления.
    shipment_type: Mapped[ShipmentType] = relationship("ShipmentType", lazy="joined")
    ## @brief Пункт приёма.
    origin_node: Mapped[Node] = relationship("Node", foreign_keys=[origin_node_id], lazy="joined")
    ## @brief Пункт назначения.
    destination_node: Mapped[Node] = relationship("Node", foreign_keys=[destination_node_id], lazy="joined")
    ## @brief Последний зарегистрированный узел.
    current_node: Mapped[Node] = relationship("Node", foreign_keys=[current_node_id], lazy="joined")
    ## @brief Следующий узел либо None.
    next_node: Mapped[Optional[Node]] = relationship("Node", foreign_keys=[next_node_id], lazy="joined")


## @brief Событие истории доставки.
#
# Содержит операцию, итоговый статус, узлы, время и исполнителя.
class ShipmentEvent(Base):
    ## @brief Имя таблицы PostgreSQL.
    __tablename__ = "shipment_events"

    ## @brief Уникальный идентификатор записи.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ## @brief Идентификатор отправления.
    shipment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shipments.id"), nullable=False, index=True)
    ## @brief Выполненная операция доставки.
    operation: Mapped[Operation] = mapped_column(_operation, nullable=False)
    ## @brief Состояние после операции.
    resulting_status: Mapped[ShipmentStatus] = mapped_column(_status, nullable=False)
    ## @brief Идентификатор связанного узла.
    node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=False)
    ## @brief Идентификатор следующего узла; None, если не назначен.
    next_node_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=True)
    ## @brief Идентификатор сотрудника.
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"), nullable=False)
    ## @brief Время события с часовым поясом.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ## @brief Связанный узел.
    node: Mapped[Node] = relationship("Node", foreign_keys=[node_id], lazy="joined")
    ## @brief Следующий узел либо None.
    next_node: Mapped[Optional[Node]] = relationship("Node", foreign_keys=[next_node_id], lazy="joined")
    ## @brief Исполнитель операции.
    employee: Mapped[Employee] = relationship("Employee", lazy="joined")


## @brief Документ участника, зафиксированный при операции.
#
# Пара shipment_id и kind уникальна: у отправления не более одного документа каждого вида.
class ShipmentDocument(Base):
    ## @brief Имя таблицы PostgreSQL.
    __tablename__ = "shipment_documents"
    ## @brief Дополнительные ограничения таблицы.
    __table_args__ = (UniqueConstraint("shipment_id", "kind", name="uq_shipment_doc_kind"),)

    ## @brief Уникальный идентификатор записи.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ## @brief Идентификатор отправления.
    shipment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shipments.id"), nullable=False)
    ## @brief Документ отправителя или получателя.
    kind: Mapped[DocumentKind] = mapped_column(_doc_kind, nullable=False)
    ## @brief Идентификатор типа документа.
    document_type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("document_types.id"), nullable=False)
    ## @brief Серия документа при наличии.
    series: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ## @brief Номер документа.
    number: Mapped[str] = mapped_column(String(30), nullable=False)
    ## @brief Время записи реквизитов.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ## @brief Идентификатор записавшего сотрудника.
    recorded_by_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"), nullable=False)

    ## @brief Тип документа из справочника.
    document_type: Mapped[DocumentType] = relationship("DocumentType", lazy="joined")
    ## @brief Сотрудник, записавший реквизиты.
    recorded_by: Mapped[Employee] = relationship("Employee", lazy="joined")