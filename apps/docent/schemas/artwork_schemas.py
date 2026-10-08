from pydantic import BaseModel, Field


class Artwork(BaseModel):
    painting_index: int
    title: str
    artist: str | None = None
    school: str | None = None
    date: str | None = None

    object_type: str | None = None
    medium: str | None = None

    room: str | None = None
    room_index: int | None = None
    room_name: str | None = None

    description: str
    provenance: str | None = None

    image_url: str | None = None
    inventory_number: str | None = None
    url: str | None = None

    themes: list[str] = Field(default_factory=list)


class ArtworkListResponse(BaseModel):
    artworks: list[Artwork]


class ArtworkSearchResponse(BaseModel):
    query: str
    results: list[Artwork]

class ArtworkDatasetSummaryResponse(BaseModel):
    total_artworks: int
    rooms: list[str]
    schools: list[str]
    object_types: list[str]