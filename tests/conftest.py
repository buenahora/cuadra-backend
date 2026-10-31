import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    email = f"test-{uuid.uuid4().hex[:10]}@cuadra.uy"
    resp = client.post(
        "/auth/register",
        json={
            "nombre_completo": "Usuaria de Prueba",
            "email": email,
            "password": "supersecreta123",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def zone_with_stats(client: TestClient) -> str:
    zones = client.get("/zones").json()
    for z in zones:
        if z["tiene_estadisticas"]:
            return z["id"]
    raise AssertionError("Ningún barrio sembrado tiene estadísticas -- revisar seed.py")


@pytest.fixture
def created_listing(
    client: TestClient, auth_headers: dict[str, str], zone_with_stats: str
) -> dict:
    payload = {
        "titulo": "Depto de prueba en Cordón",
        "descripcion": "Aviso creado por un test automático.",
        "direccion": "Bulevar Artigas 1234",
        "barrio_id": zone_with_stats,
        "ocultar_direccion": False,
        "dormitorios": 1,
        "banos": 1,
        "metraje_m2": 45,
        "planta_baja": False,
        "amueblado": "no",
        "permite_mascotas": True,
        "amenity_ids": [],
        "expensas_incluidas": False,
        "precio": 20000,
        "precio_negociable": False,
        "garantia_ids": [],
        "fotos": [
            "https://example.com/1.jpg",
            "https://example.com/2.jpg",
            "https://example.com/3.jpg",
        ],
        "disponible_desde": "2026-09-01",
    }
    resp = client.post("/listings", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()
