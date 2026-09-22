from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_roles
from ..enums import NodeType, Role
from ..errors import conflict, not_found, validation_error
from ..models import Employee, Node
from ..schemas import PasswordSet, User, UserCreate, UserPage, UserUpdate
from ..security import hash_password
from ..serializers import employee_to_user_payload

router = APIRouter(tags=["Администрирование сотрудников"], dependencies=[Depends(require_roles(Role.ADMIN))])


def _user(emp: Employee) -> User:
    return User(**employee_to_user_payload(emp))


def _validate_role_node(db: Session, role: Role, node_id: int | None, *, require: bool) -> int | None:
    if role == Role.ADMIN:
        return None
    if node_id is None:
        if require:
            raise validation_error(
                "Укажите узел для выбранной роли",
                [{"field": "nodeId", "message": "Обязательное поле для этой роли"}],
            )
        return None
    node = db.get(Node, node_id)
    if node is None or not node.active:
        raise validation_error(
            "Узел недоступен",
            [{"field": "nodeId", "message": "Узел не найден или деактивирован"}],
        )
    if role == Role.OPERATOR and node.type != NodeType.SERVICE_POINT:
        raise validation_error(
            "Оператору требуется пункт обслуживания",
            [{"field": "nodeId", "message": "Выберите пункт обслуживания"}],
        )
    if role == Role.SORTING_EMPLOYEE and node.type != NodeType.SORTING_CENTER:
        raise validation_error(
            "Сотруднику сортировочного центра нужен сортировочный центр",
            [{"field": "nodeId", "message": "Выберите сортировочный центр"}],
        )
    return node.id


def _active_admin_count(db: Session, exclude_id: int | None = None) -> int:
    stmt = select(func.count()).select_from(Employee).where(
        Employee.role == Role.ADMIN, Employee.blocked.is_(False)
    )
    if exclude_id is not None:
        stmt = stmt.where(Employee.id != exclude_id)
    return db.scalar(stmt) or 0


@router.get("/admin/users", response_model=UserPage)
def list_users(
    db: Annotated[Session, Depends(get_db)],
    role: Role | None = None,
    blocked: bool | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    stmt = select(Employee)
    if role is not None:
        stmt = stmt.where(Employee.role == role)
    if blocked is not None:
        stmt = stmt.where(Employee.blocked == blocked)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Employee.id).offset((page - 1) * size).limit(size)).scalars().all()

    return UserPage(
        page=page,
        size=size,
        totalItems=total,
        totalPages=(total + size - 1) // size if size else 0,
        items=[_user(e) for e in rows],
    )


@router.post("/admin/users", response_model=User, status_code=201)
def create_user(payload: UserCreate, response: Response, db: Annotated[Session, Depends(get_db)]):
    if db.scalar(select(Employee).where(Employee.login == payload.login)):
        raise conflict("LOGIN_ALREADY_EXISTS", "Сотрудник с таким логином уже существует")

    node_id = _validate_role_node(db, payload.role, payload.nodeId, require=(payload.role != Role.ADMIN))

    emp = Employee(
        login=payload.login,
        password_hash=hash_password(payload.password),
        full_name=payload.fullName,
        role=payload.role,
        node_id=node_id,
        blocked=False,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)

    response.headers["Location"] = f"/api/v1/admin/users/{emp.id}"
    return _user(emp)


@router.get("/admin/users/{userId}", response_model=User)
def get_user(userId: int, db: Annotated[Session, Depends(get_db)]):
    emp = db.get(Employee, userId)
    if emp is None:
        raise not_found()
    return _user(emp)


@router.patch("/admin/users/{userId}", response_model=User)
def update_user(userId: int, payload: UserUpdate, db: Annotated[Session, Depends(get_db)]):
    emp = db.get(Employee, userId)
    if emp is None:
        raise not_found()

    data = payload.model_dump(exclude_unset=True)
    new_role = data.get("role", emp.role)
    new_node_id = data.get("nodeId", emp.node_id)

    if "login" in data and data["login"] != emp.login:
        if db.scalar(select(Employee).where(Employee.login == data["login"], Employee.id != emp.id)):
            raise conflict("LOGIN_ALREADY_EXISTS", "Сотрудник с таким логином уже существует")

    role_changing_from_admin = emp.role == Role.ADMIN and (new_role != Role.ADMIN)
    if role_changing_from_admin and not emp.blocked and _active_admin_count(db, exclude_id=emp.id) == 0:
        raise conflict("LAST_ADMIN", "Нельзя лишить роли последнего активного администратора")

    if new_role == Role.ADMIN:
        new_node_id = None
    else:
        new_node_id = _validate_role_node(db, new_role, new_node_id, require=True)

    if "login" in data:
        emp.login = data["login"]
    if "fullName" in data:
        emp.full_name = data["fullName"]
    emp.role = new_role
    emp.node_id = new_node_id

    db.commit()
    db.refresh(emp)
    return _user(emp)


@router.post("/admin/users/{userId}/block", response_model=User)
def block_user(userId: int, db: Annotated[Session, Depends(get_db)]):
    emp = db.get(Employee, userId)
    if emp is None:
        raise not_found()
    if emp.role == Role.ADMIN and not emp.blocked and _active_admin_count(db, exclude_id=emp.id) == 0:
        raise conflict("LAST_ADMIN", "Нельзя заблокировать последнего активного администратора")
    emp.blocked = True
    db.commit()
    db.refresh(emp)
    return _user(emp)


@router.post("/admin/users/{userId}/unblock", response_model=User)
def unblock_user(userId: int, db: Annotated[Session, Depends(get_db)]):
    emp = db.get(Employee, userId)
    if emp is None:
        raise not_found()
    emp.blocked = False
    db.commit()
    db.refresh(emp)
    return _user(emp)


@router.put("/admin/users/{userId}/password", status_code=204)
def set_password(userId: int, payload: PasswordSet, db: Annotated[Session, Depends(get_db)]):
    emp = db.get(Employee, userId)
    if emp is None:
        raise not_found()
    emp.password_hash = hash_password(payload.newPassword)
    db.commit()