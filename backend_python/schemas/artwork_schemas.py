from pydantic import BaseModel


class Artwork(BaseModel):
    painting_index: int
    title: str
    artist: str | None = None
    date: str | None = None
    room: str | None = None
    description: str
    themes: list[str] = []
    period: str | None = None
    medium: str | None = None
    source: str | None = None


class ArtworkListResponse(BaseModel):
    artworks: list[Artwork]


class ArtworkSearchResponse(BaseModel):
    query: str
    results: list[Artwork]