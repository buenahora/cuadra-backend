"""Datos semilla para el store en memoria.

Los catálogos (barrios, amenities, garantías) siguen exactamente las
listas relevadas del prototipo (cuadra-data/docs/data-model.md §4 y §5) y
los mismos ids que los seeds de dbt (cuadra-data/dbt/seeds/), para que
convivan sin fricción con la data layer real el día que se conecten.

Los avisos y el histórico de precios son **sintéticos, generados con
semilla fija** -- igual de "no reales" que
`etl/extract/generate_synthetic_listings.py` en data_layer, y con el mismo
propósito: tener algo con qué desarrollar y probar la API ya, sin esperar
al pipeline real. No usar estos números para ninguna decisión de negocio.
"""

from __future__ import annotations

import random
import statistics
import unicodedata
from datetime import date, datetime, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from app.repositories.memory.store import store
from app.repositories.models import (
    CatalogItemRow,
    ListingRow,
    MarketSnapshotRow,
    PhotoRow,
    ZoneRow,
)

SEED_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

BARRIOS = [
    "Pocitos", "Cordón", "Parque Rodó", "Punta Carretas", "La Blanqueada",
    "Tres Cruces", "Palermo", "Buceo", "Malvín", "Carrasco", "Centro",
    "Ciudad Vieja", "Prado", "Sayago", "Cerro",
]

# Zonas con volumen sembrado suficiente para pasar `min_sample_size` -- el
# resto del catálogo existe (se puede elegir al publicar) pero muestra
# "sin datos suficientes", igual que en el prototipo (data-model.md §5).
BARRIOS_CON_VOLUMEN = ["Pocitos", "Cordón", "Parque Rodó", "Punta Carretas", "La Blanqueada", "Tres Cruces"]

AMENITIES = [
    ("cochera", "Cochera / Garaje"),
    ("balcon_terraza", "Balcón / Terraza"),
    ("ascensor", "Ascensor"),
    ("aire_acondicionado", "Aire acondicionado"),
    ("placares_empotrados", "Placares empotrados"),
    ("parrillero", "Parrillero"),
    ("piscina", "Piscina"),
    ("gimnasio", "Gimnasio"),
    ("porteria_24hs", "Portería 24 hs"),
    ("calefaccion", "Calefacción"),
    ("lavadero", "Lavadero"),
    ("seguridad_camaras", "Seguridad / Cámaras"),
]

GARANTIAS = [
    ("anda", "ANDA"),
    ("porto_seguro", "Porto Seguro"),
    ("contaduria_bhu", "Garantía de Contaduría (BHU)"),
    ("propietaria", "Garantía propietaria"),
    ("deposito_efectivo", "Depósito en efectivo"),
]

# Centro aproximado de Montevideo -- offsets pequeños por barrio para que
# los puntos no queden todos superpuestos en el mapa. Coordenadas
# aproximadas, no geocoding real (pendiente, ver roadmap Fase 1).
MONTEVIDEO_CENTER = (-34.9083, -56.1670)
ZONE_OFFSETS: dict[str, tuple[float, float]] = {}


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return normalized.lower().replace(" ", "_").replace("/", "_").replace("__", "_").strip("_")


def _seed_zones() -> None:
    rng = random.Random(42)
    for barrio in BARRIOS:
        zone_id = slugify(barrio)
        store.zones[zone_id] = ZoneRow(id=zone_id, nombre=barrio, ciudad="Montevideo")
        ZONE_OFFSETS[zone_id] = (rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03))


def _seed_catalogs() -> None:
    for amenity_id, nombre in AMENITIES:
        store.amenities[amenity_id] = CatalogItemRow(id=amenity_id, nombre=nombre)
    for garantia_id, nombre in GARANTIAS:
        store.garantias[garantia_id] = CatalogItemRow(id=garantia_id, nombre=nombre)


# Mediana base aproximada por dormitorios en un barrio "promedio" -- solo
# para que la distribución sintética tenga forma realista, no es dato de
# mercado real. Se escala por zona con un multiplicador determinístico.
BASE_MEDIAN_BY_DORMS = {0: 15000, 1: 19000, 2: 27000, 3: 38000}
ZONE_MULTIPLIER = {
    "pocitos": 1.25, "cordon": 0.95, "parque_rodo": 1.05, "punta_carretas": 1.35,
    "la_blanqueada": 0.9, "tres_cruces": 0.85, "palermo": 1.0, "buceo": 1.1,
    "malvin": 1.05, "carrasco": 1.5, "centro": 0.9, "ciudad_vieja": 0.85,
    "prado": 0.95, "sayago": 0.7, "cerro": 0.65,
}


def _listing_id_for(seed_key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"cuadra-seed-listing:{seed_key}")


