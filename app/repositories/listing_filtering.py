"""Filtrado/orden/paginación de avisos -- extraído de
app/repositories/memory/repo.py (2026-08-15) para que
ListingsRepositoryMemory y el nuevo repositorio combinado con la data
layer (app/repositories/warehouse/) apliquen exactamente la misma lógica
sobre listas de ListingRow, sin importar de dónde salió cada fila.
"""

from __future__ import annotations

from app.repositories.base import ListingFilter
from app.repositories.models import ListingRow
from app.services.geo import haversine_distance_m, point_in_polygon


def filter_and_sort_listings(
    listings: list[ListingRow], filters: ListingFilter
) -> tuple[list[ListingRow], int]:
    results = listings

    if filters.estado_publicacion:
        results = [l for l in results if l.estado_publicacion == filters.estado_publicacion]
    if filters.estado_comercial:
        results = [l for l in results if l.estado_comercial == filters.estado_comercial]
    if filters.publicado_por:
        results = [l for l in results if l.publicado_por == filters.publicado_por]
    if filters.q:
        needle = filters.q.lower()
        results = [
            l for l in results
            if needle in l.titulo.lower() or needle in l.direccion.lower()
        ]
    if filters.zone_ids:
        zone_set = set(filters.zone_ids)
        results = [l for l in results if l.zone_id in zone_set]
    if filters.dormitorios is not None:
        results = [l for l in results if l.dormitorios == filters.dormitorios]
    if filters.precio_min is not None:
        results = [l for l in results if l.precio >= filters.precio_min]
    if filters.precio_max is not None:
        results = [l for l in results if l.precio <= filters.precio_max]
    if filters.metraje_min is not None:
        results = [l for l in results if l.metraje_m2 >= filters.metraje_min]
    if filters.metraje_max is not None:
        results = [l for l in results if l.metraje_m2 <= filters.metraje_max]
    if filters.permite_mascotas is not None:
        results = [l for l in results if l.permite_mascotas == filters.permite_mascotas]
    if filters.amenity_ids:
        wanted = set(filters.amenity_ids)
        results = [l for l in results if wanted.issubset(set(l.amenity_ids))]
    if filters.garantia_ids:
        wanted = set(filters.garantia_ids)
        results = [l for l in results if wanted.issubset(set(l.garantia_ids))]
    if filters.center and filters.radio_m:
        lat0, lng0 = filters.center
        results = [
            l for l in results
            # Avisos scrapeados no tienen lat/lng (ver ListingRow) -- no se
            # puede saber si caen en el radio, se excluyen en vez de
            # reventar el cálculo o asumir que sí/no entran.
            if l.lat is not None and l.lng is not None
            and haversine_distance_m(lat0, lng0, l.lat, l.lng) <= filters.radio_m
        ]
    if filters.polygon:
        results = [
            l for l in results
            if l.lat is not None and l.lng is not None
            and point_in_polygon(l.lat, l.lng, filters.polygon)
        ]

    if filters.sort == "precio_asc":
        results = sorted(results, key=lambda l: l.precio)
    elif filters.sort == "precio_desc":
        results = sorted(results, key=lambda l: l.precio, reverse=True)
    else:
        results = sorted(results, key=lambda l: l.creado_en, reverse=True)

    total = len(results)
    start = (filters.page - 1) * filters.page_size
    end = start + filters.page_size
    return results[start:end], total
