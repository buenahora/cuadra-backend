"""Los repositorios operacionales contra un Postgres de verdad.

app/repositories/sql/ tiene un solo juego de clases para los dos motores,
así que el resto de la suite -- que corre sobre SQLite -- ya cubre la
lógica. Lo que no cubre es que el SQL sea realmente el dialecto común:
`ON CONFLICT DO NOTHING`, el marcador de parámetro que reescribe
`_a_estilo`, el acceso a las filas por nombre con pg8000 (que devuelve
tuplas, no sqlite3.Row) y leer rowcount antes de cerrar la conexión. Eso
solo lo prueba un Postgres.

Se saltea si no hay ninguno escuchando, así que no rompe el CI ni un clon
nuevo. Para correrlo:

    docker run -d --name cuadra-pg-test -e POSTGRES_PASSWORD=test \\
      -e POSTGRES_DB=alquileres -p 55432:5432 postgres:16-alpine
    uv run pytest tests/test_sql_postgres.py
"""

from __future__ import annotations

import os
import socket
import uuid
from datetime import date, datetime, timezone

import pytest

from app.core.config import settings
from app.repositories.models import ReportRow

PG = {
    "host": os.environ.get("CUADRA_TEST_PG_HOST", "127.0.0.1"),
    "port": int(os.environ.get("CUADRA_TEST_PG_PORT", "55432")),
    "dbname": os.environ.get("CUADRA_TEST_PG_DB", "alquileres"),
    "username": os.environ.get("CUADRA_TEST_PG_USER", "postgres"),
    "password": os.environ.get("CUADRA_TEST_PG_PASSWORD", "test"),
}


def _hay_postgres() -> bool:
    try:
        with socket.create_connection((PG["host"], PG["port"]), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _hay_postgres(),
    reason=f"sin Postgres en {PG['host']}:{PG['port']} -- ver el docstring del módulo",
)


@pytest.fixture
def pg(monkeypatch):
    """Apunta app/repositories/sql/ al Postgres de prueba y limpia las tablas.

    Se parchea `_credenciales_postgres` en vez de pasar por Secrets Manager:
    lo que importa probar es el SQL, no boto3.
    """
    from app.repositories.sql import connection

    monkeypatch.setattr(settings, "db_secret_arn", "arn:de-prueba")
    monkeypatch.setattr(settings, "db_ssl", False)
    monkeypatch.setattr(connection, "_credenciales_postgres", lambda: PG)

    assert connection.usa_postgres()
    connection.init_db()
    with connection.get_connection() as conn:
        for tabla in ("favorites", "inquiries", "reports", "users"):
            conn.execute(f"DELETE FROM {tabla}")
    return connection


def _repos():
    from app.repositories.sql.repo import (
        FavoritesRepositorySql,
        InquiriesRepositorySql,
        ReportsRepositorySql,
        UsersRepositorySql,
    )

    return (
        UsersRepositorySql(),
        FavoritesRepositorySql(),
        InquiriesRepositorySql(),
        ReportsRepositorySql(),
    )


def test_init_db_crea_las_tablas(pg):
    with pg.get_connection() as conn:
        nombres = {
            fila["table_name"]
            for fila in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
    assert {"users", "favorites", "inquiries", "reports"} <= nombres


def test_usuarios_ida_y_vuelta(pg):
    users, _, _, _ = _repos()
    creado = users.create(
        nombre_completo="Usuaria de Prueba",
        email="PG@cuadra.uy",
        telefono="099123456",
        password_hash="hash",
        es_corredor=True,
    )
    # El email se normaliza a minúsculas y es_corredor vuelve como bool, no
    # como el entero con que se guarda.
    assert creado.email == "pg@cuadra.uy"
    por_id = users.get_by_id(creado.id)
    assert por_id is not None
    assert por_id.es_corredor is True
    assert por_id.telefono == "099123456"
    assert users.get_by_email("pg@cuadra.uy") == por_id
    assert users.get_by_id(uuid.uuid4()) is None


def test_favorito_repetido_no_explota(pg):
    """El ON CONFLICT DO NOTHING que reemplazó al INSERT OR IGNORE de SQLite."""
    users, favoritos, _, _ = _repos()
    user = users.create("Fav", "fav@cuadra.uy", None, "hash")
    listing = uuid.uuid4()

    primero = favoritos.add(user.id, listing)
    repetido = favoritos.add(user.id, listing)
    assert primero.creado_en == repetido.creado_en
    assert len(favoritos.list_by_user(user.id)) == 1
    assert favoritos.is_favorite(user.id, listing)

    # rowcount: True la primera vez, False la segunda.
    assert favoritos.remove(user.id, listing) is True
    assert favoritos.remove(user.id, listing) is False
    assert favoritos.list_by_user(user.id) == []


def test_consultas_y_conteo(pg):
    users, _, consultas, _ = _repos()
    user = users.create("Cons", "cons@cuadra.uy", None, "hash")
    listing = uuid.uuid4()

    creada = consultas.create(
        listing,
        user.id,
        {
            "nombre": "Interesada",
            "email": "interesada@cuadra.uy",
            "telefono": None,
            "fecha_mudanza": date(2026, 12, 1),
            "mensaje": "¿Sigue disponible?",
        },
    )
    traida = consultas.get(creada.id)
    assert traida is not None
    assert traida.fecha_mudanza == date(2026, 12, 1)
    assert traida.respuesta is None
    assert traida.respondido_en is None

    respondida = consultas.respond(creada.id, "Sí, disponible.")
    assert respondida is not None
    assert respondida.respuesta == "Sí, disponible."
    assert respondida.respondido_en is not None

    assert [c.id for c in consultas.list_by_listing(listing)] == [creada.id]
    assert [c.id for c in consultas.list_by_user(user.id)] == [creada.id]

    from app.repositories.sql.repo import count_inquiries_by_listing

    assert count_inquiries_by_listing(listing) == 1
    assert count_inquiries_by_listing(uuid.uuid4()) == 0


def test_informes_guardan_las_secciones_como_json(pg):
    users, _, _, informes = _repos()
    user = users.create("Inf", "inf@cuadra.uy", None, "hash")
    row = ReportRow(
        id=uuid.uuid4(),
        generado_por=user.id,
        titulo="Informe de Pocitos",
        destinatario_nombre="Cliente",
        zone_id="pocitos",
        dormitorios_bucket="2",
        periodo="2026-10",
        secciones_incluidas=["resumen", "precios", "comparables"],
        pdf_url="/static/reports/x.pdf",
        generado_en=datetime.now(timezone.utc),
    )
    informes.create(row)
    traido = informes.get(row.id)
    assert traido is not None
    assert traido.secciones_incluidas == ["resumen", "precios", "comparables"]
    assert [r.id for r in informes.list_by_user(user.id)] == [row.id]
