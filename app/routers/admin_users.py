## @file
# @brief Управление учётными записями сотрудников.
#
# Роутер требует ADMIN; проверяет соответствие роли типу узла и сохраняет последнего активного администратора.
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


## @brief Преобразует сотрудника в административную карточку.
#
# Использует общий сериализатор без пароля и его хеша.
#
# @param emp ORM-запись сотрудника.
# @return Модель User.
def _user(emp: Employee) -> User:
    return User(**employee_to_user_payload(emp))


## @brief Проверяет соответствие роли выбранному узлу.
#
# Администратору узел не назначается; оператору нужен активный пункт, сортировщику — активный центр.
#
# @param db Сессия SQLAlchemy текущего запроса.
# @param role Роль сотрудника.
# @param node_id Идентификатор узла или None.
# @param require Требовать ли обязательное назначение узла.
# @return Идентификатор подходящего узла либо None.
# @exception errors.APIError 400 при отсутствии или несовместимости узла.
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


## @brief Считает активных администраторов.
#
# При необходимости исключает одного сотрудника для проверки возможности изменения его роли или блокировки.
#
# @param db Сессия SQLAlchemy текущего запроса.
# @param exclude_id Идентификатор исключаемого сотрудника или None.
# @return Количество незаблокированных администраторов.
def _active_admin_count(db: Session, exclude_id: int | None = None) -> int:
    stmt = select(func.count()).select_from(Employee).where(
        Employee.role == Role.ADMIN, Employee.blocked.is_(False)
    )
    if exclude_id is not None:
        stmt = stmt.where(Employee.id != exclude_id)
    return db.scalar(stmt) or 0


## @brief Возвращает страницу сотрудников.
#
# Фильтрует по роли и блокировке, сортирует по идентификатору.
#
# @param db Сессия SQLAlchemy текущего запроса.
# @param role Фильтр по роли либо None.
# @param blocked Фильтр по блокировке; None отключает фильтр.
# @param page Номер страницы, начиная с 1.
# @param size Максимальное число элементов страницы (1–100 в API).
# @return UserPage с элементами и метаданными пагинации.
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


## @brief Создаёт сотрудника с хешированным паролем.
#
# Проверяет уникальность логина и совместимость роли с узлом; устанавливает Location.
#
# @param payload Проверенная Pydantic-модель тела запроса.
# @param response HTTP-ответ для установки заголовков или cookie.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Созданная модель User; HTTP 201.
# @exception errors.APIError 409 при занятом логине; 400 при недопустимом назначении узла.
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


## @brief Возвращает карточку сотрудника по идентификатору.
#
# Доступ ограничен административной зависимостью роутера.
#
# @param userId Идентификатор сотрудника.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Модель User.
# @exception errors.APIError 404 при отсутствии сотрудника.
@router.get("/admin/users/{userId}", response_model=User)
def get_user(userId: int, db: Annotated[Session, Depends(get_db)]):
    emp = db.get(Employee, userId)
    if emp is None:
        raise not_found()
    return _user(emp)


## @brief Обновляет учётную запись сотрудника.
#
# Проверяет логин и назначение узла; запрещает лишать роли последнего активного администратора.
#
# @param userId Идентификатор сотрудника.
# @param payload Проверенная Pydantic-модель тела запроса.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Обновлённая модель User.
# @exception errors.APIError 404 при отсутствии сотрудника; 400 при неверном узле; 409 при конфликте логина или последнем администраторе.
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


## @brief Блокирует сотрудника.
#
# Последний активный администратор защищён от блокировки. API проверит blocked при следующем запросе.
#
# @param userId Идентификатор сотрудника.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Модель User с blocked=True.
# @exception errors.APIError 404 при отсутствии сотрудника; 409 при блокировке последнего администратора.
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


## @brief Снимает блокировку сотрудника.
#
# Меняет флаг blocked, не изменяя роль, пароль или назначенный узел.
#
# @param userId Идентификатор сотрудника.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Модель User с blocked=False.
# @exception errors.APIError 404 при отсутствии сотрудника.
@router.post("/admin/users/{userId}/unblock", response_model=User)
def unblock_user(userId: int, db: Annotated[Session, Depends(get_db)]):
    emp = db.get(Employee, userId)
    if emp is None:
        raise not_found()
    emp.blocked = False
    db.commit()
    db.refresh(emp)
    return _user(emp)


## @brief Задаёт новый пароль сотруднику.
#
# Сохраняет новый хеш. Существующие сессии эта функция не удаляет.
#
# @param userId Идентификатор сотрудника.
# @param payload Проверенная Pydantic-модель тела запроса.
# @param db Сессия SQLAlchemy текущего запроса.
# @note Возвращает None; HTTP 204.
# @exception errors.APIError 404 при отсутствии сотрудника.
@router.put("/admin/users/{userId}/password", status_code=204)
def set_password(userId: int, payload: PasswordSet, db: Annotated[Session, Depends(get_db)]):
    emp = db.get(Employee, userId)
    if emp is None:
        raise not_found()
    emp.password_hash = hash_password(payload.newPassword)
    db.commit()