"""Ensambla las respuestas de la API (ListingSummary/ListingOut) a partir
de las filas de dominio + el índice de mercado. Vive separado de los
routers para que tanto `/listings` como `/users/me/favorites` (o
cualquier otro endpoint que devuelva avisos) construyan la misma forma de
salida, con el mismo cálculo de `market_position`, sin duplicar lógica.
"""

from __future__ import annotations

from app.repositories.base import ListingsRepository, ZonesRepository
from app.repositories.models import ListingRow
from app.schemas.catalog import Zone
from app.schemas.listing import ListingOut, ListingSummary, MarketPosition, Photo
from app.services import market as market_service

MarketIndex = dict[tuple[str, str], market_service.ZoneDormsStats]


def build_market_index(listings_repo: ListingsRepository) -> MarketIndex:
    stats = market_service.compute_stats(listings_repo.list_active())
    return {(s.zone_id, s.dormitorios_bucket): s for s in stats}


def _market_position(listing: ListingRow, index: MarketIndex) -> MarketPosition | None:
    stats = index.get((listing.zone_id, listing.dormitorios_bucket))
    if stats is None:
        return None
    nivel, diferencia_pct = market_service.classify(listing.precio, stats.precio_mediana)
    return MarketPosition(
        nivel=nivel,
        diferencia_pct=diferencia_pct,
        precio_mediana=stats.precio_mediana,
        muestra_confiable=stats.muestra_confiable,
    )


def to_summary(listing: ListingRow, zone: Zone, market_index: MarketIndex) -> ListingSummary:
    portada = min(listing.fotos, key=lambda p: p.orden).url if listing.fotos else None
    return ListingSummary(
        id=listing.id,
        titulo=listing.titulo,
        precio=listing.precio,
        dormitorios=listing.dormitorios,
        banos=listing.banos,
        metraje_m2=listing.metraje_m2,
        barrio=zone.nombre,
        zone_id=zone.id,
        lat=listing.lat,
        lng=listing.lng,
        foto_portada=portada,
        estado_publicacion=listing.estado_publicacion,
        estado_comercial=listing.estado_comercial,
        market_position=_market_position(listing, market_index),
        creado_en=listing.creado_en,
        fuente_datos=listing.fuente_datos,
    )


def to_detail(
    listing: ListingRow,
    zone: Zone,
    amenities: list,
    garantias: list,
    consultas_count: int,
    market_index: MarketIndex,
) -> ListingOut:
    return ListingOut(
        id=listing.id,
        titulo=listing.titulo,
        descripcion=listing.descripcion,
        direccion=listing.direccion,
        ocultar_direccion=listing.ocultar_direccion,
        zone=zone,
        entre_calles=listing.entre_calles,
        lat=listing.lat,
        lng=listing.lng,
        dormitorios=listing.dormitorios,
        banos=listing.banos,
        metraje_m2=listing.metraje_m2,
        piso=listing.piso,
        planta_baja=listing.planta_baja,
        amueblado=listing.amueblado,
        permite_mascotas=listing.permite_mascotas,
        amenities=amenities,
        expensas_incluidas=listing.expensas_incluidas,
        expensas_monto=listing.expensas_monto,
        precio=listing.precio,
        precio_negociable=listing.precio_negociable,
        garantias=garantias,
        fotos=[Photo.model_validate(p) for p in sorted(listing.fotos, key=lambda p: p.orden)],
        disponible_desde=listing.disponible_desde,
        disponible_hasta=listing.disponible_hasta,
        estado_publicacion=listing.estado_publicacion,
        estado_comercial=listing.estado_comercial,
        publicado_por=listing.publicado_por,
        owner_contact_nombre=listing.owner_contact_nombre,
        lease_vencimiento=listing.lease_vencimiento,
        consultas_count=consultas_count,
        creado_en=listing.creado_en,
        actualizado_en=listing.actualizado_en,
        market_position=_market_position(listing, market_index),
        fuente_datos=listing.fuente_datos,
    )
