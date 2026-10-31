"""Utilidades geoespaciales puras en Python -- suficiente para el volumen
en memoria de hoy. El contrato (ListingFilter.center/radio_m/polygon en
app/repositories/base.py) es el mismo que usaría una implementación real
con PostGIS (`ST_DWithin` / `ST_Within`, ver
cuadra-data/docs/data-model.md §5) -- migrar es cambiar el repositorio, no
la forma en que el resto de la API pide "avisos cerca de un punto" o
"avisos dentro de este polígono".
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def point_in_polygon(lat: float, lng: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray casting estándar. `polygon` es una lista de (lat, lng); no
    hace falta cerrarlo (el último punto no necesita repetir el primero)."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        lat_i, lng_i = polygon[i]
        lat_j, lng_j = polygon[j]
        intersects = ((lng_i > lng) != (lng_j > lng)) and (
            lat < (lat_j - lat_i) * (lng - lng_i) / (lng_j - lng_i + 1e-15) + lat_i
        )
        if intersects:
            inside = not inside
        j = i
    return inside
