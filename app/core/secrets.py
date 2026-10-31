"""Lectura de secretos de AWS Secrets Manager, cacheada por proceso.

Dos secretos llegan por acá, los dos como ARN y no como valor: las
credenciales de la RDS y la clave con que se firman los JWT. Se pasa el ARN
y no el valor a propósito -- el user-data de la instancia queda guardado en
el launch template y es legible con describe-launch-template-versions, así
que un secreto escrito ahí no es un secreto.

Se cachea en memoria tras la primera lectura: Secrets Manager se cobra por
llamada y el valor no cambia durante la vida del proceso. Una rotación se
toma en el próximo arranque, igual que el resto de la configuración.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.core.config import settings


@lru_cache(maxsize=8)
def leer_secreto(arn: str) -> str:
    import boto3

    cliente = boto3.client("secretsmanager", region_name=settings.aws_region or None)
    return cliente.get_secret_value(SecretId=arn)["SecretString"]


def leer_secreto_json(arn: str) -> dict[str, Any]:
    return json.loads(leer_secreto(arn))
