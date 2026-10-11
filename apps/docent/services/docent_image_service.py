"""Map Docent artwork IDs to image references under Docent's data root."""

from apps.docent.rag.config import DOCENT_DATA_DIRECTORY


def image_reference_for_painting(painting_index: int) -> str | None:
    """Return a portable reference only when a downloaded image exists."""
    if type(painting_index) is not int:
        return None
    image_dir = DOCENT_DATA_DIRECTORY / "images"
    for extension in (".jpg", ".jpeg", ".png", ".webp"):
        image = image_dir / f"{painting_index}{extension}"
        if image.is_file():
            return image.relative_to(DOCENT_DATA_DIRECTORY).as_posix()
    return None
