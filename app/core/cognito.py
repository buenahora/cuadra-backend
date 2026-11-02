"""Verificación de los tokens que emite Cognito.

El navegador hace el login contra el hosted UI (Cognito o "Entrar con
Google"), cambia el código por tokens y manda el **ID token** en el header
Authorization. Acá se comprueba que ese token sea auténtico antes de creerle
nada de lo que dice.

Se valida el ID token y no el access token porque es el único que trae
`email` y `name`, que es lo que hace falta para dar de alta al usuario la
primera vez que entra. El access token de Cognito solo trae scopes.

La firma es RS256 con claves que publica Cognito en su JWKS. Se bajan una vez
por proceso y se guardan: son estables, y Cognito documenta que rota avisando.
Si aparece un `kid` desconocido se vuelven a bajar una sola vez, por si la
rotación ocurrió con el proceso vivo.

No se usa boto3 ni una llamada a Cognito por request: la verificación es
criptográfica y local, así que no agrega latencia ni cuota de API.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings

_TIMEOUT_JWKS_S = 5

_lock = threading.Lock()
_jwks: dict[str, Any] | None = None


def region() -> str:
    """La región sale del propio id del pool (`us-east-1_2cuCX8OHX`).

    Evita una variable de entorno más que se puede desincronizar del pool.
    """
    pool_id = settings.cognito_user_pool_id
    if "_" in pool_id:
        return pool_id.split("_", 1)[0]
    return settings.aws_region


def esta_configurado() -> bool:
    return bool(settings.cognito_user_pool_id and settings.cognito_client_id)


def issuer() -> str:
    return f"https://cognito-idp.{region()}.amazonaws.com/{settings.cognito_user_pool_id}"


def _bajar_jwks() -> dict[str, Any]:
    url = f"{issuer()}/.well-known/jwks.json"
    with urllib.request.urlopen(url, timeout=_TIMEOUT_JWKS_S) as resp:
        return json.load(resp)


def _claves(refrescar: bool = False) -> dict[str, Any]:
    global _jwks
    with _lock:
        if _jwks is None or refrescar:
            _jwks = _bajar_jwks()
        return _jwks


def _clave_para(kid: str) -> dict[str, Any] | None:
    for intento, refrescar in enumerate((False, True)):
        for clave in _claves(refrescar).get("keys", []):
            if clave.get("kid") == kid:
                return clave
        # Primer intento fallido: puede ser una rotación con el proceso vivo.
        del intento
    return None


def verificar_id_token(token: str) -> dict[str, Any] | None:
    """Devuelve los claims si el token es válido para este pool, si no None.

    Comprueba, además de la firma: que lo haya emitido nuestro pool (`iss`),
    que sea para nuestra aplicación (`aud`), que sea un ID token y no un
    access token (`token_use`) y que no esté vencido (lo hace python-jose).
    Sin el chequeo de `aud`, un token de otra app del mismo pool entraría.
    """
    if not esta_configurado():
        return None
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except JWTError:
        return None
    if not kid:
        return None

    clave = _clave_para(kid)
    if clave is None:
        return None

    try:
        claims = jwt.decode(
            token,
            clave,
            algorithms=["RS256"],
            audience=settings.cognito_client_id,
            issuer=issuer(),
        )
    except JWTError:
        return None

    if claims.get("token_use") != "id":
        return None
    return claims
