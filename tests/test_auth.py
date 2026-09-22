from datetime import datetime, timedelta, timezone

from app.enums import Role
from app.models import UserSession


def test_login_success_returns_profile_and_sets_cookie(client, make_employee):
    emp, password = make_employee(Role.ADMIN)
    resp = client.post("/api/v1/auth/login", json={"login": emp.login, "password": password})
    assert resp.status_code == 200
    body = resp.json()
    assert body["login"] == emp.login
    assert body["role"] == "ADMIN"
    assert "SESSION" in resp.cookies


def test_login_wrong_password_rejected(client, make_employee):
    emp, _ = make_employee(Role.ADMIN)
    resp = client.post("/api/v1/auth/login", json={"login": emp.login, "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_login_rejected(client):
    resp = client.post("/api/v1/auth/login", json={"login": "nobody", "password": "whatever"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


def test_login_blocked_account_rejected(client, make_employee):
    emp, password = make_employee(Role.ADMIN, blocked=True)
    resp = client.post("/api/v1/auth/login", json={"login": emp.login, "password": password})
    assert resp.status_code == 403
    assert resp.json()["code"] == "ACCOUNT_BLOCKED"


def test_me_requires_authentication(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_logout_invalidates_session(client, make_employee):
    emp, password = make_employee(Role.ADMIN)
    client.post("/api/v1/auth/login", json={"login": emp.login, "password": password})
    assert client.get("/api/v1/auth/me").status_code == 200

    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 204

    assert client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected_and_cleaned_up(client, db_session, make_employee):
    emp, password = make_employee(Role.ADMIN)
    login_resp = client.post("/api/v1/auth/login", json={"login": emp.login, "password": password})
    sid = login_resp.cookies["SESSION"]

    sess = db_session.get(UserSession, sid)
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.flush()

    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert db_session.get(UserSession, sid) is None
