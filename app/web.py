## @file
# @brief HTML-маршруты и подготовка контекста Jinja2.
#
# Отдаёт страницы /tracking, /login, /operator, /sorter и /admin. Полномочия API проверяются отдельно в deps.
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


## @brief Находит сотрудника для HTML-страницы.
#
# Проверяет наличие сессии и блокировку сотрудника. В отличие от API-зависимости, срок сессии здесь не проверяется.
#
# @param request Входящий HTTP-запрос.
# @param db Сессия SQLAlchemy текущего запроса.
# @return Сотрудник либо None.
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


## @brief Формирует HTML из шаблона Jinja2.
#
# Передаёт request и, при наличии, ограниченный набор полей сотрудника в контекст.
#
# @param request Входящий HTTP-запрос.
# @param name Имя файла шаблона Jinja2.
# @param user Сотрудник для контекста шаблона или None.
# @return TemplateResponse с HTML-страницей.
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


## @brief Перенаправляет корневой URL на отслеживание.
#
# Использует временное перенаправление HTTP 302.
#
# @return RedirectResponse на /tracking.
@router.get("/")
def index():
    return RedirectResponse("/tracking", status_code=302)


## @brief Открывает публичную страницу отслеживания.
#
# Сессия сотрудника для доступа не требуется.
#
# @param request Входящий HTTP-запрос.
# @return HTML-страница tracking.html.
@router.get("/tracking")
def tracking_page(request: Request):
    return _render(request, "tracking.html")


## @brief Открывает страницу входа.
#
# Форма отправляет логин и пароль в API авторизации.
#
# @param request Входящий HTTP-запрос.
# @return HTML-страница login.html.
@router.get("/login")
def login_page(request: Request):
    return _render(request, "login.html")


## @brief Открывает рабочее место оператора.
#
# При отсутствии сотрудника с ролью OPERATOR направляет на /login.
#
# @param request Входящий HTTP-запрос.
# @param db Сессия SQLAlchemy текущего запроса.
# @return HTML-страница либо перенаправление.
@router.get("/operator")
def operator_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    user = _page_user(request, db)
    if user is None or user.role != Role.OPERATOR:
        return RedirectResponse("/login", status_code=302)
    return _render(request, "operator.html", user)


## @brief Открывает рабочее место сортировщика.
#
# При отсутствии сотрудника с ролью SORTING_EMPLOYEE направляет на /login.
#
# @param request Входящий HTTP-запрос.
# @param db Сессия SQLAlchemy текущего запроса.
# @return HTML-страница либо перенаправление.
@router.get("/sorter")
def sorter_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    user = _page_user(request, db)
    if user is None or user.role != Role.SORTING_EMPLOYEE:
        return RedirectResponse("/login", status_code=302)
    return _render(request, "sorter.html", user)


## @brief Открывает рабочее место администратора.
#
# При отсутствии сотрудника с ролью ADMIN направляет на /login.
#
# @param request Входящий HTTP-запрос.
# @param db Сессия SQLAlchemy текущего запроса.
# @return HTML-страница либо перенаправление.
@router.get("/admin")
def admin_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    user = _page_user(request, db)
    if user is None or user.role != Role.ADMIN:
        return RedirectResponse("/login", status_code=302)
    return _render(request, "admin.html", user)