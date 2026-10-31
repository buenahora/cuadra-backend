"""Motor de inteligencia de mercado -- la pieza diferencial del producto
(ver cuadra-data/docs/market-intelligence.md). Reimplementa en Python,
sobre los avisos activos en memoria, exactamente la misma lógica que los
marts dbt (`market_stats.sql`, `listing_market_position.sql`): mismo
agrupamiento (zona+dormitorios), mismo umbral configurable below/in/above,
mismo criterio de `muestra_confiable`. Cuando la data layer real esté
poblada, este servicio pasa a leer `market_stats`/`market_snapshots` en
vez de recalcular desde `store.listings` -- el contrato de salida
(MarketStat/ClassifyResult) no cambia.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from app.core.config import settings
from app.repositories.models import ListingRow
from app.schemas.common import NivelMercado


@dataclass
class ZoneDormsStats:
    zone_id: str
    dormitorios_bucket: str
    precio_min: int | None
    precio_q1: float | None
    precio_mediana: float | None
    precio_q3: float | None
    precio_max: int | None
    avisos_activos: int
    muestra_confiable: bool


def compute_stats(
    listings: list[ListingRow],
    zone_id: str | None = None,
    dormitorios_bucket: str | None = None,
) -> list[ZoneDormsStats]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for listing in listings:
        if listing.estado_publicacion != "activo":
            continue
        if zone_id and listing.zone_id != zone_id:
            continue
        if dormitorios_bucket and listing.dormitorios_bucket != dormitorios_bucket:
            continue
        grouped[(listing.zone_id, listing.dormitorios_bucket)].append(listing.precio)

    result: list[ZoneDormsStats] = []
    for (z_id, bucket), precios in grouped.items():
        confiable = len(precios) >= settings.market_min_sample_size
        # method="inclusive" -- estable con muestras chicas (a partir de
        # market_min_sample_size), a diferencia del default "exclusive".
        q1, q3 = (statistics.quantiles(precios, n=4, method="inclusive")[0::2] if confiable else (None, None))
        result.append(
            ZoneDormsStats(
                zone_id=z_id,
                dormitorios_bucket=bucket,
                precio_min=int(min(precios)) if confiable else None,
                precio_q1=q1,
                precio_mediana=statistics.median(precios) if confiable else None,
                precio_q3=q3,
                precio_max=int(max(precios)) if confiable else None,
                avisos_activos=len(precios),
                muestra_confiable=confiable,
            )
        )
    return result


def classify(precio: float, precio_mediana: float | None) -> tuple[NivelMercado | None, float | None]:
    """below/in/above -- mismo umbral que el prototipo (S2D) y
    `dbt/macros/market_level.sql`, expuesto como parámetro
    (`settings.market_threshold_pct`), no constante de código (ver
    cuadra-data/docs/market-intelligence.md §3)."""
    if precio_mediana is None or precio_mediana == 0:
        return None, None
    diferencia_pct = round(abs(precio - precio_mediana) / precio_mediana * 100, 1)
    if precio < precio_mediana * (1 - settings.market_threshold_pct):
        return NivelMercado.below, diferencia_pct
    if precio > precio_mediana * (1 + settings.market_threshold_pct):
        return NivelMercado.above, diferencia_pct
    return NivelMercado.in_range, diferencia_pct
