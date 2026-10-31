"""Punto único de wiring entre routers y repositorios. Zonas y avisos ya
resuelven contra la data layer real (app/repositories/warehouse/,
2026-08-15) combinada con el store en memoria; usuarios, favoritos,
consultas e informes resuelven contra SQL (app/repositories/sql/,
2026-08-15 también -- son datos que no pueden perderse en cada restart,
a diferencia de catálogos/avisos sintéticos que se resiembran solos). Los
routers solo conocen los Protocols de app/repositories/base.py, nunca las
clases concretas -- así este es el único archivo que cambia cuando se
agrega o cambia una fuente de datos.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_access_token
from app.repositories.base import (
    FavoritesRepository,
    InquiriesRepository,
    ListingsRepository,
    ReportsRepository,
    UsersRepository,
    ZonesRepository,
)
from app.repositories.memory.repo import (
    CatalogRepositoryMemory,
    ListingsRepositoryMemory,
    MarketSnapshotsRepositoryMemory,
    ZonesRepositoryMemory,
)
from app.repositories.memory.seed import seed_all
from app.repositories.memory.store import store
from app.repositories.models import UserRow
from app.repositories.sql.connection import init_db, usa_postgres
from app.repositories.sql.repo import (
    FavoritesRepositorySql,
    InquiriesRepositorySql,
    ReportsRepositorySql,
    UsersRepositorySql,
)
from app.repositories.sql.gold import GoldZonesRepository, filas_de_market_listings
from app.repositories.warehouse.listings_source import (
    ListingsRepositoryBlended,
    filas_del_warehouse,
)
from app.repositories.warehouse.zones_repo import WarehouseZonesRepository

init_db()
seed_all()

_users_repo: UsersRepository = UsersRepositorySql()
# De dónde salen los avisos scrapeados y el catálogo de zonas depende del
# entorno, no del código de las rutas:
#
#   AWS      -> las tablas gold que el job de Glue construye en Postgres
#               (market_listings, zonas). Ver app/repositories/sql/gold.py.
#   local    -> el warehouse DuckDB que arma dbt en cuadra-data, como siempre.
#
# En los dos casos el catálogo en memoria es el fallback: sin zonas, los avisos
# del seed quedan con un zone_id sin ZoneRow y las rutas que hacen
# zones[listing.zone_id] fallan con KeyError.
_zonas_de_memoria = ZonesRepositoryMemory(store)
if usa_postgres():
    _zones_repo: ZonesRepository = GoldZonesRepository(fallback=_zonas_de_memoria)
    _cargar_scraped = filas_de_market_listings
else:
    _zones_repo = WarehouseZonesRepository(fallback=_zonas_de_memoria)
    _cargar_scraped = filas_del_warehouse

_catalog_repo = CatalogRepositoryMemory(store)
_listings_repo: ListingsRepository = ListingsRepositoryBlended(
    ListingsRepositoryMemory(store), cargar_filas=_cargar_scraped
)
_market_snapshots_repo = MarketSnapshotsRepositoryMemory(store)
_inquiries_repo: InquiriesRepository = InquiriesRepositorySql()
_favorites_repo: FavoritesRepository = FavoritesRepositorySql()
_reports_repo: ReportsRepository = ReportsRepositorySql()


def get_users_repo() -> UsersRepository:
    return _users_repo


def get_zones_repo() -> ZonesRepository:
    return _zones_repo


def get_catalog_repo() -> CatalogRepositoryMemory:
    return _catalog_repo


def get_listings_repo() -> ListingsRepository:
    return _listings_repo


def get_market_snapshots_repo() -> MarketSnapshotsRepositoryMemory:
    return _market_snapshots_repo


def get_inquiries_repo() -> InquiriesRepository:
    return _inquiries_repo


def get_favorites_repo() -> FavoritesRepository:
    return _favorites_repo


def get_reports_repo() -> ReportsRepository:
    return _reports_repo


_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="No se pudo validar la credencial",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str | None = Depends(_oauth2_scheme),
    users_repo: UsersRepository = Depends(get_users_repo),
) -> UserRow:
    if token is None:
        raise _credentials_exception
    user_id = decode_access_token(token)
    if user_id is None:
        raise _credentials_exception
    user = users_repo.get_by_id(user_id)
    if user is None:
        raise _credentials_exception
    return user


def get_current_user_optional(
    token: str | None = Depends(_oauth2_scheme),
    users_repo: UsersRepository = Depends(get_users_repo),
) -> UserRow | None:
    if token is None:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    return users_repo.get_by_id(user_id)
