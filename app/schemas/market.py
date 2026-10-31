from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import DormitoriosBucket, MetrajeBucket, NivelMercado


class MarketStat(BaseModel):
    """Estadística vigente por zona+tipología (data-model.md §8). Nace
    directo del mart dbt `market_stats` -- misma forma, para que el día que
    esto lea de la data layer real en vez del store en memoria sea un
    cambio de repositorio, no de contrato."""

    zone_id: str
    barrio: str
    dormitorios_bucket: DormitoriosBucket
    metraje_bucket: MetrajeBucket | None = None
    precio_min: int | None = None
    precio_q1: float | None = None
    precio_mediana: float | None = None
    precio_q3: float | None = None
    precio_max: int | None = None
    avisos_activos: int
    muestra_confiable: bool
    variacion_interanual_pct: float | None = None
    actualizado_en: date

    model_config = {"from_attributes": True}


class MarketSnapshot(BaseModel):
    """Punto mensual de la serie histórica (data-model.md §8). `fuente`
    distingue histórico sembrado de cálculo real -- ver
    docs/market-intelligence.md §4 (arranque en frío)."""

    zone_id: str
    dormitorios_bucket: DormitoriosBucket
    periodo: date
    precio_mediana: float
    fuente: str = "calculado"

    model_config = {"from_attributes": True}


class ClassifyRequest(BaseModel):
    precio: float = Field(gt=0)
    zone_id: str
    dormitorios_bucket: DormitoriosBucket


class ClassifyResult(BaseModel):
    """Salida del servicio de clasificación (market-intelligence.md §6),
    reusada en el detalle de aviso (S1C), la consulta de mercado (S2A) y el
    feedback en vivo del wizard de precio (S2D)."""

    nivel: NivelMercado | None
    diferencia_pct: float | None
    precio_mediana: float | None
    muestra_confiable: bool
    avisos_activos: int
