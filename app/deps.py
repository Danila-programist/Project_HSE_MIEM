from datetime import datetime, timezone
from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from .db import get_db
from .enums import Role
from .errors import forbidden, unauthorized
from .models import Employee, UserSession


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


def require_roles(*roles: Role):
    def _check(user: Annotated[Employee, Depends(get_current_user)]) -> Employee:
        if user.role not in roles:
            raise forbidden()
        return user

    return _check


CurrentUser = Annotated[Employee, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]