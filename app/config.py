from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://isudo:isudo@localhost:5432/isudo"
    session_cookie_name: str = "SESSION"
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "strict"
    session_ttl_hours: int = 24
    log_level: str = "INFO"


settings = Settings()