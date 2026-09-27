## @file
# @brief Подключение к PostgreSQL и управление сессиями SQLAlchemy.
#
# Общий Base используется моделями и Alembic. Зависимость get_db закрывает сессию после запроса; commit выполняют обработчики.
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


## @brief Базовый класс ORM-моделей.
#
# Наследует DeclarativeBase и объединяет метаданные таблиц, используемые Alembic.
class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


## @brief Предоставляет сессию БД на время запроса.
#
# Создаёт SessionLocal и гарантированно закрывает её в finally. Самостоятельно не подтверждает изменения.
#
# @return Генератор, выдающий одну сессию SQLAlchemy.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()