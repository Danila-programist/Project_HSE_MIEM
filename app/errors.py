## @file
# @brief Единый формат ошибок API.
#
# Фабрики создают APIError, а зарегистрированные обработчики преобразуют исключения в JSON с HTTP-статусом.
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


## @brief Прикладное исключение API.
#
# Наследует Exception; обработчик преобразует атрибуты экземпляра в HTTP-статус и JSON-ответ.
class APIError(Exception):
    ## @brief Создаёт прикладную ошибку API.
    #
    # Сохраняет HTTP-статус, машинный код, сообщение и необязательные ошибки полей для JSON-обработчика.
    #
    # @param self Экземпляр класса.
    # @param status_code HTTP-статус ошибки.
    # @param code Машинный код ошибки.
    # @param message Сообщение для пользователя.
    # @param field_errors Ошибки отдельных полей или None.
    # @note Возвращает None.
    def __init__(self, status_code: int, code: str, message: str, field_errors: list | None = None):
        ## @brief HTTP-статус ответа.
        self.status_code = status_code
        ## @brief Машинный код ошибки.
        self.code = code
        ## @brief Сообщение для пользователя.
        self.message = message
        ## @brief Список ошибок полей либо None.
        self.field_errors = field_errors


## @brief Создаёт ошибку отсутствия авторизации.
#
# Используется при отсутствующей или недействительной сессии.
#
# @param msg Сообщение для пользователя.
# @return APIError со статусом 401 и кодом UNAUTHORIZED.
def unauthorized(msg: str = "Требуется вход в систему") -> APIError:
    return APIError(401, "UNAUTHORIZED", msg)


## @brief Создаёт ошибку недостаточных прав.
#
# Используется при несоответствии роли или узла сотрудника.
#
# @param msg Сообщение для пользователя.
# @return APIError со статусом 403 и кодом FORBIDDEN.
def forbidden(msg: str = "Недостаточно прав для выполнения операции") -> APIError:
    return APIError(403, "FORBIDDEN", msg)


## @brief Создаёт ошибку отсутствующей записи.
#
# Сообщение может уточнять, какая сущность не найдена.
#
# @param msg Сообщение для пользователя.
# @return APIError со статусом 404 и кодом NOT_FOUND.
def not_found(msg: str = "Запись не найдена") -> APIError:
    return APIError(404, "NOT_FOUND", msg)


## @brief Создаёт ошибку конфликта состояния.
#
# Принимает машинный код причины, например INVALID_TRANSITION или LAST_ADMIN.
#
# @param code Машинный код ошибки.
# @param msg Сообщение для пользователя.
# @return APIError со статусом 409.
def conflict(code: str, msg: str) -> APIError:
    return APIError(409, code, msg)


## @brief Создаёт ошибку проверки входных данных.
#
# Может содержать список полей с объяснениями ошибок.
#
# @param msg Сообщение для пользователя.
# @param field_errors Ошибки отдельных полей или None.
# @return APIError со статусом 400 и кодом VALIDATION_ERROR.
def validation_error(msg: str = "Проверьте заполнение формы", field_errors: list | None = None) -> APIError:
    return APIError(400, "VALIDATION_ERROR", msg, field_errors)


## @brief Создаёт ошибку недоступности хранилища.
#
# Фабрика не перехватывает исключения SQLAlchemy автоматически.
#
# @return APIError со статусом 503 и кодом STORAGE_UNAVAILABLE.
def storage_unavailable() -> APIError:
    return APIError(503, "STORAGE_UNAVAILABLE", "Сервис временно недоступен. Операция не выполнена")


## @brief Формирует тело ответа об ошибке.
#
# Добавляет fieldErrors только при непустом списке ошибок полей.
#
# @param code Машинный код ошибки.
# @param message Сообщение для пользователя.
# @param field_errors Ошибки отдельных полей или None.
# @return Словарь с code, message и необязательным fieldErrors.
def _payload(code: str, message: str, field_errors: list | None = None) -> dict:
    body = {"code": code, "message": message}
    if field_errors:
        body["fieldErrors"] = field_errors
    return body


## @brief Регистрирует обработчики исключений FastAPI.
#
# Устанавливает единый JSON-формат для APIError, ошибок валидации, HTTPException и остальных исключений.
#
# @param app Приложение FastAPI.
# @note Возвращает None; обработчики добавляются в приложение.
def register_exception_handlers(app: FastAPI) -> None:
    ## @brief Преобразует APIError в JSON.
    #
    # Передаёт заданные исключением статус и поля ответа.
    #
    # @param _ Входящий HTTP-запрос; не используется.
    # @param exc Перехваченное исключение.
    # @return JSONResponse с прикладной ошибкой.
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code, exc.message, exc.field_errors),
        )

    ## @brief Преобразует ошибки Pydantic в ответ API.
    #
    # Исключает body, query и path из пути поля и возвращает ошибки с HTTP 400.
    #
    # @param _ Входящий HTTP-запрос; не используется.
    # @param exc Перехваченное исключение.
    # @return JSONResponse с кодом VALIDATION_ERROR.
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

    ## @brief Преобразует HTTP-исключение в единый формат.
    #
    # Отдельно обрабатывает 401, 403 и 404; для остальных сохраняет статус и использует общий код.
    #
    # @param _ Входящий HTTP-запрос; не используется.
    # @param exc Перехваченное исключение.
    # @return JSONResponse с исходным HTTP-статусом.
    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 401:
            return JSONResponse(status_code=401, content=_payload("UNAUTHORIZED", "Требуется вход в систему"))
        if exc.status_code == 403:
            return JSONResponse(status_code=403, content=_payload("FORBIDDEN", "Недостаточно прав для выполнения операции"))
        if exc.status_code == 404:
            return JSONResponse(status_code=404, content=_payload("NOT_FOUND", "Запись не найдена"))
        return JSONResponse(status_code=exc.status_code, content=_payload("INTERNAL_ERROR", "Внутренняя ошибка"))

    ## @brief Формирует ответ на необработанное исключение.
    #
    # Не включает внутренние подробности исключения в ответ клиенту.
    #
    # @param _ Входящий HTTP-запрос; не используется.
    # @param __ Необработанное исключение.
    # @return JSONResponse со статусом 500.
    @app.exception_handler(Exception)
    async def _unhandled(_: Request, __: Exception):
        return JSONResponse(
            status_code=500,
            content=_payload("INTERNAL_ERROR", "Внутренняя ошибка сервера"),
        )