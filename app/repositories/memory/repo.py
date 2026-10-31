from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.repositories.base import ListingFilter
from app.repositories.listing_filtering import filter_and_sort_listings
from app.repositories.memory.store import InMemoryStore
from app.repositories.models import (
    CatalogItemRow,
    ListingRow,
    MarketSnapshotRow,
    PhotoRow,
    ZoneRow,
)
from app.repositories.sqlite.repo import count_inquiries_by_listing


class ZonesRepositoryMemory:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def list_all(self) -> list[ZoneRow]:
        return sorted(self._store.zones.values(), key=lambda z: z.nombre)

    def get(self, zone_id: str) -> ZoneRow | None:
        return self._store.zones.get(zone_id)


class CatalogRepositoryMemory:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def list_amenities(self) -> list[CatalogItemRow]:
        return list(self._store.amenities.values())

    def list_garantias(self) -> list[CatalogItemRow]:
        return list(self._store.garantias.values())


class ListingsRepositoryMemory:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def list_all(self) -> list[ListingRow]:
        """No es parte del Protocol ListingsRepository -- lo usa
        ListingsRepositoryBlended (app/repositories/warehouse/listings_source.py)
        para mezclar avisos de Cuadra con avisos scrapeados sin acceder a
        `_store` directamente."""
        return list(self._store.listings.values())

    def create(self, publicado_por: UUID, data: dict) -> ListingRow:
        now = datetime.now(timezone.utc)
        fotos = [
            PhotoRow(id=uuid4(), url=url, orden=i) for i, url in enumerate(data.pop("fotos"))
        ]
        listing = ListingRow(
            id=uuid4(),
            zone_id=data.pop("barrio_id"),
            fotos=fotos,
            estado_publicacion="activo",
            estado_comercial="disponible",
            publicado_por=publicado_por,
            lease_vencimiento=None,
            creado_en=now,
            actualizado_en=now,
            # geocoding real pendiente (roadmap Fase 1) -- placeholder
            # determinístico centrado en Montevideo hasta integrarlo.
            lat=-34.9083,
            lng=-56.1670,
            **data,
        )
        self._store.listings[listing.id] = listing
        return listing

    def get(self, listing_id: UUID) -> ListingRow | None:
        return self._store.listings.get(listing_id)

    def update(self, listing_id: UUID, data: dict) -> ListingRow | None:
        listing = self._store.listings.get(listing_id)
        if listing is None:
            return None
        for key, value in data.items():
            if value is None:
                continue
            if key == "fotos":
                listing.fotos = [
                    PhotoRow(id=uuid4(), url=url, orden=i) for i, url in enumerate(value)
                ]
                continue
            setattr(listing, key, value)
        listing.actualizado_en = datetime.now(timezone.utc)
        return listing

    def delete(self, listing_id: UUID) -> bool:
        return self._store.listings.pop(listing_id, None) is not None

    def add_photos(self, listing_id: UUID, photos: list[PhotoRow]) -> ListingRow | None:
        listing = self._store.listings.get(listing_id)
        if listing is None:
            return None
        offset = len(listing.fotos)
        for i, photo in enumerate(photos):
            photo.orden = offset + i
        listing.fotos.extend(photos)
        listing.actualizado_en = datetime.now(timezone.utc)
        return listing

    def list_active(self) -> list[ListingRow]:
        return [l for l in self._store.listings.values() if l.estado_publicacion == "activo"]

    def count_inquiries(self, listing_id: UUID) -> int:
        return count_inquiries_by_listing(listing_id)

    def search(self, filters: ListingFilter) -> tuple[list[ListingRow], int]:
        return filter_and_sort_listings(list(self._store.listings.values()), filters)


class MarketSnapshotsRepositoryMemory:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def list_seed_history(
        self, zone_id: str | None, dormitorios_bucket: str | None
    ) -> list[MarketSnapshotRow]:
        rows = self._store.market_history_seed
        if zone_id:
            rows = [r for r in rows if r.zone_id == zone_id]
        if dormitorios_bucket:
            rows = [r for r in rows if r.dormitorios_bucket == dormitorios_bucket]
        return sorted(rows, key=lambda r: r.periodo)
