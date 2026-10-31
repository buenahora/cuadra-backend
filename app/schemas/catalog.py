from pydantic import BaseModel


class Zone(BaseModel):
    """Barrio. `tiene_estadisticas` reemplaza la lista hardcodeada de 6/15
    barrios del prototipo (data-model.md §5) -- lo calcula el motor de
    mercado, no un flag manual."""

    id: str
    nombre: str
    ciudad: str
    tiene_estadisticas: bool = False
    cantidad_avisos: int = 0

    model_config = {"from_attributes": True}


class Amenity(BaseModel):
    id: str
    nombre: str

    model_config = {"from_attributes": True}


class Garantia(BaseModel):
    id: str
    nombre: str

    model_config = {"from_attributes": True}
