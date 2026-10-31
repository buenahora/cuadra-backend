"""Lectura de las tablas gold que el pipeline de datos deja en Postgres.

Son las mismas que el proyecto dbt de cuadra-data construye en el warehouse
DuckDB (market_listings, y el catálogo de zonas), pero construidas por el job
de Glue en SQL de Postgres -- dbt no corre en AWS, ver el comentario de
GOLD_SQL en cuadra-data/glue/transform.py.

Esto es el equivalente de app/repositories/warehouse/ para el entorno
desplegado. El mapeo de fila a ListingRow no se duplica: las dos fuentes
devuelven las mismas columnas en el mismo orden (COLUMNAS_LISTINGS) y
ListingsRepositoryBlended recibe la función de carga por constructor.

Tolera que las tablas no existan. El backend se despliega antes de que el
pipeline haya corrido una sola vez, así que al principio no están -- y una
excepción acá tumbaría la API entera en vez de dejarla servir los avisos
publicados en Cuadra. Mismo criterio que
app/repositories/warehouse/connection.py con el archivo DuckDB ausente: se
avisa una vez y se devuelve vacío.
"""

from __future__ import annotations

import sys

from app.repositories.models import ZoneRow
from app.repositories.sql.connection import get_connection
from app.repositories.warehouse.listings_source import COLUMNAS_LISTINGS

_LISTINGS_QUERY = f"""
    select {COLUMNAS_LISTINGS}
    from market_listings
    where precio is not null
"""

_ZONAS_QUERY = "select zone_id, barrio, ciudad from zonas"

_ya_avisado: set[str] = set()


def _consultar(sql: str, tabla: str) -> list[tuple]:
    try:
        with get_connection() as conn:
            filas = conn.execute(sql).fetchall()
    except Exception as e:  # noqa: BLE001 -- tabla ausente o base no lista: degrada
        if tabla not in _ya_avisado:
            _ya_avisado.add(tabla)
            print(
                f"!! no se pudo leer {tabla} de Postgres: {e} -- la API sirve solo "
                f"avisos publicados en Cuadra hasta que el pipeline de datos corra.",
                file=sys.stderr,
            )
        return []
    # get_connection devuelve filas como dicts; _row_to_listing y el
    # repositorio de zonas esperan tuplas en el orden del select.
    return [tuple(f.values()) for f in filas]


def filas_de_market_listings() -> list[tuple]:
    return _consultar(_LISTINGS_QUERY, "market_listings")


class GoldZonesRepository:
    """ZonesRepository respaldado por la tabla `zonas` de Postgres.

    Mismo contrato y mismo fallback que WarehouseZonesRepository: si no hay
    zonas, los avisos del seed quedarían con un zone_id sin ZoneRow y las
    rutas que hacen zones[listing.zone_id] fallarían con KeyError.
    """

    def __init__(self, fallback=None) -> None:
        self._zones: dict[str, ZoneRow] | None = None
        self._fallback = fallback

    def _load(self) -> dict[str, ZoneRow]:
        if self._zones is not None:
            return self._zones
        filas = _consultar(_ZONAS_QUERY, "zonas")
        if not filas:
            self._zones = (
                {z.id: z for z in self._fallback.list_all()} if self._fallback else {}
            )
            return self._zones
        self._zones = {
            zone_id: ZoneRow(id=zone_id, nombre=barrio, ciudad=ciudad)
            for zone_id, barrio, ciudad in filas
        }
        return self._zones

    def list_all(self) -> list[ZoneRow]:
        return list(self._load().values())

    def get(self, zone_id: str) -> ZoneRow | None:
        return self._load().get(zone_id)
