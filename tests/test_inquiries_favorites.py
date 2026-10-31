import uuid

from fastapi.testclient import TestClient


def _second_user_headers(client: TestClient) -> dict[str, str]:
    email = f"inquilino-{uuid.uuid4().hex[:10]}@cuadra.uy"
    resp = client.post(
        "/auth/register",
        json={"nombre_completo": "Inquilino Test", "email": email, "password": "correcta123"},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_inquiry_flow(
    client: TestClient, auth_headers: dict[str, str], created_listing: dict
) -> None:
    listing_id = created_listing["id"]
    inquirer_headers = _second_user_headers(client)

    create = client.post(
        f"/listings/{listing_id}/inquiries",
        json={"nombre": "Inquilino Test", "email": "inquilino@example.com", "mensaje": "¿Sigue disponible?"},
        headers=inquirer_headers,
    )
    assert create.status_code == 201, create.text
    inquiry_id = create.json()["id"]
    assert create.json()["respuesta"] is None

    forbidden = client.get(f"/listings/{listing_id}/inquiries", headers=inquirer_headers)
    assert forbidden.status_code == 403

    received = client.get(f"/listings/{listing_id}/inquiries", headers=auth_headers)
    assert received.status_code == 200
    assert any(i["id"] == inquiry_id for i in received.json())

    mine = client.get("/users/me/inquiries", headers=inquirer_headers)
    assert any(i["id"] == inquiry_id for i in mine.json())

    forbidden_respond = client.patch(
        f"/inquiries/{inquiry_id}", json={"respuesta": "no debería poder"}, headers=inquirer_headers
    )
    assert forbidden_respond.status_code == 403

    respond = client.patch(
        f"/inquiries/{inquiry_id}", json={"respuesta": "Sí, sigue disponible"}, headers=auth_headers
    )
    assert respond.status_code == 200
    assert respond.json()["respuesta"] == "Sí, sigue disponible"
    assert respond.json()["respondido_en"] is not None

    listing_detail = client.get(f"/listings/{listing_id}").json()
    assert listing_detail["consultas_count"] == 1


def test_favorite_flow(
    client: TestClient, created_listing: dict
) -> None:
    listing_id = created_listing["id"]
    headers = _second_user_headers(client)

    add = client.post(f"/listings/{listing_id}/favorite", headers=headers)
    assert add.status_code == 204

    favorites = client.get("/users/me/favorites", headers=headers)
    assert any(f["id"] == listing_id for f in favorites.json())

    remove = client.delete(f"/listings/{listing_id}/favorite", headers=headers)
    assert remove.status_code == 204

    favorites_after = client.get("/users/me/favorites", headers=headers)
    assert not any(f["id"] == listing_id for f in favorites_after.json())
