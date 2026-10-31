"""Crea el usuario de la aplicación en Postgres. Custom resource de CloudFormation.

El stack crea la RDS con el usuario administrador `postgres_admin` (su
contraseña la maneja AWS) y, aparte, el secreto AppDbSecret con las
credenciales de `app_user`. Pero **nadie creaba app_user en la base**: el
runbook lo tenía como paso manual. Hasta que exista, la API y el job de Glue
fallan con "password authentication failed", que es un síntoma que no se
parece a la causa.

Esto lo hace solo, al crear o actualizar el stack. Corre dentro de la VPC
porque la RDS está en subredes privadas, y es el único componente que lee el
secreto del administrador -- las instancias de la app no lo pueden leer, solo
leen el de app_user.

Idempotente: si el rol ya existe le sincroniza la contraseña con el secreto en
vez de fallar. Eso hace que volver a correrlo sea seguro, y que un stack
actualizado después de una rotación quede consistente.
"""

from __future__ import annotations

import json
import os
import urllib.request

import boto3
import pg8000.dbapi

_LOG_SIN_SECRETOS = "no se loguean contraseñas: solo el nombre del rol"


def _secreto(arn: str) -> dict:
    cliente = boto3.client("secretsmanager")
    return json.loads(cliente.get_secret_value(SecretId=arn)["SecretString"])


def _responder(event, context, estado: str, motivo: str = "") -> None:
    """CloudFormation espera un PUT a una URL prefirmada; sin esto el stack se
    queda esperando una hora y recién entonces falla."""
    cuerpo = json.dumps(
        {
            "Status": estado,
            "Reason": f"{motivo} (ver CloudWatch: {context.log_stream_name})"[:1024],
            "PhysicalResourceId": event.get("PhysicalResourceId") or context.log_stream_name,
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "Data": {},
        }
    ).encode()
    peticion = urllib.request.Request(
        event["ResponseURL"], data=cuerpo, method="PUT",
        headers={"content-type": "", "content-length": str(len(cuerpo))},
    )
    urllib.request.urlopen(peticion).read()


def _crear_usuario(maestro: dict, app: dict, base: str, host: str, port: int) -> str:
    """`maestro` y `app` solo aportan usuario y contraseña.

    El secreto que AWS genera con ManageMasterUserPassword trae **solo**
    username y password: no incluye host, port ni dbname (a diferencia del
    secreto de app_user, al que SecretTargetAttachment sí le agrega la conexión).
    Por eso el endpoint llega aparte, desde el template.
    """
    usuario = app["username"]
    conn = pg8000.dbapi.connect(
        host=host,
        port=port,
        database=base,
        user=maestro["username"],
        password=maestro["password"],
        ssl_context=True,
    )
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (usuario,))
        existe = cur.fetchone() is not None

        # El nombre del rol no puede ir como parámetro (es un identificador, no
        # un valor), y la contraseña tampoco en CREATE/ALTER ROLE. Se validan a
        # mano: el nombre sale de SecretStringTemplate en el template, no de
        # input de usuario, pero igual no se interpola nada sin chequear.
        if not usuario.replace("_", "").isalnum():
            raise ValueError(f"nombre de rol no válido: {usuario!r}")
        password = app["password"].replace("'", "''")

        if existe:
            cur.execute(f"ALTER ROLE \"{usuario}\" WITH LOGIN PASSWORD '{password}'")
            accion = "contraseña sincronizada"
        else:
            cur.execute(f"CREATE ROLE \"{usuario}\" WITH LOGIN PASSWORD '{password}'")
            accion = "rol creado"

        # Permisos mínimos para lo que hacen la app y el pipeline: conectarse y
        # crear/leer sus propias tablas. CREATE en el esquema public hace falta
        # explícito desde Postgres 15 -- antes venía por defecto para PUBLIC y
        # ya no. Lo usan init_db() de la app y el CREATE TABLE del job de Glue.
        cur.execute(f'GRANT CONNECT ON DATABASE "{base}" TO "{usuario}"')
        cur.execute(f'GRANT USAGE, CREATE ON SCHEMA public TO "{usuario}"')
        conn.commit()
        print(f"{usuario}: {accion}, permisos aplicados ({_LOG_SIN_SECRETOS})")
        return accion
    finally:
        conn.close()


def handler(event, context):
    print(f"request: {event.get('RequestType')} {event.get('LogicalResourceId')}")
    try:
        # Borrar el stack no borra el rol: la base puede quedar con un snapshot
        # (DeletionPolicy: Snapshot) y restaurarla con el rol adentro es lo
        # esperado. Tampoco habría a qué conectarse si la base ya se fue.
        if event["RequestType"] == "Delete":
            _responder(event, context, "SUCCESS", "delete: nada que hacer")
            return

        base = os.environ["DB_NAME"]
        accion = _crear_usuario(
            _secreto(os.environ["MASTER_SECRET_ARN"]),
            _secreto(os.environ["APP_SECRET_ARN"]),
            base,
            os.environ["DB_HOST"],
            int(os.environ.get("DB_PORT", "5432")),
        )
        _responder(event, context, "SUCCESS", accion)
    except Exception as e:  # noqa: BLE001 -- hay que responderle a CloudFormation igual
        print(f"falló el bootstrap: {type(e).__name__}: {e}")
        _responder(event, context, "FAILED", f"{type(e).__name__}: {e}")
