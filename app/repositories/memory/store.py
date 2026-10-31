"""Store en memoria: un dict por 'tabla'. Vive mientras el proceso vive --
se resetea en cada restart. Es a propósito la implementación más simple
posible del contrato (app/repositories/base.py) para poder construir y
probar la API ya, sin esperar a que la data layer real esté poblada.

Usuarios, favoritos, consultas e informes ya NO viven acá -- se movieron a
SQLite (app/repositories/sqlite/, 2026-08-15) porque son datos que no
pueden perderse en cada restart. Lo que queda acá es todo lo que se
resiembra igual en cada arranque (catálogos, avisos sintéticos, histórico
de mercado semilla) y no pierde nada al no persistir.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.models import (
    CatalogItemRow,
    ListingRow,
    MarketSnapshotRow,
    ZoneRow,
)


class InMemoryStore:
    def __init__(self) -> None:
        self.zones: dict[str, ZoneRow] = {}
        self.amenities: dict[str, CatalogItemRow] = {}
        self.garantias: dict[str, CatalogItemRow] = {}
        self.listings: dict[UUID, ListingRow] = {}
        self.market_history_seed: list[MarketSnapshotRow] = []


store = InMemoryStore()
