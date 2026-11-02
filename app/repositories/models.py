"""Modelos de dominio (filas de "base de datos"). Independientes de los
schemas Pydantic de la API (app/schemas/) a propósito: los schemas son el
contrato HTTP, esto es la forma interna que un repositorio implementa,
sea en memoria (hoy) o contra cuadra-data/Postgres (mañana). Los routers
nunca deberían importar estas dataclasses directamente para responder --
siempre pasan por un schema de salida.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID


@dataclass
class UserRow:
    id: UUID
    nombre_completo: str
    email: str
    telefono: str | None
    # None para quien entró por Cognito: nunca hubo contraseña nuestra.
    password_hash: str | None
    es_corredor: bool
    google_id: str | None
    cognito_sub: str | None
    creado_en: datetime


@dataclass
class ZoneRow:
    id: str
    nombre: str
    ciudad: str


@dataclass
class CatalogItemRow:
    id: str
    nombre: str


@dataclass
class PhotoRow:
    id: UUID
    url: str
    orden: int


@dataclass(kw_only=True)
class ListingRow:
    """kw_only=True a propósito (2026-08-15, ver conversación sobre unificar
    avisos publicados en Cuadra y avisos scrapeados en una sola entidad):
    todo el código existente ya construye ListingRow por keyword, así que
    esto no rompe nada, y libera de la restricción de orden de dataclass
    para poder agregar campos opcionales (lat/lng/publicado_por, que un
    aviso scrapeado no tiene) sin pelear con la posición del resto.
    """

    id: UUID
    titulo: str
    descripcion: str
    direccion: str
    zone_id: str
    entre_calles: str | None
    ocultar_direccion: bool
    # None para avisos scrapeados -- ninguna fuente externa trae coordenadas
    # hoy (ver cuadra-data/dbt/models/marts/listings_unified.sql).
    lat: float | None
    lng: float | None
    dormitorios: int
    banos: int
    metraje_m2: int
    piso: int | None
    planta_baja: bool
    amueblado: str
    permite_mascotas: bool
    amenity_ids: list[str]
    expensas_incluidas: bool
    expensas_monto: float | None
    precio: float
    precio_negociable: bool
    garantia_ids: list[str]
    fotos: list[PhotoRow]
    disponible_desde: date
    disponible_hasta: date | None
    estado_publicacion: str
    estado_comercial: str
    # None para avisos scrapeados -- no los publicó ningún usuario de Cuadra.
    publicado_por: UUID | None
    owner_contact_nombre: str | None
    lease_vencimiento: date | None
    creado_en: datetime
    actualizado_en: datetime
    # None = publicado en Cuadra; si no, nombre de la fuente externa
    # ("infocasas"/"casasweb"/"buscandocasa", ver
    # cuadra-data/etl/extract/scrape_*.py) -- ver conversación 2026-08-15:
    # la idea es no distinguir avisos por endpoint/schema, solo por este
    # campo, para que el front pueda decidir qué mostrar (ej. "aviso
    # externo, puede no estar disponible") sin que la API tenga dos formas
    # de avisos distintas.
    fuente_datos: str | None = None

    @property
    def dormitorios_bucket(self) -> str:
        return "3+" if self.dormitorios >= 3 else str(self.dormitorios)


@dataclass
class InquiryRow:
    id: UUID
    listing_id: UUID
    remitente_user_id: UUID
    nombre: str
    email: str
    telefono: str | None
    fecha_mudanza: date | None
    mensaje: str
    respuesta: str | None
    creado_en: datetime
    respondido_en: datetime | None


@dataclass
class FavoriteRow:
    user_id: UUID
    listing_id: UUID
    creado_en: datetime


@dataclass
class MarketSnapshotRow:
    zone_id: str
    dormitorios_bucket: str
    periodo: date
    precio_mediana: float
    fuente: str = "historico_semilla"


@dataclass
class ReportRow:
    id: UUID
    generado_por: UUID
    titulo: str
    destinatario_nombre: str
    zone_id: str
    dormitorios_bucket: str
    periodo: str
    secciones_incluidas: list[str]
    pdf_url: str
    generado_en: datetime
