"""Contratos de repositorio (Protocols). Cada uno se implementa hoy en
memoria (app/repositories/memory/) mientras la data layer real
(dbt/DuckDB -> eventualmente Postgres operacional, ver
cuadra-data/docs/roadmap.md Fase 1) se termina de poblar en paralelo.
Cambiar de motor de datos es escribir una clase nueva que cumpla estos
Protocols e inyectarla en app/api/deps.py -- los routers no cambian.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from app.repositories.models import (
    CatalogItemRow,
    FavoriteRow,
    InquiryRow,
    ListingRow,
    MarketSnapshotRow,
    PhotoRow,
    ReportRow,
    UserRow,
    ZoneRow,
)


class UsersRepository(Protocol):
    def create(
        self,
        nombre_completo: str,
        email: str,
        telefono: str | None,
        password_hash: str | None,
        es_corredor: bool = False,
        cognito_sub: str | None = None,
    ) -> UserRow: ...

    def get_by_id(self, user_id: UUID) -> UserRow | None: ...

    def get_by_email(self, email: str) -> UserRow | None: ...

    def get_by_cognito_sub(self, cognito_sub: str) -> UserRow | None: ...

    def vincular_cognito(self, user_id: UUID, cognito_sub: str) -> None: ...


class ZonesRepository(Protocol):
    def list_all(self) -> list[ZoneRow]: ...

    def get(self, zone_id: str) -> ZoneRow | None: ...


class CatalogRepository(Protocol):
    def list_amenities(self) -> list[CatalogItemRow]: ...

    def list_garantias(self) -> list[CatalogItemRow]: ...


@dataclass
class ListingFilter:
    q: str | None = None
    zone_ids: list[str] | None = None
    dormitorios: int | None = None
    precio_min: float | None = None
    precio_max: float | None = None
    metraje_min: int | None = None
    metraje_max: int | None = None
    amenity_ids: list[str] | None = None
    garantia_ids: list[str] | None = None
    permite_mascotas: bool | None = None
    estado_publicacion: str | None = "activo"
    publicado_por: UUID | None = None
    estado_comercial: str | None = None
    center: tuple[float, float] | None = None  # (lat, lng)
    radio_m: float | None = None
    polygon: list[tuple[float, float]] | None = None
    sort: str = "recientes"
    page: int = 1
    page_size: int = 20


class ListingsRepository(Protocol):
    def create(self, publicado_por: UUID, data: dict) -> ListingRow: ...

    def get(self, listing_id: UUID) -> ListingRow | None: ...

    def update(self, listing_id: UUID, data: dict) -> ListingRow | None: ...

    def delete(self, listing_id: UUID) -> bool: ...

    def search(self, filters: ListingFilter) -> tuple[list[ListingRow], int]: ...

    def list_active(self) -> list[ListingRow]: ...

    def add_photos(self, listing_id: UUID, photos: list[PhotoRow]) -> ListingRow | None: ...

    def count_inquiries(self, listing_id: UUID) -> int: ...


class MarketSnapshotsRepository(Protocol):
    def list_seed_history(
        self, zone_id: str | None, dormitorios_bucket: str | None
    ) -> list[MarketSnapshotRow]: ...


class InquiriesRepository(Protocol):
    def create(
        self, listing_id: UUID, remitente_user_id: UUID, data: dict
    ) -> InquiryRow: ...

    def get(self, inquiry_id: UUID) -> InquiryRow | None: ...

    def list_by_listing(self, listing_id: UUID) -> list[InquiryRow]: ...

    def list_by_user(self, user_id: UUID) -> list[InquiryRow]: ...

    def respond(self, inquiry_id: UUID, respuesta: str) -> InquiryRow | None: ...


class FavoritesRepository(Protocol):
    def add(self, user_id: UUID, listing_id: UUID) -> FavoriteRow: ...

    def remove(self, user_id: UUID, listing_id: UUID) -> bool: ...

    def list_by_user(self, user_id: UUID) -> list[FavoriteRow]: ...

    def is_favorite(self, user_id: UUID, listing_id: UUID) -> bool: ...


class ReportsRepository(Protocol):
    def create(self, row: ReportRow) -> ReportRow: ...

    def get(self, report_id: UUID) -> ReportRow | None: ...

    def list_by_user(self, user_id: UUID) -> list[ReportRow]: ...
