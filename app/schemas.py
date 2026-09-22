from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import NodeType, Operation, Role, ShipmentStatus

PHONE_PATTERN = r"^\+?[0-9\s\-()]{10,20}$"
TRACK_PATTERN = r"^[A-Z0-9]{16}$"


class NodeRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: NodeType


class DictionaryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


class Page(BaseModel):
    page: int
    size: int
    totalItems: int
    totalPages: int


class FieldError(BaseModel):
    field: str
    message: str


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class UserProfile(BaseModel):
    id: int
    login: str
    fullName: str
    role: Role
    node: Optional[NodeRef] = None


class User(BaseModel):
    id: int
    login: str
    fullName: str
    role: Role
    node: Optional[NodeRef] = None
    blocked: bool


class UserCreate(BaseModel):
    login: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._\-]+$")
    fullName: str = Field(min_length=1, max_length=200)
    role: Role
    nodeId: Optional[int] = None
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: Optional[str] = Field(default=None, min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._\-]+$")
    fullName: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[Role] = None
    nodeId: Optional[int] = None


class PasswordSet(BaseModel):
    newPassword: str = Field(min_length=8, max_length=128)


class UserPage(Page):
    items: list[User]


class Node(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: NodeType
    address: str
    active: bool


class NodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: NodeType
    address: str = Field(min_length=1, max_length=500)


class NodeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    type: Optional[NodeType] = None
    address: Optional[str] = Field(default=None, min_length=1, max_length=500)


class NodePage(Page):
    items: list[Node]


class Participant(BaseModel):
    fullName: str = Field(min_length=1, max_length=200)
    phone: str = Field(pattern=PHONE_PATTERN)


class ParticipantDocument(BaseModel):
    documentTypeId: int
    series: Optional[str] = Field(default=None, max_length=20)
    number: str = Field(min_length=1, max_length=30)


class ShipmentCreate(BaseModel):
    sender: Participant
    recipient: Participant
    destinationNodeId: int
    shipmentTypeId: int
    weightKg: float = Field(gt=0, le=1000)
    lengthCm: float = Field(gt=0, le=1000)
    widthCm: float = Field(gt=0, le=1000)
    heightCm: float = Field(gt=0, le=1000)
    description: Optional[str] = Field(default=None, max_length=200)


class ShipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender: Optional[Participant] = None
    recipient: Optional[Participant] = None
    destinationNodeId: Optional[int] = None
    shipmentTypeId: Optional[int] = None
    weightKg: Optional[float] = Field(default=None, gt=0, le=1000)
    lengthCm: Optional[float] = Field(default=None, gt=0, le=1000)
    widthCm: Optional[float] = Field(default=None, gt=0, le=1000)
    heightCm: Optional[float] = Field(default=None, gt=0, le=1000)
    description: Optional[str] = Field(default=None, max_length=200)


class ShipmentCard(BaseModel):
    id: int
    trackNumber: str
    status: ShipmentStatus
    statusName: str
    originNode: NodeRef
    destinationNode: NodeRef
    currentNode: NodeRef
    nextNode: Optional[NodeRef] = None
    deliveryAddress: str
    shipmentType: DictionaryItem
    weightKg: float
    lengthCm: float
    widthCm: float
    heightCm: float
    description: Optional[str] = None
    createdAt: datetime
    acceptedAt: Optional[datetime] = None
    issuedAt: Optional[datetime] = None
    sender: Optional[Participant] = None
    recipient: Optional[Participant] = None


class ShipmentListItem(BaseModel):
    id: int
    trackNumber: str
    status: ShipmentStatus
    statusName: str
    originNode: NodeRef
    destinationNode: NodeRef
    currentNode: NodeRef
    nextNode: Optional[NodeRef] = None
    createdAt: datetime


class ShipmentPage(Page):
    items: list[ShipmentListItem]


class ShipmentEventEmployee(BaseModel):
    id: int
    fullName: str


class ShipmentEvent(BaseModel):
    id: int
    operation: Operation
    operationName: str
    resultingStatus: ShipmentStatus
    resultingStatusName: str
    node: NodeRef
    nextNode: Optional[NodeRef] = None
    occurredAt: datetime
    employee: ShipmentEventEmployee


class RecordedDocument(BaseModel):
    documentType: DictionaryItem
    series: Optional[str] = None
    number: str
    recordedAt: datetime
    recordedBy: str


class Requisites(BaseModel):
    sender: Optional[RecordedDocument] = None
    recipient: Optional[RecordedDocument] = None


class AcceptRequest(BaseModel):
    senderDocument: ParticipantDocument


class DispatchRequest(BaseModel):
    nextNodeId: int


class IssueRequest(BaseModel):
    recipientDocument: ParticipantDocument


class PublicEvent(BaseModel):
    occurredAt: datetime
    statusName: str
    nodeName: str
    nextNodeName: Optional[str] = None


class PublicTracking(BaseModel):
    trackNumber: str
    status: ShipmentStatus
    statusName: str
    currentNodeName: str
    nextNodeName: Optional[str] = None
    events: list[PublicEvent]