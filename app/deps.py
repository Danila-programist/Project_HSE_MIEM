## @file
# @brief Зависимости FastAPI для проверки сессии и роли.
#
# Служебный запрос получает текущего незаблокированного сотрудника из cookie SESSION и записи в БД.
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from .db import get_db
from .enums import Role
from .errors import forbidden, unauthorized
from .models import Employee, UserSession


## @brief Проверяет сессию и возвращает сотрудника.
#
# Проверяет cookie, наличие и срок сессии, существование и блокировку сотрудника. Просроченная сессия удаляется.
#
# @param db Сессия SQLAlchemy текущего запроса.
# @param session_id Идентификатор сессии из cookie SESSION.
# @return Авторизованный сотрудник.
# @exception errors.APIError 401 при отсутствии действующей сессии или доступного сотрудника.
def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    session_id: Annotated[str | None, Cookie(alias="SESSION")] = None,
) -> Employee:
    if not session_id:
        raise unauthorized()
    sess = db.get(UserSession, session_id)
    if sess is None:
        raise unauthorized()
    if sess.expires_at < datetime.now(timezone.utc):
        db.delete(sess)
        db.commit()
        raise unauthorized()
    emp = db.get(Employee, sess.employee_id)
    if emp is None or emp.blocked:
        raise unauthorized()
    return emp


## @brief Создаёт зависимость проверки разрешённых ролей.
#
# Возвращённая функция использует get_current_user и отклоняет роль, отсутствующую в переданном наборе.
#
# @param roles Разрешённые роли сотрудников.
# @return Функция-зависимость FastAPI, возвращающая сотрудника.
def require_roles(*roles: Role):
    ## @brief Проверяет роль текущего сотрудника.
    #
    # Использует набор ролей из замыкания require_roles.
    #
    # @param user Текущий сотрудник.
    # @return Сотрудник с разрешённой ролью.
    # @exception errors.APIError 403 при запрещённой роли.
    def _check(user: Annotated[Employee, Depends(get_current_user)]) -> Employee:
        if user.role not in roles:
            raise forbidden()
        return user

    return _check


CurrentUser = Annotated[Employee, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]