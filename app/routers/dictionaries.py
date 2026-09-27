## @file
# @brief Справочники типов узлов, отправлений и документов.
#
# Справочники доступны авторизованным сотрудникам; типы документов — только операторам.
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser
from ..enums import NodeType, Role
from ..errors import forbidden
from ..models import DocumentType, ShipmentType
from ..schemas import DictionaryItem

router = APIRouter(tags=["Справочники"])


## @brief Возвращает типы узлов.
#
# Справочник формируется из фиксированных значений SERVICE_POINT и SORTING_CENTER.
#
# @param _ Авторизованный сотрудник; значение непосредственно не используется.
# @return Список DictionaryItem.
@router.get("/dictionaries/node-types", response_model=list[DictionaryItem])
def list_node_types(_: CurrentUser):
    return [
        DictionaryItem(id=1, code=NodeType.SERVICE_POINT.value, name="Пункт обслуживания"),
        DictionaryItem(id=2, code=NodeType.SORTING_CENTER.value, name="Сортировочный центр"),
    ]


## @brief Возвращает типы отправлений.
#
# Читает справочник из БД в порядке идентификаторов.
#
# @param _ Авторизованный сотрудник; значение непосредственно не используется.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Список DictionaryItem.
@router.get("/dictionaries/shipment-types", response_model=list[DictionaryItem])
def list_shipment_types(_: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    rows = db.execute(select(ShipmentType).order_by(ShipmentType.id)).scalars().all()
    return [DictionaryItem(id=r.id, code=r.code, name=r.name) for r in rows]


## @brief Возвращает типы документов для оператора.
#
# Роль OPERATOR проверяется дополнительно к авторизации.
#
# @param user Текущий сотрудник.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Список DictionaryItem.
# @exception errors.APIError 403 при роли, отличной от OPERATOR.
@router.get("/dictionaries/document-types", response_model=list[DictionaryItem])
def list_document_types(user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    if user.role != Role.OPERATOR:
        raise forbidden()
    rows = db.execute(select(DocumentType).order_by(DocumentType.id)).scalars().all()
    return [DictionaryItem(id=r.id, code=r.code, name=r.name) for r in rows]