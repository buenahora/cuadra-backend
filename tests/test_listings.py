from fastapi.testclient import TestClient


def test_create_get_update_delete_listing(
    client: TestClient, auth_headers: dict[str, str], created_listing: dict
) -> None:
    listing_id = created_listing["id"]
    assert created_listing["estado_publicacion"] == "activo"
    assert created_listing["estado_comercial"] == "disponible"
    assert len(created_listing["fotos"]) == 3
    assert "market_position" in created_listing

    detail = client.get(f"/listings/{listing_id}")
    assert detail.status_code == 200
    assert detail.json()["titulo"] == "Depto de prueba en Cordón"

    patch = client.patch(
        f"/listings/{listing_id}",
        json={"precio": 21500, "estado_publicacion": "pausado"},
        headers=auth_headers,
    )
    assert patch.status_code == 200
    assert patch.json()["precio"] == 21500
    assert patch.json()["estado_publicacion"] == "pausado"

    delete = client.delete(f"/listings/{listing_id}", headers=auth_headers)
    assert delete.status_code == 204
    archived = client.get(f"/listings/{listing_id}")
    assert archived.json()["estado_publicacion"] == "archivado"


def test_get_missing_listing_404(client: TestClient) -> None:
    resp = client.get("/listings/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_only_owner_can_update_or_delete(
    client: TestClient, created_listing: dict
) -> None:
    other = client.post(
        "/auth/register",
        json={"nombre_completo": "Otro User", "email": "otro-owner-test@cuadra.uy", "password": "correcta123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    listing_id = created_listing["id"]

    patch = client.patch(f"/listings/{listing_id}", json={"precio": 1}, headers=other_headers)
    assert patch.status_code == 403

    delete = client.delete(f"/listings/{listing_id}", headers=other_headers)
    assert delete.status_code == 403


def test_search_listings_pagination_and_filters(client: TestClient) -> None:
    resp = client.get("/listings", params={"page": 1, "page_size": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 5
    assert len(body["items"]) <= 5
    assert body["total"] >= len(body["items"])

    filtered = client.get("/listings", params={"dormitorios": 1, "page_size": 100})
    assert filtered.status_code == 200
    assert all(item["dormitorios"] == 1 for item in filtered.json()["items"])


def test_search_listings_by_radius(client: TestClient) -> None:
    resp = client.get(
        "/listings",
        params={"lat": -34.9083, "lng": -56.1670, "radio_m": 50000, "page_size": 100},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] > 0


def test_my_listings_requires_auth(client: TestClient) -> None:
    resp = client.get("/users/me/listings")
    assert resp.status_code == 401


def test_my_listings_returns_created_one(
    client: TestClient, auth_headers: dict[str, str], created_listing: dict
) -> None:
    resp = client.get("/users/me/listings", headers=auth_headers)
    assert resp.status_code == 200
    ids = [l["id"] for l in resp.json()]
    assert created_listing["id"] in ids
