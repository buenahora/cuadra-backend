from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.catalog import Amenity, Garantia, Zone
from app.schemas.common import Amueblado, EstadoComercial, EstadoPublicacion, NivelMercado


class Photo(BaseModel):
    id: UUID
    url: str
    orden: int

    model_config = {"from_attributes": True}


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class PolygonSearch(BaseModel):
    """Zona dibujada a mano (S1B) -- polígono ad-hoc, no persistido como
    `Zone` (data-model.md §5). Requiere >= 3 vértices."""

    polygon: list[LatLng] = Field(min_length=3)
    dormitorios_bucket: str | None = None
    precio_min: float | None = None
    precio_max: float | None = None


class ListingCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str = Field(max_length=500)
    direccion: str = Field(min_length=1)
    barrio_id: str
    entre_calles: str | None = None
    ocultar_direccion: bool = False
    dormitorios: int = Field(ge=0, le=8)
    banos: int = Field(ge=1, le=6)
    metraje_m2: int = Field(gt=0)
    piso: int | None = None
    planta_baja: bool = False
    amueblado: Amueblado = Amueblado.no
    permite_mascotas: bool = False
    amenity_ids: list[str] = []
    expensas_incluidas: bool = False
    expensas_monto: float | None = None
    precio: float = Field(gt=0)
    precio_negociable: bool = False
    garantia_ids: list[str] = []
    fotos: list[str] = Field(min_length=3, max_length=10)
    disponible_desde: date
    disponible_hasta: date | None = None
    owner_contact_nombre: str | None = None


class ListingUpdate(BaseModel):
    """Todos los campos opcionales -- PATCH parcial. Incluye los dos
    estados separados que resuelven la inconsistencia 2F/3B
    (data-model.md §3)."""

    titulo: str | None = None
    descripcion: str | None = None
    precio: float | None = None
    precio_negociable: bool | None = None
    estado_publicacion: EstadoPublicacion | None = None
    estado_comercial: EstadoComercial | None = None
    lease_vencimiento: date | None = None
    disponible_hasta: date | None = None
    fotos: list[str] | None = None
    amenity_ids: list[str] | None = None
    garantia_ids: list[str] | None = None


class MarketPosition(BaseModel):
    nivel: NivelMercado | None
    diferencia_pct: float | None
    precio_mediana: float | None
    muestra_confiable: bool


class ListingSummary(BaseModel):
    """Forma liviana para resultados de búsqueda / tarjetas (AdCard en el
    front: price, level, zone, beds, area, img)."""

    id: UUID
    titulo: str
    precio: float
    dormitorios: int
    banos: int
    metraje_m2: int
    barrio: str
    zone_id: str
    # None para avisos scrapeados -- ninguna fuente externa trae
    # coordenadas hoy (ver cuadra-data/dbt/models/marts/listings_unified.sql).
    lat: float | None
    lng: float | None
    foto_portada: str | None
    estado_publicacion: EstadoPublicacion
    estado_comercial: EstadoComercial
    market_position: MarketPosition | None = None
    creado_en: datetime
    # None = publicado en Cuadra; si no, nombre de la fuente externa
    # ("infocasas"/"casasweb"/"buscandocasa") -- ver conversación 2026-08-15.
    fuente_datos: str | None = None


class ListingOut(BaseModel):
    id: UUID
    titulo: str
    descripcion: str
    direccion: str
    ocultar_direccion: bool
    zone: Zone
    entre_calles: str | None
    lat: float | None
    lng: float | None
    dormitorios: int
    banos: int
    metraje_m2: int
    piso: int | None
    planta_baja: bool
    amueblado: Amueblado
    permite_mascotas: bool
    amenities: list[Amenity]
    expensas_incluidas: bool
    expensas_monto: float | None
    precio: float
    precio_negociable: bool
    garantias: list[Garantia]
    fotos: list[Photo]
    disponible_desde: date
    disponible_hasta: date | None
    estado_publicacion: EstadoPublicacion
    estado_comercial: EstadoComercial
    # None para avisos scrapeados -- no los publicó ningún usuario de Cuadra.
    publicado_por: UUID | None
    owner_contact_nombre: str | None
    lease_vencimiento: date | None
    consultas_count: int
    creado_en: datetime
    actualizado_en: datetime
    market_position: MarketPosition | None = None
    fuente_datos: str | None = None


class UploadedPhoto(BaseModel):
    url: str
