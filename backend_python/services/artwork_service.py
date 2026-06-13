import json
from pathlib import Path

from schemas.artwork_schemas import Artwork

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ARTWORKS_FILE = DATA_DIR / "artworks.json"

def load_artworks() -> list[Artwork]:
    with open(ARTWORKS_FILE, "r", encoding="utf-8") as file:
        artworks_data = json.load(file)
    
    return [Artwork(**artwork) for artwork in artworks_data]

def get_all_artworks() -> list[Artwork]:
    return load_artworks()

def get_painting_by_index(painting_index: int) -> Artwork | None:
    artworks = load_artworks()

    for artwork in artworks:
        if artwork.painting_index == painting_index:
            return artwork
        
    return None

def search_artworks(query: str) -> list[Artwork]:
    artworks = load_artworks()
    normalized_query = query.lower().strip()
    results = []

    for artwork in artworks:
        searchable_text = " ".join(
            [
                artwork.title,
                artwork.artist or "",
                artwork.description or "",
                artwork.room or "",
                artwork.period or "",
                " ".join(artwork.themes)
            ]
        ).lower()

        if normalized_query in searchable_text:
            results.append(artwork)
        
    return results