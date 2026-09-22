import secrets
import string

_ALPHABET = string.ascii_uppercase + string.digits


def generate_track_number() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(16))


def normalize_track_number(raw: str) -> str:
    return (raw or "").strip().upper()