from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.repositories.models import UserRow
from app.schemas.user import UserOut

router = APIRouter(tags=["users"])


@router.get("/users/me", response_model=UserOut)
def get_me(current_user: UserRow = Depends(get_current_user)) -> UserRow:
    return current_user
