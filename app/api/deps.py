"""Punto único de wiring entre routers y repositorios. Zonas y avisos ya
resuelven contra la data layer real (app/repositories/warehouse/,
2026-08-15) combinada con el store en memoria; usuarios, favoritos,
consultas e informes resuelven contra SQL (app/repositories/sql/,
2026-08-15 también -- son datos que no pueden perderse en cada restart,
a diferencia de los catálogos, que se resiembran solos; los avisos
sintéticos del seed ya no se cargan en AWS, ver seed_all más abajo). Los
routers solo conocen los Protocols de app/repositories/base.py, nunca las
clases concretas -- así este es el único archivo que cambia cuando se
agrega o cambia una fuente de datos.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core import cognito
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
# En AWS (Postgres) los avisos y el histórico salen de las tablas gold: el
# seed solo aporta zonas de fallback y catálogos. Sembrar los avisos
# sintéticos ahí los publicaba en la API real y contaminaba las medianas.
seed_all(datos_sinteticos=not usa_postgres())

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


def _usuario_de_cognito(token: str, users_repo: UsersRepository) -> UserRow | None:
    """Resuelve el ID token de Cognito a una fila de `users`, creándola la
    primera vez que la persona entra.

    El pool es la autoridad de identidad: acá no se valida contraseña ni se
    confirma email, solo se guarda a quién corresponde cada `sub` para poder
    colgarle favoritos, consultas e informes.

    Se busca primero por `sub` y después por email, en ese orden. Al revés,
    alguien que cambia su email en Google se convertiría en un usuario nuevo
    y perdería todo lo suyo. El rescate por email existe para el caso
    contrario: una cuenta vieja con contraseña que entra por Google por
    primera vez -- sin eso el INSERT chocaría contra el UNIQUE de email.
    """
    claims = cognito.verificar_id_token(token)
    if claims is None:
        return None
    sub = claims.get("sub")
    if not sub:
        return None

    user = users_repo.get_by_cognito_sub(sub)
    if user is not None:
        return user

    email = (claims.get("email") or "").lower()
    if not email:
        # Sin email no hay cómo identificar ni contactar a la persona. El pool
        # pide email como nombre de usuario, así que esto no debería pasar.
        return None

    existente = users_repo.get_by_email(email)
    if existente is not None:
        users_repo.vincular_cognito(existente.id, sub)
        return users_repo.get_by_id(existente.id)

    return users_repo.create(
        nombre_completo=claims.get("name") or email.split("@")[0],
        email=email,
        telefono=None,
        password_hash=None,  # la contraseña, si existe, vive en Cognito
        cognito_sub=sub,
    )


def _resolver_usuario(token: str, users_repo: UsersRepository) -> UserRow | None:
    """Un solo lugar donde se decide qué es un token válido.

    Con el pool configurado (AWS) se aceptan únicamente ID tokens de Cognito.
    No se cae al JWT propio como respaldo a propósito: dejar los dos caminos
    abiertos es dejar abierto el de las contraseñas viejas, que es
    justamente lo que se está retirando.
    """
    if cognito.esta_configurado():
        return _usuario_de_cognito(token, users_repo)
    user_id = decode_access_token(token)
    return users_repo.get_by_id(user_id) if user_id else None


def get_current_user(
    token: str | None = Depends(_oauth2_scheme),
    users_repo: UsersRepository = Depends(get_users_repo),
) -> UserRow:
    if token is None:
        raise _credentials_exception
    user = _resolver_usuario(token, users_repo)
    if user is None:
        raise _credentials_exception
    return user


def get_current_user_optional(
    token: str | None = Depends(_oauth2_scheme),
    users_repo: UsersRepository = Depends(get_users_repo),
) -> UserRow | None:
    if token is None:
        return None
    return _resolver_usuario(token, users_repo)
