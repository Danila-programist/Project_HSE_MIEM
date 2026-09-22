import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import CurrentUser
from ..errors import APIError
from ..models import Employee, UserSession
from ..schemas import LoginRequest, UserProfile
from ..security import verify_password
from ..serializers import node_ref

router = APIRouter(tags=["Аутентификация"])


@router.post("/auth/login", response_model=UserProfile)
def login(payload: LoginRequest, response: Response, db: Annotated[Session, Depends(get_db)]):
    emp = db.execute(select(Employee).where(Employee.login == payload.login)).scalar_one_or_none()
    if emp is None or not verify_password(payload.password, emp.password_hash):
        raise APIError(401, "INVALID_CREDENTIALS", "Неверный логин или пароль")
    if emp.blocked:
        raise APIError(403, "ACCOUNT_BLOCKED", "Учётная запись заблокирована")

    sid = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
    db.add(UserSession(id=sid, employee_id=emp.id, expires_at=expires))
    db.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=sid,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return UserProfile(
        id=emp.id,
        login=emp.login,
        fullName=emp.full_name,
        role=emp.role,
        node=node_ref(emp.node) if emp.node else None,
    )


@router.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    session_id: Annotated[str | None, Cookie(alias="SESSION")] = None,
):
    if session_id:
        sess = db.get(UserSession, session_id)
        if sess is not None:
            db.delete(sess)
            db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/auth/me", response_model=UserProfile)
def me(user: CurrentUser):
    return UserProfile(
        id=user.id,
        login=user.login,
        fullName=user.full_name,
        role=user.role,
        node=node_ref(user.node) if user.node else None,
    )