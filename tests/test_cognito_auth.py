"""Login con Cognito: verificación del token y alta del usuario.

El token se firma de verdad con una clave RSA generada en el test y se
publica un JWKS falso, así que se ejercita el mismo camino criptográfico que
en AWS. Los casos negativos son lo que importa: un token que no se rechaza es
una sesión que alguien se fabricó.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt
from jose.utils import base64url_encode

from app.core import cognito

POOL_ID = "us-east-1_TESTPOOL1"
CLIENT_ID = "cliente-de-prueba"
KID = "clave-1"


def _pem_privada(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _jwk_publica(key: rsa.RSAPrivateKey, kid: str = KID) -> dict[str, Any]:
    numeros = key.public_key().public_numbers()
    def b64(n: int) -> str:
        largo = (n.bit_length() + 7) // 8
        return base64url_encode(n.to_bytes(largo, "big")).decode()
    return {"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256",
            "n": b64(numeros.n), "e": b64(numeros.e)}


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> rsa.RSAPrivateKey:
    """Pool configurado, con un JWKS que sirve la clave del test."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(cognito.settings, "cognito_user_pool_id", POOL_ID)
    monkeypatch.setattr(cognito.settings, "cognito_client_id", CLIENT_ID)
    monkeypatch.setattr(cognito, "_jwks", None)
    monkeypatch.setattr(cognito, "_bajar_jwks", lambda: {"keys": [_jwk_publica(key)]})
    return key


