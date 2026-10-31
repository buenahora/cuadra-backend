"""Conexión SQLite para los datos operacionales (usuarios, favoritos,
consultas, informes) -- separada a propósito de
app/repositories/warehouse/ (el warehouse.duckdb de data_layer): ese
archivo es un artefacto de dbt pensado para reconstruirse (dbt run/build
lo puede pisar o dejarlo bloqueado mientras corre), y esto es el registro
transaccional que no puede perderse. Ver conversación 2026-08-15 sobre
por qué no comparten motor.

Se abre y cierra una conexión por operación (en vez de una conexión larga
compartida entre threads) -- FastAPI corre los endpoints sync en un
threadpool y sqlite3 no es thread-safe por conexión; a esta escala el
costo de abrir/cerrar es insignificante y evita cualquier problema de
concurrencia sin tener que manejar locks a mano.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    nombre_completo TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    telefono TEXT,
    password_hash TEXT NOT NULL,
    es_corredor INTEGER NOT NULL DEFAULT 0,
    google_id TEXT,
    creado_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    creado_en TEXT NOT NULL,
    PRIMARY KEY (user_id, listing_id)
);

CREATE TABLE IF NOT EXISTS inquiries (
    id TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL,
    remitente_user_id TEXT NOT NULL,
    nombre TEXT NOT NULL,
    email TEXT NOT NULL,
    telefono TEXT,
    fecha_mudanza TEXT,
    mensaje TEXT NOT NULL,
    respuesta TEXT,
    creado_en TEXT NOT NULL,
    respondido_en TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    generado_por TEXT NOT NULL,
    titulo TEXT NOT NULL,
    destinatario_nombre TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    dormitorios_bucket TEXT NOT NULL,
    periodo TEXT NOT NULL,
    secciones_incluidas TEXT NOT NULL,
    pdf_url TEXT NOT NULL,
    generado_en TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_inquiries_listing ON inquiries(listing_id);
CREATE INDEX IF NOT EXISTS idx_inquiries_remitente ON inquiries(remitente_user_id);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_reports_generado_por ON reports(generado_por);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    path = Path(settings.sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(_SCHEMA)
