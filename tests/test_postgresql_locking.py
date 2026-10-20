"""Row-lock regression; run with TEST_DATABASE_URL pointing to PostgreSQL."""

from uuid import uuid4

import pytest
from psycopg.errors import LockNotAvailable
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.enums import NodeType, ShipmentStatus
from app.models import Node, Shipment, ShipmentType
from app.routers.operations import _lock


@pytest.fixture()
def committed_shipment(postgres_engine):
    if postgres_engine is None:
        pytest.skip("Set TEST_DATABASE_URL to check PostgreSQL row locks")

    # These rows must be committed so a second connection can see them.
    with Session(postgres_engine, expire_on_commit=False) as db:
        origin = Node(name="Lock origin", type=NodeType.SERVICE_POINT, address="Origin")
        destination = Node(
            name="Lock destination", type=NodeType.SERVICE_POINT, address="Destination"
        )
        shipment_type = ShipmentType(code=uuid4().hex, name="Lock parcel")
        db.add_all([origin, destination, shipment_type])
        db.flush()
        shipment = Shipment(
            track_number=uuid4().hex[:16].upper(),
            status=ShipmentStatus.CREATED,
            shipment_type_id=shipment_type.id,
            origin_node_id=origin.id,
            destination_node_id=destination.id,
            current_node_id=origin.id,
            next_node_id=None,
            delivery_address=destination.address,
            sender_full_name="Sender",
            sender_phone="+79991234567",
            recipient_full_name="Recipient",
            recipient_phone="+79997654321",
            weight_kg=1,
            length_cm=10,
            width_cm=10,
            height_cm=10,
        )
        db.add(shipment)
        db.commit()

    try:
        yield shipment
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(delete(Shipment).where(Shipment.id == shipment.id))
            connection.execute(delete(ShipmentType).where(ShipmentType.id == shipment_type.id))
            connection.execute(delete(Node).where(Node.id.in_([origin.id, destination.id])))


def test_lock_blocks_other_shipment_writers_but_not_related_nodes(
    postgres_engine, committed_shipment
):
    shipment_id = committed_shipment.id
    with Session(postgres_engine) as owner, Session(postgres_engine) as contender:
        shipment = _lock(owner, shipment_id)
        assert shipment.next_node is None
        assert shipment.origin_node.id == committed_shipment.origin_node_id

        # Other shipments sharing a node must remain independently editable.
        contender.execute(select(Node.id).with_for_update(nowait=True)).all()
        contender.execute(select(ShipmentType.id).with_for_update(nowait=True)).all()
        contender.rollback()

        competing_lock = (
            select(Shipment.id)
            .where(Shipment.id == shipment_id)
            .with_for_update(nowait=True)
        )
        with pytest.raises(OperationalError) as error:
            contender.execute(competing_lock)
        assert isinstance(error.value.orig, LockNotAvailable)
        contender.rollback()

        owner.commit()
        assert contender.execute(competing_lock).scalar_one() == shipment_id
