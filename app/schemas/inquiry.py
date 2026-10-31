from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class InquiryCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    email: EmailStr
    telefono: str | None = None
    fecha_mudanza: date | None = None
    mensaje: str = Field(min_length=1, max_length=2000)


class InquiryRespond(BaseModel):
    respuesta: str = Field(min_length=1, max_length=2000)


class InquiryOut(BaseModel):
    id: UUID
    listing_id: UUID
    remitente_user_id: UUID
    nombre: str
    email: EmailStr
    telefono: str | None
    fecha_mudanza: date | None
    mensaje: str
    respuesta: str | None
    creado_en: datetime
    respondido_en: datetime | None
