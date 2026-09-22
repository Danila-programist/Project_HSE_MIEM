from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_roles
from ..enums import Role, ShipmentStatus
from ..errors import conflict, not_found
from ..models import Employee, Node, Shipment
from ..schemas import Node as NodeSchema, NodeCreate, NodeUpdate
from .nodes import node_to_schema

router = APIRouter(tags=["Администрирование узлов"], dependencies=[Depends(require_roles(Role.ADMIN))])


@router.post("/admin/nodes", response_model=NodeSchema, status_code=201)
def create_node(payload: NodeCreate, response: Response, db: Annotated[Session, Depends(get_db)]):
    node = Node(name=payload.name, type=payload.type, address=payload.address, active=True)
    db.add(node)
    db.commit()
    db.refresh(node)
    response.headers["Location"] = f"/api/v1/admin/nodes/{node.id}"
    return node_to_schema(node)


@router.patch("/admin/nodes/{nodeId}", response_model=NodeSchema)
def update_node(nodeId: int, payload: NodeUpdate, db: Annotated[Session, Depends(get_db)]):
    node = db.get(Node, nodeId)
    if node is None:
        raise not_found()
    if not node.active:
        raise conflict("INVALID_TRANSITION", "Деактивированный узел не редактируется")

    data = payload.model_dump(exclude_unset=True)
    new_type = data.get("type", node.type)

    if "name" in data:
        node.name = data["name"]
    if "address" in data:
        node.address = data["address"]

    if new_type != node.type:
        node.type = new_type
        db.query(Employee).filter(Employee.node_id == node.id).update(
            {"node_id": None, "blocked": True}, synchronize_session=False
        )

    db.commit()
    db.refresh(node)
    return node_to_schema(node)


@router.post("/admin/nodes/{nodeId}/deactivate", response_model=NodeSchema)
def deactivate_node(nodeId: int, db: Annotated[Session, Depends(get_db)]):
    node = db.get(Node, nodeId)
    if node is None:
        raise not_found()
    if not node.active:
        return node_to_schema(node)

    active_count = db.scalar(
        select(func.count())
        .select_from(Shipment)
        .where(
            or_(
                and_(
                    Shipment.current_node_id == node.id,
                    Shipment.status != ShipmentStatus.ISSUED,
                ),
                and_(
                    Shipment.next_node_id == node.id,
                    Shipment.status == ShipmentStatus.DISPATCHED,
                ),
            )
        )
    )
    if active_count:
        raise conflict(
            "NODE_HAS_ACTIVE_SHIPMENTS",
            "В узле есть невыданные отправления или направленные в него отправления",
        )

    node.active = False
    db.commit()
    db.refresh(node)
    return node_to_schema(node)