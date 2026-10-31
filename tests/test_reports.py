from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings


def test_generate_report_pdf(
    client: TestClient, auth_headers: dict[str, str], zone_with_stats: str
) -> None:
    stats = client.get("/market/stats", params={"zone_id": zone_with_stats}).json()
    bucket = next(s["dormitorios_bucket"] for s in stats if s["muestra_confiable"])

    create = client.post(
        "/reports",
        json={
            "titulo": f"Valuación {zone_with_stats} · {bucket} dorm",
            "destinatario_nombre": "C. Suárez",
            "zone_id": zone_with_stats,
            "dormitorios_bucket": bucket,
            "periodo": "12m",
            "secciones_incluidas": [
                "precio_mediano", "rango_de_precios", "evolucion_historica", "avisos_comparables",
            ],
        },
        headers=auth_headers,
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["pdf_url"].startswith("/static/reports/")

    pdf_path = Path(settings.reports_dir) / f"{body['id']}.pdf"
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0

    fetched = client.get(f"/reports/{body['id']}", headers=auth_headers)
    assert fetched.status_code == 200

    mine = client.get("/users/me/reports", headers=auth_headers)
    assert any(r["id"] == body["id"] for r in mine.json())


def test_get_report_requires_owner(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/reports/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404
