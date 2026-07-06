from fastapi import APIRouter, HTTPException

from docent.schemas.artwork_schemas import (
    Artwork,
    ArtworkDatasetSummaryResponse,
    ArtworkListResponse,
    ArtworkSearchResponse,
)
from docent.services.artwork_service import (
    get_all_artworks,
    get_artwork_dataset_summary,
    get_painting_by_index,
    search_artworks,
)

router = APIRouter()

@router.get("/api/artworks", response_model=ArtworkListResponse)
def list_artworks():
    artworks = get_all_artworks()
    return ArtworkListResponse(artworks=artworks)

@router.get("/api/artworks/summary", response_model=ArtworkDatasetSummaryResponse)
def read_artwork_dataset_summary():
    summary = get_artwork_dataset_summary()
    return ArtworkDatasetSummaryResponse(**summary)

@router.get("/api/artworks/search", response_model=ArtworkSearchResponse)
def search_list_artworks(query: str):
    results = search_artworks(query)
    return ArtworkSearchResponse(query=query, results=results)

@router.get("/api/artworks/{painting_index}", response_model=Artwork)
def get_artwork(painting_index: int):
    artwork = get_painting_by_index(painting_index)

    if artwork is None:
        raise HTTPException(
            status_code=404, 
            detail="Artwork not found"
        )
    
    return artwork