## @file
# @brief Окружение миграций Alembic.
#
# Подключает метаданные ORM и выбирает онлайн- или офлайн-режим. DATABASE_URL переопределяет URL конфигурации.
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import Base
from app import models  # noqa: F401 — регистрирует модели в metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


## @brief Готовит миграции без подключения к БД.
#
# Конфигурирует Alembic для SQL-вывода с литеральными параметрами.
#
# @note Возвращает None.
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


## @brief Применяет миграции через подключение к БД.
#
# Создаёт engine с NullPool и запускает миграции в транзакции Alembic.
#
# @note Возвращает None.
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()