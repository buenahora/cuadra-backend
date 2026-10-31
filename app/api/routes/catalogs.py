from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_catalog_repo, get_listings_repo, get_zones_repo
from app.repositories.base import ListingsRepository, ZonesRepository
from app.repositories.memory.repo import CatalogRepositoryMemory
from app.schemas.catalog import Amenity, Garantia, Zone
from app.services import market as market_service

router = APIRouter(tags=["catalogs"])


@router.get("/zones", response_model=list[Zone])
def list_zones(
    zones_repo: ZonesRepository = Depends(get_zones_repo),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
) -> list[Zone]:
    """Catálogo de barrios. `tiene_estadisticas` se calcula en vivo (¿hay
    al menos una combinación zona+dormitorios con muestra confiable?), no
    es un flag manual -- reemplaza la lista hardcodeada de 6/15 barrios
    del prototipo (cuadra-data/docs/data-model.md §5). `cantidad_avisos`
    alimenta el autocomplete de la barra de búsqueda por zona (S1A)."""
    activos = listings_repo.list_active()
    stats = market_service.compute_stats(activos)
    zones_con_datos = {s.zone_id for s in stats if s.muestra_confiable}
    cantidad_por_zona = Counter(l.zone_id for l in activos)
    return [
        Zone(
            id=z.id,
            nombre=z.nombre,
            ciudad=z.ciudad,
            tiene_estadisticas=z.id in zones_con_datos,
            cantidad_avisos=cantidad_por_zona.get(z.id, 0),
        )
        for z in zones_repo.list_all()
    ]


@router.get("/zones/{zone_id}", response_model=Zone)
def get_zone(
    zone_id: str,
    zones_repo: ZonesRepository = Depends(get_zones_repo),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
) -> Zone:
    zone = zones_repo.get(zone_id)
    if zone is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zona no encontrada")
    activos = listings_repo.list_active()
    stats = market_service.compute_stats(activos, zone_id=zone_id)
    tiene_estadisticas = any(s.muestra_confiable for s in stats)
    cantidad_avisos = sum(1 for l in activos if l.zone_id == zone_id)
    return Zone(
        id=zone.id,
        nombre=zone.nombre,
        ciudad=zone.ciudad,
        tiene_estadisticas=tiene_estadisticas,
        cantidad_avisos=cantidad_avisos,
    )


@router.get("/amenities", response_model=list[Amenity])
def list_amenities(catalog_repo: CatalogRepositoryMemory = Depends(get_catalog_repo)) -> list[Amenity]:
    return [Amenity.model_validate(a) for a in catalog_repo.list_amenities()]


@router.get("/garantias", response_model=list[Garantia])
def list_garantias(catalog_repo: CatalogRepositoryMemory = Depends(get_catalog_repo)) -> list[Garantia]:
    return [Garantia.model_validate(g) for g in catalog_repo.list_garantias()]
