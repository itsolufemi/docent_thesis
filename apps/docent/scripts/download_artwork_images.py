
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "apps" / "docent" / "data"
ARTWORKS = DATA / "artworks.json"
IMAGES = DATA / "images"

IMAGES.mkdir(parents=True, exist_ok=True)

artworks = json.loads(ARTWORKS.read_text(encoding="utf-8"))

for artwork in artworks:
    painting_id = artwork["painting_index"]
    url = artwork.get("image_url")

    if not url:
        print(f"SKIPPED {painting_id}: no image URL")
        continue

    try:
        request = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urlopen(request, timeout=30) as response:
            data = response.read(12 * 1024 * 1024 + 1)

        if len(data) > 12 * 1024 * 1024:
            raise ValueError("Image exceeds 12 MB")

        if data.startswith(b"\xff\xd8\xff"):
            extension = ".jpg"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = ".png"
        else:
            raise ValueError("Response is not a JPEG or PNG image")

        destination = IMAGES / f"{painting_id}{extension}"
        destination.write_bytes(data)

        print(f"OK: {painting_id} - {artwork['title']}")

    except Exception as error:
        print(f"FAILED: {painting_id} - {error}")
