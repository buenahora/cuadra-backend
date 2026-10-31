"""El bootstrap del usuario de la base, contra un Postgres de verdad.

lambdas/db_bootstrap/app.py corre como custom resource de CloudFormation y
crea el usuario con el que se conectan la API y el job de Glue. Si ese rol no
existe, los dos fallan con "password authentication failed" -- un síntoma que
no se parece a la causa, y que antes de esto dependía de que alguien se
acordara de un paso manual del runbook.

Lo que importa probar no es que el SQL parsee, sino que el usuario resultante
pueda hacer su trabajo: conectarse y crear tablas (init_db() de la app y el
CREATE TABLE del job de Glue). Desde Postgres 15 el permiso de crear en el
esquema public ya no viene por defecto, así que esto no es teórico.

Se saltea si no hay Postgres escuchando. Para correrlo:

    docker run -d --name cuadra-pg-test -e POSTGRES_PASSWORD=test \\
      -e POSTGRES_DB=alquileres -p 55432:5432 postgres:16-alpine
    uv run pytest tests/test_db_bootstrap.py
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import socket

import pytest

PG_HOST = os.environ.get("CUADRA_TEST_PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("CUADRA_TEST_PG_PORT", "55432"))
PG_DB = os.environ.get("CUADRA_TEST_PG_DB", "alquileres")

# Exactamente la forma del secreto que AWS genera con
# ManageMasterUserPassword: solo usuario y contraseña, SIN host ni puerto. La
# versión anterior de este fixture le agregaba host, y por eso no detectó que
# el handler hacía maestro["host"] -- el deploy del 2026-10-31 murió con
# KeyError: 'host'. No agregar claves que el secreto real no trae.
MAESTRO = {
    "username": os.environ.get("CUADRA_TEST_PG_USER", "postgres"),
    "password": os.environ.get("CUADRA_TEST_PG_PASSWORD", "test"),
}
APP = {"username": "app_user", "password": "una-clave-de-prueba"}


def _hay_postgres() -> bool:
    try:
        with socket.create_connection((PG_HOST, PG_PORT), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _hay_postgres(),
    reason=f"sin Postgres en {PG_HOST}:{PG_PORT} -- ver el docstring del módulo",
)


def _bootstrap(monkeypatch):
    """Carga el handler por ruta (lambdas/ no es un paquete) y le saca el TLS.

    Contra RDS el ssl_context va siempre; el Postgres del contenedor no tiene
    certificados, así que se envuelve connect() solo para el test en vez de
    meterle un interruptor al código que va a producción.
    """
    ruta = pathlib.Path(__file__).resolve().parents[1] / "lambdas" / "db_bootstrap" / "app.py"
    spec = importlib.util.spec_from_file_location("db_bootstrap", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    original = modulo.pg8000.dbapi.connect

    def sin_tls(**kwargs):
        kwargs.pop("ssl_context", None)
        return original(**kwargs)

    monkeypatch.setattr(modulo.pg8000.dbapi, "connect", sin_tls)
    return modulo


@pytest.fixture
def limpio(monkeypatch):
    modulo = _bootstrap(monkeypatch)
    conn = modulo.pg8000.dbapi.connect(
        host=PG_HOST, port=PG_PORT, database=PG_DB,
        user=MAESTRO["username"], password=MAESTRO["password"],
    )
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS prueba_de_permisos CASCADE")
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'app_user'")
    if cur.fetchone():
        cur.execute("DROP OWNED BY app_user")
        cur.execute("DROP ROLE app_user")
    conn.commit()
    conn.close()
    return modulo


def _conectar_como_app(modulo, password: str = APP["password"]):
    return modulo.pg8000.dbapi.connect(
        host=PG_HOST, port=PG_PORT, database=PG_DB,
        user=APP["username"], password=password,
    )


def test_crea_el_rol_si_no_existe(limpio):
    accion = limpio._crear_usuario(MAESTRO, APP, PG_DB, PG_HOST, PG_PORT)
    assert accion == "rol creado"


def test_el_usuario_creado_puede_conectarse_y_crear_tablas(limpio):
    """Lo que de verdad importa: que init_db() de la app y el CREATE TABLE del
    job de Glue funcionen con este usuario."""
    limpio._crear_usuario(MAESTRO, APP, PG_DB, PG_HOST, PG_PORT)

    conn = _conectar_como_app(limpio)
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE prueba_de_permisos (id int)")
        cur.execute("INSERT INTO prueba_de_permisos VALUES (1)")
        cur.execute("SELECT COUNT(*) FROM prueba_de_permisos")
        assert cur.fetchone()[0] == 1
        conn.commit()
    finally:
        conn.close()


def test_es_idempotente_y_sincroniza_la_contrasena(limpio):
    """Correrlo de nuevo no falla, y deja la contraseña igual a la del secreto
    -- que es lo que hace seguro reejecutarlo en cada deploy."""
    assert limpio._crear_usuario(MAESTRO, APP, PG_DB, PG_HOST, PG_PORT) == "rol creado"
    assert limpio._crear_usuario(MAESTRO, APP, PG_DB, PG_HOST, PG_PORT) == "contraseña sincronizada"

    nueva = dict(APP, password="otra-clave-rotada")
    assert limpio._crear_usuario(MAESTRO, nueva, PG_DB, PG_HOST, PG_PORT) == "contraseña sincronizada"

    # La nueva sirve y la vieja ya no.
    _conectar_como_app(limpio, "otra-clave-rotada").close()
    with pytest.raises(Exception):
        _conectar_como_app(limpio, APP["password"]).close()


def test_una_contrasena_con_comilla_no_rompe_el_sql(limpio):
    """Las contraseñas de Secrets Manager excluyen la comilla simple, pero el
    código no debería depender de eso."""
    con_comilla = dict(APP, password="ab'cd--efg")
    limpio._crear_usuario(MAESTRO, con_comilla, PG_DB, PG_HOST, PG_PORT)
    _conectar_como_app(limpio, "ab'cd--efg").close()


def test_rechaza_un_nombre_de_rol_no_valido(limpio):
    malicioso = dict(APP, username='app"; DROP DATABASE alquileres; --')
    with pytest.raises(ValueError, match="nombre de rol no válido"):
        limpio._crear_usuario(MAESTRO, malicioso, PG_DB, PG_HOST, PG_PORT)


def test_no_usa_host_ni_puerto_del_secreto_del_master(limpio):
    """El secreto de ManageMasterUserPassword no trae host ni port.

    Este test existe porque la primera versión los leía de ahí y el deploy
    murió con KeyError: 'host'. Se le pasa un secreto con claves extra basura
    para que, si alguien vuelve a leer la conexión del secreto, falle acá y no
    en medio de un deploy.
    """
    envenenado = dict(MAESTRO, host="no-existe.invalid", port=1)
    # Si el handler usara esas claves, no podría conectarse.
    assert limpio._crear_usuario(envenenado, APP, PG_DB, PG_HOST, PG_PORT) == "rol creado"
