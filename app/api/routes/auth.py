"""Registro y login.

Con el user pool configurado (AWS) estas dos rutas quedan apagadas: el login
es el hosted UI de Cognito, que incluye "Entrar con Google", y la API solo
acepta los ID tokens que Cognito emite. Siguen vivas sin pool -- desarrollo y
tests -- contra la tabla `users` con bcrypt.

Responden 404 y no 403 cuando están apagadas: para un cliente que habla con
la API desplegada, estas rutas sencillamente no existen.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_users_repo
from app.core import cognito
from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.base import UsersRepository
from app.repositories.models import UserRow
from app.schemas.user import Token, UserLogin, UserOut, UserRegister

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_token(user: UserRow) -> Token:
    return Token(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


def _rechazar_si_cognito() -> None:
    if cognito.esta_configurado():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "El acceso con contraseña está deshabilitado: entrá por Cognito",
        )


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserRegister, users_repo: UsersRepository = Depends(get_users_repo)
) -> Token:
    _rechazar_si_cognito()
    if users_repo.get_by_email(payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese email")
    user = users_repo.create(
        nombre_completo=payload.nombre_completo,
        email=payload.email,
        telefono=payload.telefono,
        password_hash=hash_password(payload.password),
    )
    return _to_token(user)


@router.post("/login", response_model=Token)
def login(
    payload: UserLogin, users_repo: UsersRepository = Depends(get_users_repo)
) -> Token:
    _rechazar_si_cognito()
    user = users_repo.get_by_email(payload.email)
    if user is None or not user.password_hash or not verify_password(
        payload.password, user.password_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña incorrectos")
    return _to_token(user)
