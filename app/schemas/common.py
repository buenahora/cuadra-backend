from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, computed_field

T = TypeVar("T")


class EstadoPublicacion(str, Enum):
    """Visibilidad del aviso -- ¿se muestra en búsquedas? (data-model.md §3)."""

    activo = "activo"
    pausado = "pausado"
    archivado = "archivado"


class EstadoComercial(str, Enum):
    """Etapa comercial real de la propiedad, independiente de su
    visibilidad (data-model.md §3, resuelve la inconsistencia 2F vs 3B)."""

    disponible = "disponible"
    en_proceso = "en_proceso"
    alquilada = "alquilada"


class Amueblado(str, Enum):
    si = "si"
    no = "no"
    parcial = "parcial"


class DormitoriosBucket(str, Enum):
    cero = "0"
    uno = "1"
    dos = "2"
    tres_mas = "3+"


class MetrajeBucket(str, Enum):
    menos_40 = "<40"
    entre_40_60 = "40-60"
    entre_60_80 = "60-80"
    mas_80 = ">80"


class NivelMercado(str, Enum):
    below = "below"
    in_range = "in"
    above = "above"


class PeriodoReporte(str, Enum):
    tres_meses = "3m"
    seis_meses = "6m"
    doce_meses = "12m"


class SeccionReporte(str, Enum):
    precio_mediano = "precio_mediano"
    rango_de_precios = "rango_de_precios"
    evolucion_historica = "evolucion_historica"
    avisos_comparables = "avisos_comparables"


class SortOrder(str, Enum):
    recientes = "recientes"
    precio_asc = "precio_asc"
    precio_desc = "precio_desc"


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int

    @computed_field
    @property
    def pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size
