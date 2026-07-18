import sys
from pathlib import Path
from time import perf_counter

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[2]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from config import settings
from docent.services.docent_retrieval_adapter import get_docent_retrieval_chunks
from extensions.retrieval.services.embedding_service import embed_indexed_chunks
from extensions.retrieval.services.index_service import build_retrieval_index
from extensions.retrieval.services.vector_store_service import save_vector_store


def build_docent_vector_store() -> None:
    started_at = perf_counter()

    print("Loading Docent retrieval chunks...")
    chunks = get_docent_retrieval_chunks()
    print(f"Loaded {len(chunks)} retrieval chunks.")

    print("Building retrieval index...")
    indexed_chunks = build_retrieval_index(chunks)
    print(f"Built {len(indexed_chunks)} indexed chunks.")

    print("Generating embeddings. This may take some time...")
    chunk_embeddings = embed_indexed_chunks(indexed_chunks)
    print(f"Generated {len(chunk_embeddings)} embeddings.")

    print("Saving vector store...")
    save_vector_store(
        indexed_chunks=indexed_chunks,
        chunk_embeddings=chunk_embeddings,
        metadata_path=settings.docent_vector_metadata_path,
        embeddings_path=settings.docent_vector_embeddings_path,
    )

    print("Vector store saved successfully.")
    print("Metadata:", settings.docent_vector_metadata_path)
    print("Embeddings:", settings.docent_vector_embeddings_path)
    print("Total time:", round(perf_counter() - started_at, 2), "seconds")


if __name__ == "__main__":
    build_docent_vector_store()
