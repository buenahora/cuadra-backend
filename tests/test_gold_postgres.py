"""La lectura de las tablas gold de Postgres (app/repositories/sql/gold.py).

Es el camino que corre en AWS: el job de Glue de cuadra-data deja
market_listings y zonas en Postgres, y el backend lee de ahí en vez del
warehouse DuckDB. Lo que se verifica acá es el contrato de columnas (orden
incluido, porque _row_to_listing desempaqueta por posición), el mapeo a
ListingRow y que la API degrade -- no explote -- cuando las tablas todavía
no existen, que es el estado del día del deploy, antes de la primera corrida
del pipeline.

El esquema se crea acá y no se importa de cuadra-data a propósito: son repos
independientes que se despliegan por separado, así que cada lado prueba su
mitad del contrato. El del otro lado está en
cuadra-data/tests/integration/test_gold_postgres.py.

Se saltea si no hay Postgres escuchando. Para correrlo:

    docker run -d --name cuadra-pg-test -e POSTGRES_PASSWORD=test \\
      -e POSTGRES_DB=alquileres -p 55432:5432 postgres:16-alpine
    uv run pytest tests/test_gold_postgres.py
"""

from __future__ import annotations

import os
import socket
from datetime import date, datetime

import pytest

from app.core.config import settings
from app.repositories.base import ListingFilter

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

# Mismas columnas y tipos que deja el job de Glue (GOLD_SQL en
# cuadra-data/glue/transform.py). Solo las que lee el backend.
_DDL = """
CREATE TABLE market_listings (
    listing_id text, fuente_datos text, barrio text, subbarrio text,
    zone_id text, direccion text, latitud double precision,
    longitud double precision, operacion text, tipo_propiedad text,
    dormitorios integer, dormitorios_bucket text, banos integer,
    metraje_m2 integer, precio numeric(12,0), estado text,
    es_activo boolean, publicado_en date, descripcion text,
    amenities text[], fotos text[], foto_count integer,
    ingestado_en timestamp
)
"""


@pytest.fixture
def gold(monkeypatch):
    from app.repositories.sql import connection
    from app.repositories.sql import gold as modulo_gold

    monkeypatch.setattr(settings, "db_secret_arn", "arn:de-prueba")
    monkeypatch.setattr(settings, "db_ssl", False)
    monkeypatch.setattr(connection, "_credenciales_postgres", lambda: PG)
    # El aviso de "no pude leer" se emite una vez por proceso; se limpia para
    # que cada test parta de cero.
    modulo_gold._ya_avisado.clear()

    with connection.get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS market_listings CASCADE")
        conn.execute("DROP TABLE IF EXISTS zonas CASCADE")
        conn.execute(_DDL)
        conn.execute("CREATE TABLE zonas (zone_id text, barrio text, ciudad text)")
        conn.execute(
            "INSERT INTO market_listings VALUES"
            " ('IC100','infocasas','Pocitos','Pocitos','pocitos','Calle 1',"
            "  -34.91,-56.15,'alquiler','apartamento',2,'2',1,70,30000,'activo',"
            "  true,%s,'Lindo',ARRAY['Ascensor','GYM'],ARRAY['a.jpg','b.jpg'],2,%s)",
            (date(2026, 10, 1), datetime(2026, 10, 15, 6, 0, 0)),
        )
        conn.execute(
            "INSERT INTO zonas VALUES ('pocitos','Pocitos','Montevideo')"
        )
    return modulo_gold


def test_lee_y_mapea_un_aviso(gold):
    from app.repositories.warehouse.listings_source import _row_to_listing

    filas = gold.filas_de_market_listings()
    assert len(filas) == 1
    aviso = _row_to_listing(filas[0])

    assert aviso.zone_id == "pocitos"
    assert aviso.precio == 30000.0
    assert aviso.dormitorios == 2
    assert aviso.banos == 1
    assert aviso.metraje_m2 == 70
    assert aviso.titulo == "2 dormitorios en Pocitos"
    assert [f.url for f in aviso.fotos] == ["a.jpg", "b.jpg"]
    # Los nombres de InfoCasas se mapean al catálogo propio de Cuadra.
    assert aviso.amenity_ids == ["ascensor", "gimnasio"]
    assert aviso.estado_publicacion == "activo"
    assert aviso.fuente_datos == "infocasas"
    # Un aviso scrapeado no tiene dueño: por eso no se puede editar por API.
    assert aviso.publicado_por is None


def test_el_id_del_aviso_es_estable_entre_corridas(gold):
    """Favoritos y consultas sobre un aviso scrapeado tienen que sobrevivir a
    que el pipeline reconstruya la tabla."""
    from app.repositories.warehouse.listings_source import _row_to_listing

    primero = _row_to_listing(gold.filas_de_market_listings()[0])
    segundo = _row_to_listing(gold.filas_de_market_listings()[0])
    assert primero.id == segundo.id


def test_zonas_desde_postgres(gold):
    repo = gold.GoldZonesRepository()
    zonas = repo.list_all()
    assert [(z.id, z.nombre, z.ciudad) for z in zonas] == [
        ("pocitos", "Pocitos", "Montevideo")
    ]
    assert repo.get("pocitos") is not None
    assert repo.get("no_existe") is None


def test_el_blended_mezcla_postgres_con_los_avisos_de_cuadra(gold):
    from app.repositories.memory.repo import ListingsRepositoryMemory
    from app.repositories.memory.store import store
    from app.repositories.warehouse.listings_source import ListingsRepositoryBlended

    repo = ListingsRepositoryBlended(
        ListingsRepositoryMemory(store), cargar_filas=gold.filas_de_market_listings
    )
    avisos, total = repo.search(ListingFilter(zone_ids=["pocitos"], page_size=100))
    fuentes = {a.fuente_datos for a in avisos}
    assert "infocasas" in fuentes, "el aviso de Postgres tiene que aparecer"
    assert total >= 1


def test_sin_las_tablas_degrada_en_vez_de_explotar(gold, capsys):
    """El día del deploy las tablas no existen todavía: la API tiene que
    seguir sirviendo los avisos de Cuadra, no caerse."""
    from app.repositories.sql.connection import get_connection

    with get_connection() as conn:
        conn.execute("DROP TABLE market_listings CASCADE")
        conn.execute("DROP TABLE zonas CASCADE")
    gold._ya_avisado.clear()

    assert gold.filas_de_market_listings() == []
    assert "no se pudo leer market_listings" in capsys.readouterr().err


def test_sin_tabla_zonas_usa_el_fallback(gold):
    from app.repositories.memory.repo import ZonesRepositoryMemory
    from app.repositories.memory.store import store
    from app.repositories.sql.connection import get_connection

    with get_connection() as conn:
        conn.execute("DROP TABLE zonas CASCADE")
    gold._ya_avisado.clear()

    repo = gold.GoldZonesRepository(fallback=ZonesRepositoryMemory(store))
    assert len(repo.list_all()) > 0, "cae al catálogo sembrado, no a lista vacía"
