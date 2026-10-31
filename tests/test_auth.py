import uuid

from fastapi.testclient import TestClient


def test_register_login_me_flow(client: TestClient) -> None:
    email = f"flow-{uuid.uuid4().hex[:10]}@cuadra.uy"
    register = client.post(
        "/auth/register",
        json={"nombre_completo": "Ana Flow", "email": email, "password": "correcta123"},
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]

    dup = client.post(
        "/auth/register",
        json={"nombre_completo": "Otra", "email": email, "password": "correcta123"},
    )
    assert dup.status_code == 409

    bad_login = client.post("/auth/login", json={"email": email, "password": "incorrecta"})
    assert bad_login.status_code == 401

    login = client.post("/auth/login", json={"email": email, "password": "correcta123"})
    assert login.status_code == 200
    login_token = login.json()["access_token"]

    me = client.get("/users/me", headers={"Authorization": f"Bearer {login_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    me_no_token = client.get("/users/me")
    assert me_no_token.status_code == 401

    _ = token  # el token de registro también es válido, ver test siguiente


def test_register_token_is_usable_immediately(client: TestClient) -> None:
    email = f"immediate-{uuid.uuid4().hex[:10]}@cuadra.uy"
    register = client.post(
        "/auth/register",
        json={"nombre_completo": "Bruno", "email": email, "password": "correcta123"},
    )
    token = register.json()["access_token"]
    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email
