from app.security import hash_password, verify_password


def test_verify_password_roundtrip_succeeds():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_password_rejects_wrong_password():
    h = hash_password("correct horse battery staple")
    assert verify_password("wrong password", h) is False


def test_verify_password_rejects_malformed_hash():
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False


def test_hash_password_produces_different_hashes_for_same_password():
    h1 = hash_password("same password")
    h2 = hash_password("same password")
    assert h1 != h2
    assert verify_password("same password", h1) is True
    assert verify_password("same password", h2) is True
