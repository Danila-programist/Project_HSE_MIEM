## @file
# @brief Настройки приложения из переменных окружения.
#
# Pydantic Settings читает окружение и необязательный файл .env; значения по умолчанию предназначены для разработки.
from pydantic_settings import BaseSettings, SettingsConfigDict


## @brief Настройки приложения.
#
# Значения берутся из окружения и .env; имена переменных соответствуют полям без учёта регистра.
class Settings(BaseSettings):
    ## @brief Настройки чтения и проверки модели Pydantic.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ## @brief Строка подключения SQLAlchemy к PostgreSQL.
    database_url: str = "postgresql+psycopg://isudo:isudo@localhost:5432/isudo"
    ## @brief Имя cookie при установке; чтение текущими зависимостями использует SESSION.
    session_cookie_name: str = "SESSION"
    ## @brief Передавать cookie только через HTTPS.
    session_cookie_secure: bool = False
    ## @brief Политика SameSite cookie.
    session_cookie_samesite: str = "strict"
    ## @brief Срок жизни сессии в часах.
    session_ttl_hours: int = 24
    ## @brief Настройка уровня журналирования; main.py её пока не применяет.
    log_level: str = "INFO"


settings = Settings()