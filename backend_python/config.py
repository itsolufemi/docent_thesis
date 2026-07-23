import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

class Settings():
    backend_root: Path = Path(__file__).resolve().parent

    backend_host: str = os.getenv("BACKEND_HOST", "127.0.0.1")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))
    environment: str = os.getenv("ENVIRONMENT", "development")

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")
    ollama_embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    ollama_trp_model: str = os.getenv("OLLAMA_TRP_MODEL", "")
    ollama_classifier_model: str = os.getenv("OLLAMA_CLASSIFIER_MODEL", "")

    whisper_model: str = os.getenv("WHISPER_MODEL", "base.en")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cpu")
    whisper_compute_type: str = os.getenv(
        "WHISPER_COMPUTE_TYPE",
        "int8",
    )

    docent_vector_store_directory: Path = (
        backend_root / "docent" / "data" / "vector_store"
    )
    docent_vector_metadata_path: Path = (
        docent_vector_store_directory / "docent_vector_index.json"
    )
    docent_vector_embeddings_path: Path = (
        docent_vector_store_directory / "docent_vector_embeddings.npy"
    )

    class Config:
        env_file = ".env"

settings = Settings()
