"""ListingsRepository que combina avisos publicados en Cuadra (en memoria)
con avisos scrapeados de las 3 fuentes externas (mart dbt market_listings
de data_layer) -- ver conversación 2026-08-15: la idea del producto es no
distinguir origen para quien consulta la API, solo exponer `fuente_datos`
(None = Cuadra) para que el front decida qué mostrar si quiere.

Se lee de market_listings, no de listings_unified directo -- ya viene
filtrado a alquiler/apartamento/sin outliers de precio (ver
cuadra-data/dbt/models/marts/market_listings.sql), así que acá no hace
falta repetir esa lógica de negocio en Python.

create/update/delete/add_photos siguen aplicando solo a avisos de Cuadra
(decisión explícita, misma conversación): no tiene sentido editar un
aviso externo vía API, se actualiza solo con el próximo scrape. Un intento
de PATCH/DELETE sobre un listing_id scrapeado llega hasta _require_owner
en app/api/routes/listings.py y ahí da 403 (publicado_por=None nunca
coincide con un usuario real), no 404 -- semántica correcta: el aviso
existe, no se puede editar.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from app.repositories.base import ListingFilter
from app.repositories.listing_filtering import filter_and_sort_listings
from app.repositories.memory.repo import ListingsRepositoryMemory
from app.repositories.models import ListingRow, PhotoRow
from app.repositories.warehouse.connection import get_warehouse_connection

_LISTINGS_QUERY = """
    select listing_id, fuente_datos, barrio, zone_id, direccion, latitud,
           longitud, dormitorios, banos, metraje_m2, precio, estado,
           es_activo, publicado_en, descripcion, amenities, fotos,
           ingestado_en
    from main.market_listings
    where precio is not null
