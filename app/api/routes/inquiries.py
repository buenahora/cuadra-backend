import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_inquiries_repo, get_listings_repo
from app.repositories.base import InquiriesRepository, ListingsRepository
from app.repositories.models import InquiryRow, UserRow
from app.schemas.inquiry import InquiryCreate, InquiryOut, InquiryRespond

router = APIRouter(tags=["inquiries"])


def _to_out(row: InquiryRow) -> InquiryOut:
    return InquiryOut(
        id=row.id,
        listing_id=row.listing_id,
        remitente_user_id=row.remitente_user_id,
        nombre=row.nombre,
        email=row.email,
        telefono=row.telefono,
        fecha_mudanza=row.fecha_mudanza,
        mensaje=row.mensaje,
        respuesta=row.respuesta,
        creado_en=row.creado_en,
        respondido_en=row.respondido_en,
    )


@router.post(
    "/listings/{listing_id}/inquiries", response_model=InquiryOut, status_code=status.HTTP_201_CREATED
)
def create_inquiry(
    listing_id: uuid.UUID,
    payload: InquiryCreate,
    current_user: UserRow = Depends(get_current_user),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    inquiries_repo: InquiriesRepository = Depends(get_inquiries_repo),
) -> InquiryOut:
    """Formulario de contacto (S1D) -- requiere sesión, igual que en el
    prototipo (se pide login recién al tocar 'Contactar al propietario')."""
    if listings_repo.get(listing_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aviso no encontrado")
    inquiry = inquiries_repo.create(listing_id, current_user.id, payload.model_dump())
    return _to_out(inquiry)


@router.get("/listings/{listing_id}/inquiries", response_model=list[InquiryOut])
def list_listing_inquiries(
    listing_id: uuid.UUID,
    current_user: UserRow = Depends(get_current_user),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    inquiries_repo: InquiriesRepository = Depends(get_inquiries_repo),
) -> list[InquiryOut]:
    """Consultas recibidas (S2G) -- solo el propietario/publicador del
    aviso puede verlas."""
    listing = listings_repo.get(listing_id)
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aviso no encontrado")
    if listing.publicado_por != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No sos el publicador de este aviso")
    return [_to_out(i) for i in inquiries_repo.list_by_listing(listing_id)]


@router.get("/users/me/inquiries", response_model=list[InquiryOut])
def my_sent_inquiries(
    current_user: UserRow = Depends(get_current_user),
    inquiries_repo: InquiriesRepository = Depends(get_inquiries_repo),
) -> list[InquiryOut]:
    """Consultas enviadas por el inquilino (historial propio)."""
    return [_to_out(i) for i in inquiries_repo.list_by_user(current_user.id)]


@router.patch("/inquiries/{inquiry_id}", response_model=InquiryOut)
def respond_inquiry(
    inquiry_id: uuid.UUID,
    payload: InquiryRespond,
    current_user: UserRow = Depends(get_current_user),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    inquiries_repo: InquiriesRepository = Depends(get_inquiries_repo),
) -> InquiryOut:
    """Responder desde la plataforma (S2G)."""
    inquiry = inquiries_repo.get(inquiry_id)
    if inquiry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consulta no encontrada")
    listing = listings_repo.get(inquiry.listing_id)
    if listing is None or listing.publicado_por != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No sos el publicador de este aviso")
    updated = inquiries_repo.respond(inquiry_id, payload.respuesta)
    return _to_out(updated)
