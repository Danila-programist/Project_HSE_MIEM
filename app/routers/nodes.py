from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser
from ..enums import NodeType
from ..errors import not_found
from ..models import Node
from ..schemas import Node as NodeSchema, NodePage

router = APIRouter(tags=["Узлы"])


def node_to_schema(n: Node) -> NodeSchema:
    return NodeSchema(id=n.id, name=n.name, type=n.type, address=n.address, active=n.active)


@router.get("/nodes", response_model=NodePage)
def list_nodes(
    _: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    type: NodeType | None = None,
    active: bool | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    stmt = select(Node)
    if type is not None:
        stmt = stmt.where(Node.type == type)
    if active is not None:
        stmt = stmt.where(Node.active == active)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Node.id).offset((page - 1) * size).limit(size)).scalars().all()

    return NodePage(
        page=page,
        size=size,
        totalItems=total,
        totalPages=(total + size - 1) // size if size else 0,
        items=[node_to_schema(n) for n in rows],
    )


@router.get("/nodes/{nodeId}", response_model=NodeSchema)
def get_node(nodeId: int, _: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    node = db.get(Node, nodeId)
    if node is None:
        raise not_found()
    return node_to_schema(node)