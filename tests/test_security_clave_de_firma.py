"""De dónde sale la clave con que se firman los JWT.

Lo que se protege acá es el caso de producción: arrancar en AWS con la
clave de desarrollo que está escrita en el repositorio significa que
cualquiera que la lea puede firmarse un token válido para cualquier
usuario. app/core/security.py se niega a arrancar en esa situación.
"""

from __future__ import annotations

import pytest

from app.core import security
from app.core.config import settings


def test_sin_configurar_usa_la_clave_local():
    """Desarrollo y tests: no hay ARN ni Postgres, se usa secret_key."""
    assert settings.jwt_secret_arn == ""
    assert settings.db_secret_arn == ""
    assert security.clave_de_firma() == settings.secret_key


def test_con_postgres_y_clave_de_desarrollo_no_arranca(monkeypatch):
    monkeypatch.setattr(settings, "db_secret_arn", "arn:de-prueba-db")
    monkeypatch.setattr(settings, "secret_key", security._CLAVE_DE_DESARROLLO)
    monkeypatch.setattr(settings, "jwt_secret_arn", "")
    with pytest.raises(RuntimeError, match="clave de firma"):
        security.clave_de_firma()


def test_con_postgres_y_clave_propia_arranca(monkeypatch):
    monkeypatch.setattr(settings, "db_secret_arn", "arn:de-prueba-db")
    monkeypatch.setattr(settings, "secret_key", "una-clave-de-verdad")
    monkeypatch.setattr(settings, "jwt_secret_arn", "")
    assert security.clave_de_firma() == "una-clave-de-verdad"


def test_el_arn_gana_sobre_secret_key(monkeypatch):
    monkeypatch.setattr(settings, "db_secret_arn", "arn:de-prueba-db")
    monkeypatch.setattr(settings, "secret_key", security._CLAVE_DE_DESARROLLO)
    monkeypatch.setattr(settings, "jwt_secret_arn", "arn:de-prueba-jwt")
    monkeypatch.setattr(security, "leer_secreto", lambda arn: f"clave-de-{arn}")
    assert security.clave_de_firma() == "clave-de-arn:de-prueba-jwt"


def test_un_token_firmado_con_otra_clave_no_valida(monkeypatch):
    """Cambiar la clave invalida las sesiones viejas, que es lo esperado."""
    from uuid import uuid4

    user_id = uuid4()
    monkeypatch.setattr(settings, "secret_key", "clave-a")
    token = security.create_access_token(user_id)
    assert security.decode_access_token(token) == user_id

    monkeypatch.setattr(settings, "secret_key", "clave-b")
    assert security.decode_access_token(token) is None
