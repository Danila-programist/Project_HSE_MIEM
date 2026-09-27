## @file
# @brief Хеширование и проверка паролей.
#
# Пароль сначала преобразуется SHA-256 и Base64, затем обрабатывается bcrypt со случайной солью.
import base64
import hashlib

import bcrypt


## @brief Создаёт адаптивный хеш пароля.
#
# SHA-256 и Base64 приводят вход к фиксированной длине перед bcrypt. Для каждого вызова создаётся новая соль.
#
# @param password Пароль в открытом виде.
# @return ASCII-строка хеша bcrypt.
def hash_password(password: str) -> str:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return bcrypt.hashpw(base64.b64encode(digest), bcrypt.gensalt()).decode("ascii")


## @brief Проверяет пароль по сохранённому хешу.
#
# Повторяет предварительное преобразование и вызывает bcrypt.checkpw. Ошибка формата хеша приводит к False.
#
# @param password Пароль в открытом виде.
# @param password_hash Сохранённый хеш bcrypt.
# @return True при совпадении, иначе False.
def verify_password(password: str, password_hash: str) -> bool:
    try:
        digest = hashlib.sha256(password.encode("utf-8")).digest()
        return bcrypt.checkpw(base64.b64encode(digest), password_hash.encode("ascii"))
    except Exception:
        return False