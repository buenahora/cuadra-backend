# Cuadra — Backend

API operacional de Cuadra: usuarios, avisos, consultas, favoritos e
inteligencia de mercado (below/in/above, min/mediana/máximo, histórico de
12 meses, informes PDF de corredor). FastAPI + Pydantic.

**Enfoque: contract-first.** Este backend define y sirve el contrato HTTP
completo que el frontend (`cuadra-frontend/`) necesita, hoy contra un **store en
memoria sembrado con datos sintéticos** (misma idea que
`cuadra-data/etl/extract/generate_synthetic_listings.py`, pero en Python
puro, sin pipeline). La data layer real (`cuadra-data/`, dbt + DuckDB) se
está poblando en paralelo y por separado — cuando tenga volumen real, se
conecta reemplazando el repositorio (ver "Cómo se enchufa la data layer
real" más abajo), sin tocar routers ni schemas.

## Quickstart

Requisitos: [`uv`](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload   # http://127.0.0.1:8000
```

Docs interactivos (OpenAPI) en `http://127.0.0.1:8000/docs`. El store se
siembra automáticamente al arrancar (`app/repositories/memory/seed.py`):
15 barrios, 12 amenities, 5 garantías, y ~70 avisos sintéticos con
histórico de 12 meses para los 6 barrios de mayor volumen — suficiente
para ejercitar cada endpoint sin depender de la data layer real.

```bash
uv run pytest -v      # 22 tests, cubren cada router end-to-end
```

Para que el frontend (`frontend/`, Vite en `localhost:5173`) le pegue
directo, CORS ya está habilteado para ese origen (`app/core/config.py`,
`cors_origins`).

## Estructura

```
app/
  main.py                  Punto de entrada FastAPI, CORS, montaje de /static, include_router
  core/                    config.py (Settings via env vars), security.py (bcrypt + JWT)
  schemas/                 Contratos Pydantic de la API -- lo que ve el frontend
  repositories/
    base.py                Protocols: el contrato que cualquier motor de datos debe cumplir
    models.py              Filas de dominio (dataclasses), independientes del schema HTTP
    memory/                Implementación actual: store en memoria + seed sintético
  services/
    market.py               Motor de clasificación below/in/above + cómputo de MarketStat
    geo.py                   Haversine + point-in-polygon (búsqueda por radio / zona dibujada)
    listing_view.py          Ensambla ListingSummary/ListingOut a partir de filas + índice de mercado
    report_pdf.py            Genera el PDF de valuación de corredor (fpdf2)
  api/
    deps.py                 Wiring repos <-> routers, auth dependency (get_current_user)
    routes/                 Un router por recurso
tests/                      pytest + TestClient, un archivo por área
```

## Endpoints

Agrupados por lo que resuelven (ver `cuadra-data/docs/data-model.md` para
el porqué de cada entidad):

**Auth** — `POST /auth/register`, `POST /auth/login`, `GET /users/me`

**Avisos** (`Listing`) —
`GET /listings` (búsqueda: texto, zona(s), dormitorios, precio, metraje,
amenities, garantías, mascotas, radio desde un punto `lat/lng/radio_m`,
orden, paginación) ·
`POST /listings/search` (zona dibujada a mano, polígono) ·
`GET /listings/{id}` · `POST /listings` · `PATCH /listings/{id}` ·
`DELETE /listings/{id}` (soft-delete → `archivado`) ·
`POST /listings/{id}/photos`, `POST /uploads/photos` ·
`GET /users/me/listings` ("mis publicaciones" / "mi cartera", filtrable
por `estado_comercial`)

**Mercado** — `GET /market/stats`, `GET /market/snapshots` (histórico
12 meses), `POST /market/classify` (below/in/above para un precio
propuesto — el mismo servicio alimenta el chip del detalle, la consulta
pre-publicación y el feedback en vivo del wizard de precio)

**Consultas** (`Inquiry`) — `POST /listings/{id}/inquiries`,
`GET /listings/{id}/inquiries` (solo el publicador), `PATCH
/inquiries/{id}` (responder), `GET /users/me/inquiries`

**Favoritos** — `POST` / `DELETE /listings/{id}/favorite`,
`GET /users/me/favorites`

**Catálogos** — `GET /zones` (`tiene_estadisticas` se calcula en vivo,
no es un flag manual), `GET /amenities`, `GET /garantias`

**Informes de corredor** (`Report`) — `POST /reports` (genera PDF real
con `fpdf2` a partir de `MarketStat`/`MarketSnapshot`/comparables),
`GET /reports/{id}`, `GET /users/me/reports`

## Decisiones de diseño

- **`estado_publicacion` vs `estado_comercial` separados** en `Listing`,
  resolviendo la inconsistencia `Activo/Pausado` (S2F) vs
  `Disponible/Alquilada/En proceso` (S3B) que señala
  `cuadra-data/docs/data-model.md §3`.
- **Umbral below/in/above (8%) y tamaño de muestra mínimo (5)** son
  config (`app/core/config.py`, override por env var `CUADRA_*`), no
  constantes de código — están copiados del prototipo/dbt sin validar con
  datos reales, van a cambiar.
- **`MarketStat` se calcula en el momento**, agrupando avisos activos en
  memoria por zona+dormitorios (`app/services/market.py`), replicando
  exactamente la lógica de `cuadra-data/dbt/models/marts/market_stats.sql`
  (misma agrupación, mismo criterio de `muestra_confiable`). No se
  guarda una tabla de estadísticas separada que se pueda desincronizar
  de los avisos.
- **Búsqueda geoespacial sin PostGIS**: `app/services/geo.py` implementa
  haversine y point-in-polygon en Python puro — suficiente para el
  volumen en memoria de hoy, con el mismo contrato
  (`ListingFilter.center/radio_m/polygon`) que tendría una
  implementación real con `ST_DWithin`/`ST_Within`.
- **Geocoding real pendiente**: `POST /listings` hoy asigna
  `lat/lng` fijos (centro de Montevideo) en vez de geocodificar
  `direccion` — marcado explícitamente en
  `ListingsRepositoryMemory.create` (roadmap Fase 1).

## Cómo se enchufa la data layer real

Todo repositorio implementa un `Protocol` de `app/repositories/base.py`
(`ListingsRepository`, `MarketSnapshotsRepository`, etc.). Hoy
`app/api/deps.py` los resuelve todos contra
`app/repositories/memory/repo.py`. El día que `data_layer` (dbt/DuckDB, o
lo que sea que termine siendo el warehouse operacional) tenga datos
reales:

1. Escribir una clase nueva (ej. `app/repositories/duckdb/repo.py`) que
   cumpla el mismo `Protocol` — mismos métodos, misma forma de entrada y
   salida (`ListingRow`, `ListingFilter`, etc.).
2. Cambiar las funciones `get_*_repo()` en `app/api/deps.py` para que
   construyan esa clase en vez de la de memoria.

Ningún router, schema ni servicio cambia. Es a propósito el único punto
de acoplamiento entre la API y el motor de datos.

## Qué es real y qué no (igual que `cuadra-data/README.md`)

| Pieza | Estado |
|---|---|
| Contrato HTTP (schemas, routers, códigos de estado, paginación) | Real, pensado para que el frontend actual (`frontend/src/data/`) deje de hardcodear datos |
| Auth (bcrypt + JWT) | Real, funcional |
| Store en memoria + seed | **Sintético**, semilla fija, se resetea en cada restart del proceso |
| `MarketStat`/clasificación below-in-above | Lógica real, sobre datos sintéticos |
| Geocoding de `direccion` → `lat/lng` | **No implementado** — placeholder fijo |
| Generación de PDF (`/reports`) | Real (`fpdf2`), contenido armado con los datos sintéticos disponibles |
| OAuth Google | No implementado (tampoco lo está en el prototipo frontend) |
| Verificación de identidad propietario/corredor | No implementada (pregunta de negocio abierta, ver `cuadra-data/docs/business.md §8`) |

## Deploy

El CI despliega solo. En cada push a `main`, `.github/workflows/deploy.yml`
corre los tests, empaqueta `app/` + el `requirements.txt` resuelto por `uv`,
construye la AMI con Packer (`packer/`), hace `aws cloudformation deploy` de
`infra/backend.yaml` con la AMI nueva y dispara un instance refresh del ASG.

Este repo también es dueño del stack **base** (red, security groups, SNS,
bucket de artefactos, roles de OIDC), que usan los tres repos:
`infra/base.yaml`, con su propio workflow manual ("Deploy base").

El runbook completo — orden del primer despliegue, secrets y variables de cada
repo, qué exporta cada stack — está en **`infra/README.md`**.
