"""ZonesRepository respaldado por el warehouse de data_layer -- reemplaza
la lista fija de 15 barrios sembrada en memoria (ver
app/repositories/memory/seed.py, que ya quedó desactualizada el
2026-08-15 cuando data_layer sumó ~30 barrios más a
dbt/seeds/seed_barrios.csv) por el catálogo real: esa curaduría, más
cualquier zone_id que aparezca en avisos reales (listings_unified) pero
todavía no esté curado ahí -- para que ningún aviso scrapeado quede con
un zone_id sin ZoneRow correspondiente (evita KeyError en las rutas que
hacen zones[listing.zone_id], ver app/api/routes/listings.py).

Cachea en memoria de proceso tras la primera consulta -- se refresca con
un restart, igual que el resto del store hoy (ver
app/repositories/memory/store.py). No hace falta más que eso todavía.
"""

from __future__ import annotations

from app.repositories.models import ZoneRow
from app.repositories.warehouse.connection import get_warehouse_connection

_ZONES_QUERY = """
    with combined as (
        select zone_id, barrio, ciudad, 1 as prioridad
        from main.seed_barrios
        union all
        -- Zonas reales sin curar todavía en seed_barrios -- prioridad más
        -- baja: si algún día se cura esa zona, seed_barrios gana.
        select zone_id, barrio, 'Montevideo' as ciudad, 2 as prioridad
        from main.listings_unified
    ),
    ranked as (
        select
            zone_id, barrio, ciudad,
            row_number() over (partition by zone_id order by prioridad, barrio) as rn
        from combined
    )
    select zone_id, barrio, ciudad from ranked where rn = 1
"""


class WarehouseZonesRepository:
    def __init__(self) -> None:
        self._zones: dict[str, ZoneRow] | None = None

    def _load(self) -> dict[str, ZoneRow]:
        if self._zones is not None:
            return self._zones
        con = get_warehouse_connection()
        if con is None:
            self._zones = {}
            return self._zones
        rows = con.execute(_ZONES_QUERY).fetchall()
        self._zones = {
            zone_id: ZoneRow(id=zone_id, nombre=barrio, ciudad=ciudad)
            for zone_id, barrio, ciudad in rows
        }
        return self._zones

    def list_all(self) -> list[ZoneRow]:
        return list(self._load().values())

    def get(self, zone_id: str) -> ZoneRow | None:
        return self._load().get(zone_id)
