import json
from pathlib import Path

from schemas.artwork_schemas import Artwork

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ARTWORKS_FILE = DATA_DIR / "superlist.json"

_artworks_cache: list[Artwork] | None = None

def normalise_artwork_record(raw_artwork: dict) -> Artwork:
    return Artwork(
        painting_index=raw_artwork["painting_index"],
        title=raw_artwork.get("title", "untitled"),

        artist=raw_artwork.get("artist"),
        school=raw_artwork.get("school"),
        date=raw_artwork.get("date"),

        object_type=raw_artwork.get("object_type"),
        medium=raw_artwork.get("medium"),

        room=raw_artwork.get("room"),
        room_index=raw_artwork.get("room_index"),
        room_name=raw_artwork.get("room_name"),

        description=raw_artwork.get("description"),
        provenance=raw_artwork.get("provenance"),

        image_url=raw_artwork.get("image_url"),
        inventory_number=raw_artwork.get("inventory_number"),
        url=raw_artwork.get("url"),

        themes=raw_artwork.get("themes") or [],
    )

def load_artworks(force_reload: bool = False) -> list[Artwork]:
    global _artworks_cache

    if _artworks_cache is not None and force_reload is False:
        return _artworks_cache

    with open(ARTWORKS_FILE, "r", encoding="utf-8") as file:
        artworks_data = json.load(file)

    _artworks_cache = [
        normalise_artwork_record(artwork)
        for artwork in artworks_data
    ]

    return _artworks_cache

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
                artwork.title or "",
                artwork.artist or "",
                artwork.school or "",
                artwork.date or "",
                artwork.object_type or "",
                artwork.medium or "",
                artwork.room or "",
                artwork.room_name or "",
                artwork.description or "",
                artwork.provenance or "",
                artwork.inventory_number or "",
                " ".join(artwork.themes),
            ]
        ).lower()

        if normalized_query in searchable_text:
            results.append(artwork)
        
    return results

def get_artwork_dataset_summary() -> dict:
    artworks = load_artworks()

    rooms = sorted(
        {
            artwork.room_name or artwork.room
            for artwork in artworks
            if artwork.room_name or artwork.room
        }
    )

    schools = sorted(
        {
            artwork.school
            for artwork in artworks
            if artwork.school
        }
    )

    object_types = sorted(
        {
            artwork.object_type
            for artwork in artworks
            if artwork.object_type
        }
    )

    return {
        "total_artworks": len(artworks),
        "rooms": rooms,
        "schools": schools,
        "object_types": object_types,
    }