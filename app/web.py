from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import get_db
from .enums import Role
from .models import Employee, UserSession
from .serializers import node_ref

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _page_user(request: Request, db: Session) -> Employee | None:
    sid = request.cookies.get("SESSION")
    if not sid:
        return None
    sess = db.get(UserSession, sid)
    if sess is None:
        return None
    emp = db.get(Employee, sess.employee_id)
    if emp is None or emp.blocked:
        return None
    return emp


def _render(request: Request, name: str, user: Employee | None = None):
    ctx = {"request": request}
    if user is not None:
        ctx["user"] = {
            "id": user.id,
            "login": user.login,
            "fullName": user.full_name,
            "role": user.role.value,
            "node": node_ref(user.node).model_dump() if user.node else None,
        }
    return templates.TemplateResponse(name, ctx)


@router.get("/")
def index():
    return RedirectResponse("/tracking", status_code=302)


@router.get("/tracking")
def tracking_page(request: Request):
    return _render(request, "tracking.html")


@router.get("/login")
def login_page(request: Request):
    return _render(request, "login.html")


@router.get("/operator")
def operator_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    user = _page_user(request, db)
    if user is None or user.role != Role.OPERATOR:
        return RedirectResponse("/login", status_code=302)
    return _render(request, "operator.html", user)


@router.get("/sorter")
def sorter_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    user = _page_user(request, db)
    if user is None or user.role != Role.SORTING_EMPLOYEE:
        return RedirectResponse("/login", status_code=302)
    return _render(request, "sorter.html", user)


@router.get("/admin")
def admin_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    user = _page_user(request, db)
    if user is None or user.role != Role.ADMIN:
        return RedirectResponse("/login", status_code=302)
    return _render(request, "admin.html", user)