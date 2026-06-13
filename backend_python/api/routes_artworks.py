from fastapi import APIRouter, HTTPException

from schemas.artwork_schemas import (
    Artwork,
    ArtworkListResponse,
    ArtworkSearchResponse
)

from services.artwork_service import (
    get_all_artworks,
    get_painting_by_index,
    search_artworks
)

router = APIRouter()

@router.get("/api/artworks", response_model=ArtworkListResponse)
def list_artworks():
    artworks = get_all_artworks()
    return ArtworkListResponse(artworks=artworks)

@router.get("/api/artworks/search", response_model=ArtworkSearchResponse)
def search_list_artworks(query: str):
    results = search_artworks(query)
    return ArtworkSearchResponse(query=query, results=results)

@router.get("/api/artworks/{artwork_id}", response_model=Artwork)
def get_artwork(artwork_id: int):
    artwork = get_painting_by_index(artwork_id)

    if artwork is None:
        raise HTTPException(
            status_code=404, 
            detail="Artwork not found"
        )
    
    return artwork