def _seed_listings() -> None:
    rng = random.Random(1234)
    now = datetime.now(timezone.utc)
    counts = {barrio: (9 if barrio in BARRIOS_CON_VOLUMEN else 2) for barrio in BARRIOS}

    for barrio, n in counts.items():
        zone_id = slugify(barrio)
        lat_off, lng_off = ZONE_OFFSETS[zone_id]
        multiplier = ZONE_MULTIPLIER.get(zone_id, 1.0)
        for i in range(n):
            dormitorios = rng.choices([0, 1, 2, 3], weights=[1, 4, 3, 1])[0]
            base = BASE_MEDIAN_BY_DORMS[dormitorios] * multiplier
            precio = round(base * rng.uniform(0.82, 1.22), -2)
            metraje = {0: 28, 1: 42, 2: 62, 3: 90}[dormitorios] + rng.randint(-8, 15)
            seed_key = f"{zone_id}-{i}"
            listing_id = _listing_id_for(seed_key)
            publicado_en = now - timedelta(days=rng.randint(1, 120))
            fotos = [
                PhotoRow(
                    id=uuid5(NAMESPACE_URL, f"cuadra-seed-photo:{seed_key}:{p}"),
                    url=f"https://picsum.photos/seed/cuadra-{seed_key}-{p}/800/600",
                    orden=p,
                )
                for p in range(rng.randint(3, 6))
            ]
            store.listings[listing_id] = ListingRow(
                id=listing_id,
                titulo=f"{'Monoambiente' if dormitorios == 0 else str(dormitorios) + ' dormitorios'} en {barrio}",
                descripcion=f"Aviso de ejemplo (dato sintético) en {barrio}. Reemplazar por avisos reales -- ver cuadra-data/docs/market-intelligence.md.",
                direccion=f"Calle {rng.randint(1000, 2500)}, {barrio}",
                zone_id=zone_id,
                entre_calles=None,
                ocultar_direccion=False,
                lat=MONTEVIDEO_CENTER[0] + lat_off + rng.uniform(-0.004, 0.004),
                lng=MONTEVIDEO_CENTER[1] + lng_off + rng.uniform(-0.004, 0.004),
                dormitorios=dormitorios,
                banos=max(1, dormitorios),
                metraje_m2=max(18, metraje),
                piso=rng.randint(0, 12),
                planta_baja=rng.random() < 0.15,
                amueblado=rng.choice(["si", "no", "parcial"]),
                permite_mascotas=rng.random() < 0.4,
                amenity_ids=[a for a, _ in AMENITIES if rng.random() < 0.3],
                expensas_incluidas=rng.random() < 0.5,
                expensas_monto=None if rng.random() < 0.5 else round(precio * 0.08, -2),
                precio=precio,
                precio_negociable=rng.random() < 0.3,
                garantia_ids=[g for g, _ in GARANTIAS if rng.random() < 0.4] or ["deposito_efectivo"],
                fotos=fotos,
                disponible_desde=(now - timedelta(days=rng.randint(0, 10))).date(),
                disponible_hasta=None,
                estado_publicacion="activo",
                estado_comercial="disponible",
                publicado_por=SEED_USER_ID,
                owner_contact_nombre=None,
                lease_vencimiento=None,
                creado_en=publicado_en,
                actualizado_en=publicado_en,
            )


def _seed_market_history() -> None:
    """11 meses hacia atrás + el mes actual se calcula en vivo desde
    `store.listings` (igual que `market_snapshots.sql` -- histórico
    sembrado UNION ALL cálculo actual, ver
    cuadra-data/dbt/models/marts/market_snapshots.sql)."""
    rng = random.Random(777)
    by_group: dict[tuple[str, str], list[float]] = {}
    for listing in store.listings.values():
        key = (listing.zone_id, listing.dormitorios_bucket)
        by_group.setdefault(key, []).append(listing.precio)

    today = date.today().replace(day=1)
    for (zone_id, bucket), precios in by_group.items():
        if len(precios) < 5:
            continue
        current_median = statistics.median(precios)
        median = current_median / rng.uniform(1.04, 1.14)  # hace 11 meses, algo más barato
        for months_ago in range(11, 0, -1):
            month = _shift_months(today, -months_ago)
            median *= rng.uniform(1.005, 1.02)  # tendencia levemente alcista
            store.market_history_seed.append(
                MarketSnapshotRow(
                    zone_id=zone_id,
                    dormitorios_bucket=bucket,
                    periodo=month,
                    precio_mediana=round(median, -2),
                    fuente="historico_semilla",
                )
            )


def _shift_months(d: date, delta: int) -> date:
    month_index = d.month - 1 + delta
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def seed_all() -> None:
    if store.zones:
        return  # ya sembrado -- idempotente (uvicorn --reload reimporta)
    _seed_zones()
    _seed_catalogs()
    _seed_listings()
    _seed_market_history()
