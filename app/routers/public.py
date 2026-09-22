from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import not_found
from ..models import Shipment, ShipmentEvent
from ..schemas import PublicTracking
from ..serializers import public_tracking
from ..utils import normalize_track_number

router = APIRouter(tags=["Публичное отслеживание"])


@router.get("/public/tracking/{trackNumber}", response_model=PublicTracking)
def track_shipment(trackNumber: str, db: Annotated[Session, Depends(get_db)]):
    tn = normalize_track_number(trackNumber)
    s = db.execute(select(Shipment).where(Shipment.track_number == tn)).scalar_one_or_none()
    if s is None:
        raise not_found("Отправление не найдено")

    events = (
        db.execute(
            select(ShipmentEvent)
            .where(ShipmentEvent.shipment_id == s.id)
            .order_by(ShipmentEvent.occurred_at.asc(), ShipmentEvent.id.asc())
        )
        .scalars()
        .all()
    )
    return public_tracking(s, events)