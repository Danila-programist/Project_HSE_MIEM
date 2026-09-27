## @file
# @brief Создание и нормализация трек-номеров.
#
# Трек-номер состоит из 16 символов A–Z и 0–9. Уникальность обеспечивается при сохранении в БД.
import secrets
import string

_ALPHABET = string.ascii_uppercase + string.digits


## @brief Генерирует случайный трек-номер.
#
# Использует secrets.choice для 16 символов из латинских заглавных букв и цифр. Базу данных не проверяет.
#
# @return Строка длиной 16 символов.
def generate_track_number() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(16))


## @brief Нормализует введённый трек-номер.
#
# Удаляет внешние пробелы и переводит строку в верхний регистр; длину и алфавит не проверяет.
#
# @param raw Введённая строка трек-номера.
# @return Нормализованная строка, либо пустая строка для пустого входа.
def normalize_track_number(raw: str) -> str:
    return (raw or "").strip().upper()