## @file
# @brief Создание первого администратора из окружения.
#
# Запускается как python -m seed. Существующая запись с тем же логином не изменяется.
"""Идемпотентно создаёт первого администратора, если заданы env-переменные."""
import os

from sqlalchemy import select

from .db import SessionLocal
from .enums import Role
from .models import Employee
from .security import hash_password


## @brief Создаёт начального администратора при необходимости.
#
# Читает ADMIN_LOGIN, ADMIN_PASSWORD и ADMIN_FULL_NAME. Без логина или пароля, а также при существующем логине, ничего не создаёт.
#
# @note Возвращает None; при создании запись подтверждается в БД.
def seed_admin() -> None:
    login = os.environ.get("ADMIN_LOGIN")
    password = os.environ.get("ADMIN_PASSWORD")
    full_name = os.environ.get("ADMIN_FULL_NAME", "Администратор")
    if not login or not password:
        return
    with SessionLocal() as db:
        if db.scalar(select(Employee).where(Employee.login == login)):
            print(f"[seed] admin '{login}' already exists")
            return
        emp = Employee(
            login=login,
            password_hash=hash_password(password),
            full_name=full_name,
            role=Role.ADMIN,
            node_id=None,
            blocked=False,
        )
        db.add(emp)
        db.commit()
        print(f"[seed] admin '{login}' created (id={emp.id})")


if __name__ == "__main__":
    seed_admin()