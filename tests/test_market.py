from fastapi.testclient import TestClient


def _confident_stat(client: TestClient, zone_id: str) -> dict:
    stats = client.get("/market/stats", params={"zone_id": zone_id}).json()
    confident = [s for s in stats if s["muestra_confiable"]]
    assert confident, f"Se esperaba al menos una combinación confiable en {zone_id}"
    return confident[0]


def test_market_stats_for_zone_with_data(client: TestClient, zone_with_stats: str) -> None:
    stat = _confident_stat(client, zone_with_stats)
    assert stat["precio_min"] <= stat["precio_mediana"] <= stat["precio_max"]
    assert stat["avisos_activos"] >= 5


def test_market_stats_unknown_zone_is_empty(client: TestClient) -> None:
    resp = client.get("/market/stats", params={"zone_id": "sayago", "dormitorios_bucket": "3+"})
    assert resp.status_code == 200
    assert resp.json() == [] or all(not s["muestra_confiable"] for s in resp.json())


def test_market_snapshots_has_12_points(client: TestClient) -> None:
    # zone_with_stats no sirve acá desde que /zones sale del warehouse real
    # (2026-08-15, ver app/repositories/warehouse/zones_repo.py): casi
    # cualquier zona real tiene avisos activos (tiene_estadisticas), pero
    # el histórico sintético sembrado en memoria (ver _seed_market_history
    # en app/repositories/memory/seed.py) solo cubre combinaciones
    # zona+dormitorios con >=5 avisos EN MEMORIA -- que ya no coincide
    # necesariamente con la primera combinación "confiable" que devuelve
    # /market/stats, calculado ahora sobre avisos reales + sintéticos
    # combinados. "cordon" es uno de los 6 barrios originalmente sembrados,
    # pero se prueban sus 3 buckets en vez de asumir cuál tiene histórico.
    snapshots = None
    for bucket in ("1", "2", "3+"):
        resp = client.get(
            "/market/snapshots", params={"zone_id": "cordon", "dormitorios_bucket": bucket}
        )
        assert resp.status_code == 200
        candidate = resp.json()
        if len(candidate) >= 12:
            snapshots = candidate
            break
    assert snapshots is not None, "ningún bucket de 'cordon' tiene histórico sembrado completo"
    # 12 meses sembrados, + el punto de este mes si esa combinación da
    # muestra confiable (ver app/api/routes/market.py get_market_snapshots).
    assert len(snapshots) in (12, 13)
    periodos = [s["periodo"] for s in snapshots]
    assert periodos == sorted(periodos)


def test_classify_below_in_above(client: TestClient, zone_with_stats: str) -> None:
    stat = _confident_stat(client, zone_with_stats)
    mediana = stat["precio_mediana"]
    bucket = stat["dormitorios_bucket"]

    below = client.post(
        "/market/classify",
        json={"precio": mediana * 0.5, "zone_id": zone_with_stats, "dormitorios_bucket": bucket},
    ).json()
    assert below["nivel"] == "below"

    above = client.post(
        "/market/classify",
        json={"precio": mediana * 2, "zone_id": zone_with_stats, "dormitorios_bucket": bucket},
    ).json()
    assert above["nivel"] == "above"

    in_range = client.post(
        "/market/classify",
        json={"precio": mediana, "zone_id": zone_with_stats, "dormitorios_bucket": bucket},
    ).json()
    assert in_range["nivel"] == "in"


def test_classify_unknown_zone_404(client: TestClient) -> None:
    resp = client.post(
        "/market/classify",
        json={"precio": 20000, "zone_id": "no-existe", "dormitorios_bucket": "1"},
    )
    assert resp.status_code == 404


def test_variacion_interanual_nunca_sale_del_historico_sembrado(client: TestClient) -> None:
    """El histórico sembrado es inventado (random.Random(777) en
    memory/seed.py). Publicarlo como variación interanual daba cifras como
    "Pocitos 1 dormitorio +25,5%", indistinguibles de un dato real -- estaba
    así en producción el 2026-11-02. Mientras no haya doce meses de snapshots
    de verdad, el campo va vacío.

    Se recorren todas las zonas sembradas, no una: la combinación que tenía
    histórico dependía de cuántos avisos en memoria caían en cada bucket, y
    fijar una sola acá haría que el test pase por no encontrar nada.
    """
    zonas = [z["id"] for z in client.get("/zones").json()]
    assert zonas, "sin zonas no se prueba nada"

    for zone_id in zonas:
        for stat in client.get("/market/stats", params={"zone_id": zone_id}).json():
            assert stat["variacion_interanual_pct"] is None, (
                f"{zone_id}/{stat['dormitorios_bucket']} publica "
                f"{stat['variacion_interanual_pct']}% calculado sobre histórico inventado"
            )