"""

# Mapea nombres de comodidades tal cual los publica InfoCasas (columna
# `amenities` de bronze, ver scrape_infocasas.py) a los amenity_id del
# catálogo propio de Cuadra (cuadra-data/dbt/seeds/seed_amenities.csv,
# hoy hardcodeado también en frontend/src/screens/grupo2/S2C.jsx). Mapeo
# explícito, no fuzzy-match: mejor perder una comodidad real (queda afuera,
# sin aparecer) que mostrar una que no corresponde. Armado 2026-08-20
# revisando los ~40 nombres más frecuentes en una corrida real -- nombres
# que no tienen equivalente claro en el catálogo (ej. "Se aceptan mascotas",
# "Internet", "Amueblada") quedan deliberadamente sin mapear.
_AMENITY_NAME_MAP = {
    "Ascensor": "ascensor",
    "Aire Acondicionado": "aire_acondicionado",
    "Piscina": "piscina",
    "GYM": "gimnasio",
    "Parrillero / Barbacoa": "parrillero",
    "Parrillero": "parrillero",
    "Barbacoa": "parrillero",
    "Balcón / Terraza": "balcon_terraza",
    "Balcón": "balcon_terraza",
    "Lavadero": "lavadero",
    "Lavandería": "lavadero",
    "Terraza Lavadero": "lavadero",
    "Cochera": "cochera",
    "Garaje": "cochera",
    "Placard en dormitorio": "placares",
    "Placard en cocina": "placares",
    "Calefacción Individual": "calefaccion",
    "Calefacción Central": "calefaccion",
}


def _map_amenity_ids(amenities: list[str] | None) -> list[str]:
    ids = {_AMENITY_NAME_MAP[name] for name in (amenities or []) if name in _AMENITY_NAME_MAP}
    return sorted(ids)

# estado en bronze mezcla dos dimensiones que el backend separa
# (estado_publicacion/estado_comercial -- ver cuadra-data/docs/data-model.md
# §3, la misma inconsistencia que ese doc ya señalaba). Casasweb/BuscandoCasa
# siempre informan "activo" (sin flag confiable de pausado/alquilada);
# InfoCasas es la única fuente con las 4 variantes reales.
_ESTADO_COMERCIAL = {"alquilada": "alquilada", "en_proceso": "en_proceso"}


def _listing_id_uuid(listing_id: str) -> UUID:
    """Determinístico -- el mismo listing_id externo (ej. "IC194073518")
    siempre mapea al mismo UUID entre corridas del warehouse, para que
    favoritos/consultas sobre un aviso scrapeado tengan sentido de una
    carga a otra."""
    return uuid5(NAMESPACE_URL, f"https://cuadra.uy/scraped-listings/{listing_id}")


def _titulo(dormitorios: int, barrio: str) -> str:
    # Misma fórmula que app/repositories/memory/seed.py para los avisos
    # sintéticos -- no inventar un criterio de título distinto acá.
    tipologia = "Monoambiente" if dormitorios == 0 else f"{dormitorios} dormitorios"
    return f"{tipologia} en {barrio}"


def _row_to_listing(row: tuple) -> ListingRow:
    (
        listing_id, fuente_datos, barrio, zone_id, direccion, latitud,
        longitud, dormitorios, banos, metraje_m2, precio, estado, es_activo,
        publicado_en, descripcion, amenities, fotos,
        ingestado_en,
    ) = row

    fotos_rows = [
        PhotoRow(id=uuid5(NAMESPACE_URL, f"{listing_id}:{i}"), url=url, orden=i)
        for i, url in enumerate(fotos or [])
    ]

    disponible_desde: date = publicado_en if publicado_en else ingestado_en.date()
    creado_en: datetime = (
        datetime.combine(publicado_en, datetime.min.time(), tzinfo=timezone.utc)
        if publicado_en
        else ingestado_en
    )

    return ListingRow(
        id=_listing_id_uuid(listing_id),
        titulo=_titulo(dormitorios, barrio),
        descripcion=descripcion or "",
        direccion=direccion or "",
        zone_id=zone_id,
        entre_calles=None,
        ocultar_direccion=False,
        lat=latitud,
        lng=longitud,
        dormitorios=dormitorios,
        # banos real solo para fuentes que lo scrapean (hoy: InfoCasas, ver
        # scrape_infocasas.py) -- 1 de fallback para el resto, mismo
        # placeholder que antes cuando no había ninguna señal real.
        banos=banos if banos is not None else 1,
        metraje_m2=metraje_m2 or 0,
        piso=None,
        planta_baja=False,
        amueblado="no",
        permite_mascotas=False,
        amenity_ids=_map_amenity_ids(amenities),
        expensas_incluidas=False,
        expensas_monto=None,
        precio=float(precio),
        precio_negociable=False,
        garantia_ids=[],
        fotos=fotos_rows,
        disponible_desde=disponible_desde,
        disponible_hasta=None,
        estado_publicacion="activo" if es_activo else "pausado",
        estado_comercial=_ESTADO_COMERCIAL.get(estado, "disponible"),
        publicado_por=None,
        owner_contact_nombre=None,
        lease_vencimiento=None,
        creado_en=creado_en,
        actualizado_en=ingestado_en,
        fuente_datos=fuente_datos,
    )


class ListingsRepositoryBlended:
    def __init__(self, memory_repo: ListingsRepositoryMemory) -> None:
        self._memory_repo = memory_repo
        self._scraped: dict[UUID, ListingRow] | None = None

    def _load_scraped(self) -> dict[UUID, ListingRow]:
        if self._scraped is not None:
            return self._scraped
        con = get_warehouse_connection()
        if con is None:
            self._scraped = {}
            return self._scraped
        rows = con.execute(_LISTINGS_QUERY).fetchall()
        listings = {}
        for row in rows:
            listing = _row_to_listing(row)
            listings[listing.id] = listing
        self._scraped = listings
        return self._scraped

    def _combined(self) -> list[ListingRow]:
        return self._memory_repo.list_all() + list(self._load_scraped().values())

    # -- solo lectura, mezcla las 2 fuentes --

    def get(self, listing_id: UUID) -> ListingRow | None:
        listing = self._memory_repo.get(listing_id)
        if listing is not None:
            return listing
        return self._load_scraped().get(listing_id)

    def search(self, filters: ListingFilter) -> tuple[list[ListingRow], int]:
        return filter_and_sort_listings(self._combined(), filters)

    def list_active(self) -> list[ListingRow]:
        return [l for l in self._combined() if l.estado_publicacion == "activo"]

    # -- escritura, solo avisos de Cuadra --

    def create(self, publicado_por: UUID, data: dict) -> ListingRow:
        return self._memory_repo.create(publicado_por, data)

    def update(self, listing_id: UUID, data: dict) -> ListingRow | None:
        return self._memory_repo.update(listing_id, data)

    def delete(self, listing_id: UUID) -> bool:
        return self._memory_repo.delete(listing_id)

    def add_photos(self, listing_id: UUID, photos: list[PhotoRow]) -> ListingRow | None:
        return self._memory_repo.add_photos(listing_id, photos)

    def count_inquiries(self, listing_id: UUID) -> int:
        return self._memory_repo.count_inquiries(listing_id)
