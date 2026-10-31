import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status

from app.api.deps import (
    get_catalog_repo,
    get_current_user,
    get_listings_repo,
    get_zones_repo,
)
from app.core.config import settings
from app.repositories.base import ListingFilter, ListingsRepository, ZonesRepository
from app.repositories.memory.repo import CatalogRepositoryMemory
from app.repositories.models import ListingRow, PhotoRow, UserRow
from app.schemas.catalog import Zone
from app.schemas.common import EstadoComercial, EstadoPublicacion, Page, SortOrder
from app.schemas.listing import (
    ListingCreate,
    ListingOut,
    ListingSummary,
    ListingUpdate,
    PolygonSearch,
    UploadedPhoto,
)
from app.services import listing_view

router = APIRouter(tags=["listings"])


def _require_owner(listing: ListingRow, current_user: UserRow) -> None:
    if listing.publicado_por != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No sos el publicador de este aviso")


def _get_listing_or_404(listing_id: uuid.UUID, repo: ListingsRepository) -> ListingRow:
    listing = repo.get(listing_id)
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aviso no encontrado")
    return listing


def _zone_or_404(zone_id: str, zones_repo: ZonesRepository) -> Zone:
    zone = zones_repo.get(zone_id)
    if zone is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Zona '{zone_id}' no existe")
    return Zone.model_validate(zone)


def _build_detail(
    listing: ListingRow,
    zones_repo: ZonesRepository,
    catalog_repo: CatalogRepositoryMemory,
    listings_repo: ListingsRepository,
) -> ListingOut:
    zone = Zone.model_validate(zones_repo.get(listing.zone_id))
    all_amenities = {a.id: a for a in catalog_repo.list_amenities()}
    all_garantias = {g.id: g for g in catalog_repo.list_garantias()}
    amenities = [all_amenities[a] for a in listing.amenity_ids if a in all_amenities]
    garantias = [all_garantias[g] for g in listing.garantia_ids if g in all_garantias]
    index = listing_view.build_market_index(listings_repo)
    return listing_view.to_detail(
        listing,
        zone,
        amenities,
        garantias,
        listings_repo.count_inquiries(listing.id),
        index,
    )


