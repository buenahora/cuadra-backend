from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FavoriteOut(BaseModel):
    listing_id: UUID
    creado_en: datetime
