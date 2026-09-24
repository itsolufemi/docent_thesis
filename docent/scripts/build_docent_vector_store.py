import sys
from pathlib import Path
from time import perf_counter

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PYTHON_ROOT = REPOSITORY_ROOT / "backend_python"

for import_root in (REPOSITORY_ROOT, BACKEND_PYTHON_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from conversation_core.rag.build_vector_store import build_vector_store
from docent.rag.config import (
    DOCENT_ARTWORKS_PATH,
    DOCENT_VECTOR_EMBEDDINGS_PATH,
    DOCENT_VECTOR_METADATA_PATH,
    DOCENT_VECTOR_STORE_DIRECTORY,
)
from docent.rag.document_builder import build_artwork_document


def build_docent_vector_store() -> None:
    started_at = perf_counter()

    print("Building Docent vector store...")
    indexed_chunks, chunk_embeddings = build_vector_store(
        input_path=DOCENT_ARTWORKS_PATH,
        output_path=DOCENT_VECTOR_STORE_DIRECTORY,
        document_builder=build_artwork_document,
        metadata_filename=(
            DOCENT_VECTOR_METADATA_PATH.name
        ),
        embeddings_filename=(
            DOCENT_VECTOR_EMBEDDINGS_PATH.name
        ),
    )
    print(f"Built {len(indexed_chunks)} indexed chunks.")
    print(f"Generated {len(chunk_embeddings)} embeddings.")

    print("Vector store saved successfully.")
    print("Metadata:", DOCENT_VECTOR_METADATA_PATH)
    print("Embeddings:", DOCENT_VECTOR_EMBEDDINGS_PATH)
    print("Total time:", round(perf_counter() - started_at, 2), "seconds")


if __name__ == "__main__":
    build_docent_vector_store()