def _token(key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    claims = {
        "sub": "sub-abc-123",
        "email": "persona@example.com",
        "name": "Persona de Prueba",
        "token_use": "id",
        "aud": CLIENT_ID,
        "iss": f"https://cognito-idp.us-east-1.amazonaws.com/{POOL_ID}",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    claims.update(overrides)
    return jwt.encode(claims, _pem_privada(key), algorithm="RS256", headers={"kid": KID})


def test_token_valido_se_acepta(pool: rsa.RSAPrivateKey) -> None:
    claims = cognito.verificar_id_token(_token(pool))
    assert claims is not None
    assert claims["sub"] == "sub-abc-123"
    assert claims["email"] == "persona@example.com"


def test_region_sale_del_pool_id(pool: rsa.RSAPrivateKey) -> None:
    assert cognito.region() == "us-east-1"


@pytest.mark.parametrize(
    "overrides, motivo",
    [
        ({"aud": "otra-app"}, "token de otra aplicación del mismo pool"),
        ({"iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_OTRO"}, "otro pool"),
        ({"token_use": "access"}, "access token en vez de ID token"),
        ({"exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, "vencido"),
    ],
)
def test_tokens_que_hay_que_rechazar(
    pool: rsa.RSAPrivateKey, overrides: dict[str, Any], motivo: str
) -> None:
    assert cognito.verificar_id_token(_token(pool, **overrides)) is None, motivo


def test_firma_de_otra_clave_se_rechaza(pool: rsa.RSAPrivateKey) -> None:
    """Lo más importante del archivo: un token bien formado pero firmado por
    quien no es Cognito no puede entrar."""
    impostora = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert cognito.verificar_id_token(_token(impostora)) is None


def test_basura_no_explota(pool: rsa.RSAPrivateKey) -> None:
    for valor in ("", "no-es-un-jwt", "a.b.c"):
        assert cognito.verificar_id_token(valor) is None


def test_sin_pool_configurado_no_valida_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cognito.settings, "cognito_user_pool_id", "")
    monkeypatch.setattr(cognito.settings, "cognito_client_id", "")
    assert cognito.esta_configurado() is False
    assert cognito.verificar_id_token("cualquier-cosa") is None


# --------------------------------------------------------------- alta de usuario

@pytest.fixture
def users_repo(monkeypatch: pytest.MonkeyPatch):
    """Repo de usuarios en memoria, con la misma interfaz que el de SQL."""
    from uuid import uuid4
    from app.repositories.models import UserRow

    class RepoFalso:
        def __init__(self) -> None:
            self.filas: dict[Any, UserRow] = {}

        def create(self, nombre_completo, email, telefono, password_hash,
                   es_corredor=False, cognito_sub=None) -> UserRow:
            fila = UserRow(
                id=uuid4(), nombre_completo=nombre_completo, email=email.lower(),
                telefono=telefono, password_hash=password_hash,
                es_corredor=es_corredor, google_id=None, cognito_sub=cognito_sub,
                creado_en=datetime.now(timezone.utc),
            )
            self.filas[fila.id] = fila
            return fila

        def get_by_id(self, user_id):
            return self.filas.get(user_id)

        def get_by_email(self, email):
            return next((f for f in self.filas.values() if f.email == email.lower()), None)

        def get_by_cognito_sub(self, sub):
            return next((f for f in self.filas.values() if f.cognito_sub == sub), None)

        def vincular_cognito(self, user_id, sub):
            self.filas[user_id].cognito_sub = sub

    return RepoFalso()


def test_primer_login_crea_el_usuario(pool, users_repo) -> None:
    from app.api.deps import _usuario_de_cognito

    user = _usuario_de_cognito(_token(pool), users_repo)
    assert user is not None
    assert user.email == "persona@example.com"
    assert user.nombre_completo == "Persona de Prueba"
    assert user.cognito_sub == "sub-abc-123"
    # Nunca hubo contraseña nuestra: la guarda Cognito.
    assert user.password_hash is None


def test_segundo_login_reusa_la_misma_fila(pool, users_repo) -> None:
    from app.api.deps import _usuario_de_cognito

    primero = _usuario_de_cognito(_token(pool), users_repo)
    segundo = _usuario_de_cognito(_token(pool), users_repo)
    assert primero.id == segundo.id
    assert len(users_repo.filas) == 1


def test_cambiar_el_email_en_google_no_crea_un_usuario_nuevo(pool, users_repo) -> None:
    """Se busca por `sub` antes que por email justamente para esto: si mandara
    el email, la persona perdería favoritos, consultas e informes."""
    from app.api.deps import _usuario_de_cognito

    primero = _usuario_de_cognito(_token(pool), users_repo)
    segundo = _usuario_de_cognito(_token(pool, email="otro@example.com"), users_repo)
    assert primero.id == segundo.id
    assert len(users_repo.filas) == 1


def test_cuenta_vieja_con_el_mismo_email_se_vincula(pool, users_repo) -> None:
    """Sin este rescate, el INSERT chocaría contra el UNIQUE de email."""
    from app.api.deps import _usuario_de_cognito

    vieja = users_repo.create(
        nombre_completo="Antes", email="persona@example.com",
        telefono=None, password_hash="hash-bcrypt-viejo",
    )
    user = _usuario_de_cognito(_token(pool), users_repo)
    assert user.id == vieja.id
    assert user.cognito_sub == "sub-abc-123"
    assert len(users_repo.filas) == 1


def test_token_invalido_no_crea_nada(pool, users_repo) -> None:
    from app.api.deps import _usuario_de_cognito

    impostora = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert _usuario_de_cognito(_token(impostora), users_repo) is None
    assert users_repo.filas == {}


# --------------------------------------------------------- rutas de contraseña

def test_register_y_login_apagados_con_cognito(pool, client) -> None:
    for ruta, cuerpo in [
        ("/auth/register", {"nombre_completo": "X", "email": "x@y.com",
                            "telefono": None, "password": "Secreta123"}),
        ("/auth/login", {"email": "x@y.com", "password": "Secreta123"}),
    ]:
        resp = client.post(ruta, json=cuerpo)
        assert resp.status_code == 404, f"{ruta} sigue aceptando contraseñas"


def test_register_y_login_siguen_vivos_sin_cognito(client) -> None:
    # Email único: la base de los tests sobrevive entre corridas, y un email
    # fijo daría 409 la segunda vez por una razón que no es la que se prueba.
    from uuid import uuid4

    email = f"sincognito-{uuid4().hex[:8]}@example.com"
    resp = client.post("/auth/register", json={
        "nombre_completo": "Sin Cognito", "email": email,
        "telefono": None, "password": "Secreta123",
    })
    assert resp.status_code == 201
