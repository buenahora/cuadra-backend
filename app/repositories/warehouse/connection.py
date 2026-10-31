"""Conexión de solo lectura al warehouse DuckDB de data_layer (dbt marts +
seeds -- ver app/core/config.py Settings.data_layer_duckdb_path).

Perezosa a propósito: si esto se conectara al importar app/api/deps.py
(donde se construyen los repositorios), levantar la API con el warehouse
todavía sin poblar (ej. clon nuevo del repo, antes de correr el pipeline
de data_layer al menos una vez) tumbaría el arranque entero. En cambio,
si falla, se loguea una vez y las fuentes que dependen de esto devuelven
vacío -- la API sigue funcionando solo con avisos de Cuadra.
"""

from __future__ import annotations

import sys

import duckdb

from app.core.config import settings

_connection: duckdb.DuckDBPyConnection | None = None
_tried_and_failed = False


def get_warehouse_connection() -> duckdb.DuckDBPyConnection | None:
    global _connection, _tried_and_failed
    if _connection is not None:
        return _connection
    if _tried_and_failed:
        return None
    try:
        _connection = duckdb.connect(settings.data_layer_duckdb_path, read_only=True)
        return _connection
    except Exception as e:  # noqa: BLE001 -- cualquier falla de conexión degrada, no tumba la API
        _tried_and_failed = True
        print(
            f"!! no se pudo conectar al warehouse de data_layer "
            f"({settings.data_layer_duckdb_path}): {e} -- "
            f"sirviendo solo avisos publicados en Cuadra hasta el próximo restart.",
            file=sys.stderr,
        )
        return None
