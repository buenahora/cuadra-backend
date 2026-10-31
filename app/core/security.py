"""Hash de contraseñas y firma/verificación de los JWT de sesión.

La clave de firma sale de `clave_de_firma()`, no de settings.secret_key
directo: en AWS llega como ARN de Secrets Manager (settings.jwt_secret_arn)
y settings.secret_key queda sin usar. Ver app/core/secrets.py.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.core.secrets import leer_secreto

_CLAVE_DE_DESARROLLO = "dev-secret-change-me"


def clave_de_firma() -> str:
    """La clave con que se firman y validan los tokens.

    Con jwt_secret_arn cargado sale de Secrets Manager (cacheada por
    proceso). Sin ARN cae a settings.secret_key, que sirve para desarrollo
    y para los tests.

    Si la app está configurada contra Postgres -- o sea, corriendo en AWS --
    y la clave sigue siendo la de desarrollo, no arranca. Ese texto está en
    el repositorio: firmar con él es dejar que cualquiera se haga un token
    válido para cualquier usuario. Mejor que la instancia no pase el health
    check que servir sesiones falsificables.
    """
    if settings.jwt_secret_arn:
        return leer_secreto(settings.jwt_secret_arn)
    if settings.db_secret_arn and settings.secret_key == _CLAVE_DE_DESARROLLO:
        raise RuntimeError(
            "La app está configurada contra Postgres (CUADRA_DB_SECRET_ARN) pero la "
            "clave de firma de los JWT sigue siendo la de desarrollo. Cargar "
            "CUADRA_JWT_SECRET_ARN (output AppJwtSecretArn del stack del backend) "
            "o CUADRA_SECRET_KEY."
        )
    return settings.secret_key


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8")[:72], password_hash.encode("utf-8"))


def create_access_token(user_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, clave_de_firma(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> UUID | None:
    try:
        payload = jwt.decode(token, clave_de_firma(), algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        return UUID(sub)
    except ValueError:
        return None
