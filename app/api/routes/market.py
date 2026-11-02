from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_listings_repo, get_market_snapshots_repo, get_zones_repo
from app.repositories.base import ListingsRepository, ZonesRepository
from app.repositories.memory.repo import MarketSnapshotsRepositoryMemory
from app.schemas.common import DormitoriosBucket
from app.schemas.market import ClassifyRequest, ClassifyResult, MarketSnapshot, MarketStat
from app.services import market as market_service

router = APIRouter(prefix="/market", tags=["market"])


def _yoy_pct(
    zone_id: str,
    bucket: str,
    current_median: float | None,
    snapshots_repo: MarketSnapshotsRepositoryMemory,
) -> float | None:
    if current_median is None:
        return None
    # El histórico sembrado es inventado (random.Random(777) en
    # memory/seed.py: la mediana de hoy dividida por un factor al azar y
    # después una deriva al alza). Publicarlo como variación interanual daba
    # cifras como "Pocitos 1 dormitorio +25,5%" indistinguibles de un dato
    # real. Mientras no haya doce meses de snapshots de verdad, este campo va
    # vacío: el front ya sabe mostrar None como "sin datos suficientes".
    history = [
        s for s in snapshots_repo.list_seed_history(zone_id, bucket)
        if s.fuente != "historico_semilla"
    ]
    if not history:
        return None
    oldest = history[0]  # ya viene ordenado por periodo ascendente
    if oldest.precio_mediana == 0:
        return None
    return round((current_median - oldest.precio_mediana) / oldest.precio_mediana * 100, 1)


@router.get("/stats", response_model=list[MarketStat])
def get_market_stats(
    zone_id: str | None = None,
    dormitorios_bucket: DormitoriosBucket | None = None,
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
    snapshots_repo: MarketSnapshotsRepositoryMemory = Depends(get_market_snapshots_repo),
) -> list[MarketStat]:
    """Min/mediana/máximo/tamaño de muestra por zona+tipología
    (cuadra-data/docs/data-model.md §8). Sin filtros, devuelve todas las
    combinaciones con al menos un aviso activo -- útil para pintar el mapa
    de calor de S2A/S3A. Combinaciones sin ningún aviso simplemente no
    aparecen: no se inventa una mediana sin datos."""
    stats = market_service.compute_stats(
        listings_repo.list_active(),
        zone_id=zone_id,
        dormitorios_bucket=dormitorios_bucket.value if dormitorios_bucket else None,
    )
    zones = {z.id: z.nombre for z in zones_repo.list_all()}
    return [
        MarketStat(
            zone_id=s.zone_id,
            barrio=zones.get(s.zone_id, s.zone_id),
            dormitorios_bucket=s.dormitorios_bucket,
            precio_min=s.precio_min,
            precio_q1=s.precio_q1,
            precio_mediana=s.precio_mediana,
            precio_q3=s.precio_q3,
            precio_max=s.precio_max,
            avisos_activos=s.avisos_activos,
            muestra_confiable=s.muestra_confiable,
            variacion_interanual_pct=_yoy_pct(s.zone_id, s.dormitorios_bucket, s.precio_mediana, snapshots_repo),
            actualizado_en=date.today(),
        )
        for s in stats
    ]


@router.get("/snapshots", response_model=list[MarketSnapshot])
def get_market_snapshots(
    zone_id: str,
    dormitorios_bucket: DormitoriosBucket,
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    snapshots_repo: MarketSnapshotsRepositoryMemory = Depends(get_market_snapshots_repo),
) -> list[MarketSnapshot]:
    """Serie histórica mensual para el gráfico de tendencia de 12 meses
    (S2A/S3A). Combina histórico sembrado + el punto de este mes calculado
    en vivo -- misma unión que `market_snapshots.sql` en la data layer."""
    bucket = dormitorios_bucket.value
    history = snapshots_repo.list_seed_history(zone_id, bucket)
    result = [
        MarketSnapshot(
            zone_id=r.zone_id,
            dormitorios_bucket=r.dormitorios_bucket,
            periodo=r.periodo,
            precio_mediana=r.precio_mediana,
            fuente=r.fuente,
        )
        for r in history
    ]
    current = market_service.compute_stats(listings_repo.list_active(), zone_id, bucket)
    if current and current[0].muestra_confiable:
        result.append(
            MarketSnapshot(
                zone_id=zone_id,
                dormitorios_bucket=bucket,
                periodo=date.today().replace(day=1),
                precio_mediana=current[0].precio_mediana,
                fuente="calculado",
            )
        )
    return result


@router.post("/classify", response_model=ClassifyResult)
def classify_price(
    payload: ClassifyRequest,
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
) -> ClassifyResult:
    """below/in/above para un precio propuesto (S2D, feedback en vivo del
    wizard de precio) -- mismo servicio que usa el detalle de aviso y la
    consulta de mercado, ver cuadra-data/docs/market-intelligence.md §6."""
    if zones_repo.get(payload.zone_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Zona '{payload.zone_id}' no existe")
    stats = market_service.compute_stats(
        listings_repo.list_active(), payload.zone_id, payload.dormitorios_bucket.value
    )
    if not stats:
        return ClassifyResult(
            nivel=None, diferencia_pct=None, precio_mediana=None,
            muestra_confiable=False, avisos_activos=0,
        )
    s = stats[0]
    nivel, diferencia_pct = market_service.classify(payload.precio, s.precio_mediana)
    return ClassifyResult(
        nivel=nivel if s.muestra_confiable else None,
        diferencia_pct=diferencia_pct if s.muestra_confiable else None,
        precio_mediana=s.precio_mediana,
        muestra_confiable=s.muestra_confiable,
        avisos_activos=s.avisos_activos,
    )
