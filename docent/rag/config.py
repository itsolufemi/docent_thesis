from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCENT_DATA_DIRECTORY = REPOSITORY_ROOT / "docent" / "data"
DOCENT_ARTWORKS_PATH = DOCENT_DATA_DIRECTORY / "artworks.json"
DOCENT_VECTOR_STORE_DIRECTORY = (
    DOCENT_DATA_DIRECTORY / "vector_store"
)
DOCENT_VECTOR_METADATA_PATH = (
    DOCENT_VECTOR_STORE_DIRECTORY
    / "docent_vector_index.json"
)
DOCENT_VECTOR_EMBEDDINGS_PATH = (
    DOCENT_VECTOR_STORE_DIRECTORY
    / "docent_vector_embeddings.npy"
)
