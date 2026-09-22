from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, field_errors: list | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors


def unauthorized(msg: str = "Требуется вход в систему") -> APIError:
    return APIError(401, "UNAUTHORIZED", msg)


def forbidden(msg: str = "Недостаточно прав для выполнения операции") -> APIError:
    return APIError(403, "FORBIDDEN", msg)


def not_found(msg: str = "Запись не найдена") -> APIError:
    return APIError(404, "NOT_FOUND", msg)


def conflict(code: str, msg: str) -> APIError:
    return APIError(409, code, msg)


def validation_error(msg: str = "Проверьте заполнение формы", field_errors: list | None = None) -> APIError:
    return APIError(400, "VALIDATION_ERROR", msg, field_errors)


def storage_unavailable() -> APIError:
    return APIError(503, "STORAGE_UNAVAILABLE", "Сервис временно недоступен. Операция не выполнена")


def _payload(code: str, message: str, field_errors: list | None = None) -> dict:
    body = {"code": code, "message": message}
    if field_errors:
        body["fieldErrors"] = field_errors
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code, exc.message, exc.field_errors),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        field_errors = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
            field_errors.append({"field": ".".join(loc) or "body", "message": err.get("msg", "Некорректное значение")})
        return JSONResponse(
            status_code=400,
            content=_payload("VALIDATION_ERROR", "Проверьте заполнение формы", field_errors),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 401:
            return JSONResponse(status_code=401, content=_payload("UNAUTHORIZED", "Требуется вход в систему"))
        if exc.status_code == 403:
            return JSONResponse(status_code=403, content=_payload("FORBIDDEN", "Недостаточно прав для выполнения операции"))
        if exc.status_code == 404:
            return JSONResponse(status_code=404, content=_payload("NOT_FOUND", "Запись не найдена"))
        return JSONResponse(status_code=exc.status_code, content=_payload("INTERNAL_ERROR", "Внутренняя ошибка"))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, __: Exception):
        return JSONResponse(
            status_code=500,
            content=_payload("INTERNAL_ERROR", "Внутренняя ошибка сервера"),
        )