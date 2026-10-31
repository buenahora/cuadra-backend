from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DormitoriosBucket, PeriodoReporte, SeccionReporte


class ReportCreate(BaseModel):
    """Informe PDF de corredor (S3C, data-model.md §9)."""

    titulo: str = Field(min_length=1, max_length=200)
    destinatario_nombre: str = Field(min_length=1, max_length=200)
    zone_id: str
    dormitorios_bucket: DormitoriosBucket
    periodo: PeriodoReporte = PeriodoReporte.doce_meses
    secciones_incluidas: list[SeccionReporte] = list(SeccionReporte)


class ReportOut(BaseModel):
    id: UUID
    generado_por: UUID
    titulo: str
    destinatario_nombre: str
    zone_id: str
    dormitorios_bucket: DormitoriosBucket
    periodo: PeriodoReporte
    secciones_incluidas: list[SeccionReporte]
    pdf_url: str
    generado_en: datetime
