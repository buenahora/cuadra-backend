import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_favorites_repo, get_listings_repo, get_zones_repo
from app.repositories.base import FavoritesRepository, ListingsRepository, ZonesRepository
from app.repositories.models import UserRow
from app.schemas.catalog import Zone
from app.schemas.listing import ListingSummary
from app.services import listing_view

router = APIRouter(tags=["favorites"])


@router.post("/listings/{listing_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
def add_favorite(
    listing_id: uuid.UUID,
    current_user: UserRow = Depends(get_current_user),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    favorites_repo: FavoritesRepository = Depends(get_favorites_repo),
) -> None:
    if listings_repo.get(listing_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aviso no encontrado")
    favorites_repo.add(current_user.id, listing_id)


@router.delete("/listings/{listing_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(
    listing_id: uuid.UUID,
    current_user: UserRow = Depends(get_current_user),
    favorites_repo: FavoritesRepository = Depends(get_favorites_repo),
) -> None:
    favorites_repo.remove(current_user.id, listing_id)


@router.get("/users/me/favorites", response_model=list[ListingSummary])
def my_favorites(
    current_user: UserRow = Depends(get_current_user),
    favorites_repo: FavoritesRepository = Depends(get_favorites_repo),
    listings_repo: ListingsRepository = Depends(get_listings_repo),
    zones_repo: ZonesRepository = Depends(get_zones_repo),
) -> list[ListingSummary]:
    favorite_rows = favorites_repo.list_by_user(current_user.id)
    index = listing_view.build_market_index(listings_repo)
    zones = {z.id: Zone.model_validate(z) for z in zones_repo.list_all()}
    out = []
    for fav in favorite_rows:
        listing = listings_repo.get(fav.listing_id)
        if listing is None:
            continue
        out.append(listing_view.to_summary(listing, zones[listing.zone_id], index))
    return out