@router.get("/listings", response_model=Page[ListingSummary])
def search_listings(
    q: str | None = None,
    zone_id: list[str] | None = Query(default=None),
    dormitorios: int | None = None,
    precio_min: float | None = None,
    precio_max: float | None = None,
    metraje_min: int | None = None,
    metraje_max: int | None = None,
    amenity_id: list[str] | None = Query(default=None),
    garantia_id: list[str] | None = Query(default=None),
    permite_mascotas: bool | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radio_m: float | None = None,
    sort: SortOrder = SortOrder.recientes,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
) -> Page[ListingSummary]:
    center = (lat, lng) if lat is not None and lng is not None else None
    filters = ListingFilter(
        q=q,
        zone_ids=zone_id,
        dormitorios=dormitorios,
        precio_min=precio_min,
        precio_max=precio_max,
        metraje_min=metraje_min,
        metraje_max=metraje_max,
        amenity_ids=amenity_id,
        garantia_ids=garantia_id,
        permite_mascotas=permite_mascotas,
        center=center,
        radio_m=radio_m,
        sort=sort.value,
        page=page,
        page_size=page_size,
    )
    rows, total = listings_repo.search(filters)
    index = listing_view.build_market_index(listings_repo)
    zones = {z.id: Zone.model_validate(z) for z in zones_repo.list_all()}
    items = [listing_view.to_summary(r, zones[r.zone_id], index) for r in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/listings/search", response_model=Page[ListingSummary])
def search_listings_by_polygon(
    payload: PolygonSearch,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
) -> Page[ListingSummary]:
    """Zona dibujada a mano (S1B) -- polígono ad-hoc, no una `Zone`
    persistida (ver cuadra-data/docs/data-model.md §5)."""
    filters = ListingFilter(
        dormitorios=int(payload.dormitorios_bucket) if payload.dormitorios_bucket and payload.dormitorios_bucket != "3+" else None,
        precio_min=payload.precio_min,
        precio_max=payload.precio_max,
        polygon=[(p.lat, p.lng) for p in payload.polygon],
        page=page,
        page_size=page_size,
    )
    rows, total = listings_repo.search(filters)
    index = listing_view.build_market_index(listings_repo)
    zones = {z.id: Zone.model_validate(z) for z in zones_repo.list_all()}
    items = [listing_view.to_summary(r, zones[r.zone_id], index) for r in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/listings/{listing_id}", response_model=ListingOut)
def get_listing(
    listing_id: uuid.UUID,
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
    catalog_repo: CatalogRepositoryMemory = Depends(get_catalog_repo),
) -> ListingOut:
    listing = _get_listing_or_404(listing_id, listings_repo)
    return _build_detail(listing, zones_repo, catalog_repo, listings_repo)


@router.post("/listings", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
def create_listing(
    payload: ListingCreate,
    current_user: UserRow = Depends(get_current_user),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
    catalog_repo: CatalogRepositoryMemory = Depends(get_catalog_repo),
) -> ListingOut:
    _zone_or_404(payload.barrio_id, zones_repo)
    listing = listings_repo.create(current_user.id, payload.model_dump())
    return _build_detail(listing, zones_repo, catalog_repo, listings_repo)


@router.patch("/listings/{listing_id}", response_model=ListingOut)
def update_listing(
    listing_id: uuid.UUID,
    payload: ListingUpdate,
    current_user: UserRow = Depends(get_current_user),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
    catalog_repo: CatalogRepositoryMemory = Depends(get_catalog_repo),
) -> ListingOut:
    listing = _get_listing_or_404(listing_id, listings_repo)
    _require_owner(listing, current_user)
    updated = listings_repo.update(
        listing_id, payload.model_dump(exclude_unset=True, exclude_none=True)
    )
    return _build_detail(updated, zones_repo, catalog_repo, listings_repo)


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_listing(
    listing_id: uuid.UUID,
    current_user: UserRow = Depends(get_current_user),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
) -> None:
    """Soft-delete: pasa a `archivado`. No se borra la fila -- conserva
    historial de consultas/favoritos asociados."""
    listing = _get_listing_or_404(listing_id, listings_repo)
    _require_owner(listing, current_user)
    listings_repo.update(listing_id, {"estado_publicacion": EstadoPublicacion.archivado.value})


@router.get("/users/me/listings", response_model=list[ListingSummary])
def my_listings(
    estado_comercial: EstadoComercial | None = None,
    estado_publicacion: EstadoPublicacion | None = None,
    current_user: UserRow = Depends(get_current_user),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
) -> list[ListingSummary]:
    """'Mis publicaciones' (propietario, S2F) o 'Mi cartera' (corredor,
    S3B) -- misma fuente, filtrada por estado comercial en el front."""
    filters = ListingFilter(
        publicado_por=current_user.id,
        estado_publicacion=estado_publicacion.value if estado_publicacion else None,
        estado_comercial=estado_comercial.value if estado_comercial else None,
        page=1,
        page_size=500,
    )
    rows, _ = listings_repo.search(filters)
    index = listing_view.build_market_index(listings_repo)
    zones = {z.id: Zone.model_validate(z) for z in zones_repo.list_all()}
    return [listing_view.to_summary(r, zones[r.zone_id], index) for r in rows]


@router.post("/listings/{listing_id}/photos", response_model=ListingOut)
def add_listing_photos(
    listing_id: uuid.UUID,
    files: list[UploadFile],
    current_user: UserRow = Depends(get_current_user),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
    catalog_repo: CatalogRepositoryMemory = Depends(get_catalog_repo),
) -> ListingOut:
    listing = _get_listing_or_404(listing_id, listings_repo)
    _require_owner(listing, current_user)
    if len(listing.fotos) + len(files) > 10:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Máximo 10 fotos por aviso")
    new_photos = [PhotoRow(id=uuid.uuid4(), url=_save_upload(f), orden=0) for f in files]
    updated = listings_repo.add_photos(listing_id, new_photos)
    return _build_detail(updated, zones_repo, catalog_repo, listings_repo)


@router.post("/uploads/photos", response_model=UploadedPhoto, status_code=status.HTTP_201_CREATED)
def upload_photo(file: UploadFile) -> UploadedPhoto:
    """Sube una foto suelta antes de tener un aviso creado (S2E del
    wizard sube fotos antes de publicar). Devuelve la URL para incluir en
    `ListingCreate.fotos`."""
    return UploadedPhoto(url=_save_upload(file))


def _save_upload(file: UploadFile) -> str:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    destination = upload_dir / filename
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return f"/static/uploads/{filename}"
