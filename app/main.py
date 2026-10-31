from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, catalogs, favorites, inquiries, listings, market, reports, users
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description=(
        "API operacional de Cuadra (usuarios, avisos, consultas, inteligencia de "
        "mercado). Contract-first: hoy corre sobre un store en memoria sembrado con "
        "datos sintéticos; ver README.md para cómo se enchufa la data layer real."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(catalogs.router)
app.include_router(listings.router)
app.include_router(market.router)
app.include_router(inquiries.router)
app.include_router(favorites.router)
app.include_router(reports.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
