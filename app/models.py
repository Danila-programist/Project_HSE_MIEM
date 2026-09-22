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


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[NodeType] = mapped_column(_node_type, nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    login: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[Role] = mapped_column(_role, nullable=False)
    node_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    node: Mapped[Optional[Node]] = relationship("Node", lazy="joined")


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShipmentType(Base):
    __tablename__ = "shipment_types"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class DocumentType(Base):
    __tablename__ = "document_types"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    track_number: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    status: Mapped[ShipmentStatus] = mapped_column(_status, nullable=False)
    shipment_type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shipment_types.id"), nullable=False)
    origin_node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=False)
    destination_node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=False)
    current_node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=False)
    next_node_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=True)
    delivery_address: Mapped[str] = mapped_column(String(500), nullable=False)

    sender_full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sender_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient_full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_phone: Mapped[str] = mapped_column(String(20), nullable=False)

    weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    length_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    width_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    height_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    shipment_type: Mapped[ShipmentType] = relationship("ShipmentType", lazy="joined")
    origin_node: Mapped[Node] = relationship("Node", foreign_keys=[origin_node_id], lazy="joined")
    destination_node: Mapped[Node] = relationship("Node", foreign_keys=[destination_node_id], lazy="joined")
    current_node: Mapped[Node] = relationship("Node", foreign_keys=[current_node_id], lazy="joined")
    next_node: Mapped[Optional[Node]] = relationship("Node", foreign_keys=[next_node_id], lazy="joined")


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shipments.id"), nullable=False, index=True)
    operation: Mapped[Operation] = mapped_column(_operation, nullable=False)
    resulting_status: Mapped[ShipmentStatus] = mapped_column(_status, nullable=False)
    node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=False)
    next_node_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("nodes.id"), nullable=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    node: Mapped[Node] = relationship("Node", foreign_keys=[node_id], lazy="joined")
    next_node: Mapped[Optional[Node]] = relationship("Node", foreign_keys=[next_node_id], lazy="joined")
    employee: Mapped[Employee] = relationship("Employee", lazy="joined")


class ShipmentDocument(Base):
    __tablename__ = "shipment_documents"
    __table_args__ = (UniqueConstraint("shipment_id", "kind", name="uq_shipment_doc_kind"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shipments.id"), nullable=False)
    kind: Mapped[DocumentKind] = mapped_column(_doc_kind, nullable=False)
    document_type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("document_types.id"), nullable=False)
    series: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    number: Mapped[str] = mapped_column(String(30), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    recorded_by_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"), nullable=False)

    document_type: Mapped[DocumentType] = relationship("DocumentType", lazy="joined")
    recorded_by: Mapped[Employee] = relationship("Employee", lazy="joined")