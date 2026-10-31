"""Conexión a los datos operacionales (usuarios, favoritos, consultas,
informes), con dos motores detrás del mismo contrato:

- **SQLite**, en un archivo local. Es el default y lo que se usa en
  desarrollo y en los tests: cero setup, el repo se clona y anda.
- **Postgres** (RDS), cuando `settings.db_secret_arn` está cargado. Es lo
  que corre en AWS: las instancias del ASG son efímeras y hay más de una,
  así que un archivo en disco local no sirve -- se pierde en cada instance
  refresh y las dos instancias no se ven entre ellas.

Un solo dialecto SQL para los dos, no dos implementaciones de repositorio.
Alcanza porque el modelo guarda todo como texto (UUID como str, fechas como
ISO), así que no hay tipos propios de un motor en juego, y porque
`ON CONFLICT DO NOTHING` existe en Postgres y en SQLite >= 3.24. Lo único
que difiere es el marcador de parámetro, y de eso se encarga `_a_estilo`.

Se abre y cierra una conexión por operación, igual que antes con SQLite:
FastAPI corre los endpoints sync en un threadpool y ninguno de los dos
drivers es thread-safe por conexión. A esta escala el costo es irrelevante
y evita manejar locks o un pool a mano.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.secrets import leer_secreto_json

# Todo texto a propósito -- ver el docstring. Los tipos valen en los dos
# motores, así que el esquema es uno solo.
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


def usa_postgres() -> bool:
    return bool(settings.db_secret_arn)


def _a_estilo(sql: str, estilo: str) -> str:
    """Pasa los `?` del SQL compartido al marcador que espera el driver.

    No es un replace a secas: un `?` dentro de un literal entre comillas es
    un signo de pregunta, no un parámetro, y no hay que tocarlo.
    """
    if estilo == "qmark":
        return sql
    salida: list[str] = []
    en_literal = False
    for char in sql:
        if char == "'":
            en_literal = not en_literal
            salida.append(char)
        elif char == "?" and not en_literal:
            salida.append("%s")
        else:
            salida.append(char)
    return "".join(salida)


class _Resultado:
    """Lo que devuelve execute(). Expone filas como dicts para que el código
    de los repositorios acceda por nombre con los dos drivers (pg8000
    devuelve tuplas; sqlite3.Row ya permite por nombre, pero no es un dict).
    """

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor
        descripcion = cursor.description or []
        self._columnas = [
            c[0].decode() if isinstance(c[0], bytes) else c[0] for c in descripcion
        ]

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def _a_dict(self, fila: Any) -> dict[str, Any]:
        return dict(zip(self._columnas, fila))

    def fetchone(self) -> dict[str, Any] | None:
        fila = self._cursor.fetchone()
        return self._a_dict(fila) if fila is not None else None

    def fetchall(self) -> list[dict[str, Any]]:
        return [self._a_dict(f) for f in self._cursor.fetchall()]


class Conexion:
    def __init__(self, conn: Any, estilo: str) -> None:
        self._conn = conn
        self._estilo = estilo

    def execute(self, sql: str, params: Sequence[Any] = ()) -> _Resultado:
        cursor = self._conn.cursor()
        cursor.execute(_a_estilo(sql, self._estilo), tuple(params))
        return _Resultado(cursor)


def _credenciales_postgres() -> dict[str, Any]:
    """Lee el secreto de RDS que crea infra/backend.yaml (AppDbSecret). Es el
    mismo secreto y el mismo formato que usa el job de Glue de cuadra-data
    (ver glue/transform.py, cargar_en_postgres)."""
    return leer_secreto_json(settings.db_secret_arn)


@contextmanager
def get_connection() -> Iterator[Conexion]:
    if usa_postgres():
        import pg8000.dbapi

        secreto = _credenciales_postgres()
        conn = pg8000.dbapi.connect(
            host=secreto["host"],
            port=int(secreto.get("port", 5432)),
            database=secreto.get("dbname", settings.db_name),
            user=secreto["username"],
            password=secreto["password"],
            ssl_context=True if settings.db_ssl else None,
        )
        estilo = "format"
    else:
        path = Path(settings.sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        estilo = "qmark"
    try:
        yield Conexion(conn, estilo)
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    # executescript es solo de sqlite3: se parte el esquema y se manda
    # sentencia por sentencia, que sirve para los dos motores.
    sentencias = [s.strip() for s in _SCHEMA.split(";") if s.strip()]
    with get_connection() as conn:
        for sentencia in sentencias:
            conn.execute(sentencia)
