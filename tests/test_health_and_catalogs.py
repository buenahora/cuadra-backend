from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_zones_includes_original_15_barrios(client: TestClient) -> None:
    # >= 15, no == 15: desde 2026-08-15 el catálogo sale del warehouse real
    # de data_layer (ver app/repositories/warehouse/zones_repo.py), que ya
    # trae más zonas que las 15 originales del prototipo -- se verifica que
    # esas 15 sigan estando, no una cantidad exacta.
    resp = client.get("/zones")
    assert resp.status_code == 200
    zones = resp.json()
    assert len(zones) >= 15
    ids = {z["id"] for z in zones}
    assert {"pocitos", "cordon", "sayago", "cerro"}.issubset(ids)
    assert any(z["tiene_estadisticas"] for z in zones)
    assert any(not z["tiene_estadisticas"] for z in zones)


def test_get_zone_404(client: TestClient) -> None:
    resp = client.get("/zones/no-existe")
    assert resp.status_code == 404


def test_list_amenities_and_garantias(client: TestClient) -> None:
    amenities = client.get("/amenities").json()
    garantias = client.get("/garantias").json()
    assert len(amenities) == 12
    assert len(garantias) == 5
    assert {"id": "anda", "nombre": "ANDA"} in garantias
