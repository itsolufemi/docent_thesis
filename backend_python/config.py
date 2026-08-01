import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _read_bool(name: str, default: bool = False) -> bool:
    value = _optional_boolean(name)

    if value is None:
        return default

    return value


def _optional_boolean(
    name: str,
) -> bool | None:
    raw_value = os.getenv(name)

    if raw_value is None:
        return None

    value = raw_value.strip().lower()

    if value in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if value in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    return None


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
    ollama_main_think: bool | None = (
        _optional_boolean(
            "OLLAMA_MAIN_THINK"
        )
    )

    whisper_model: str = os.getenv("WHISPER_MODEL", "base.en")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cpu")
    whisper_compute_type: str = os.getenv(
        "WHISPER_COMPUTE_TYPE",
        "int8",
    )
    whisper_no_speech_threshold: float = float(
        os.getenv(
            "WHISPER_NO_SPEECH_THRESHOLD",
            "0.6",
        )
    )

    whisper_log_prob_threshold: float = float(
        os.getenv(
            "WHISPER_LOG_PROB_THRESHOLD",
            "-1.0",
        )
    )

    warm_up_whisper_on_startup: bool = _read_bool(
        "WARM_UP_WHISPER_ON_STARTUP",
        True
    )

    transcription_backend: str = os.getenv(
        "TRANSCRIPTION_BACKEND",
        "whisper",
    ).strip().lower()

    moonshine_language: str = os.getenv(
        "MOONSHINE_LANGUAGE",
        "en",
    )

    moonshine_model_arch_raw: str = os.getenv(
        "MOONSHINE_MODEL_ARCH",
        "",
    ).strip()

    moonshine_model_arch: int | None = (
        int(moonshine_model_arch_raw)
        if moonshine_model_arch_raw
        else None
    )

    moonshine_update_interval: float = float(
        os.getenv(
            "MOONSHINE_UPDATE_INTERVAL",
            "0.2",
        )
    )

    warm_up_moonshine_on_startup: bool = _read_bool(
        "WARM_UP_MOONSHINE_ON_STARTUP",
        True,
    )

    smart_turn_enabled: bool = _read_bool(
        "SMART_TURN_ENABLED",
        False,
    )
    smart_turn_model_path: Path = (
        backend_root
        / os.getenv(
            "SMART_TURN_MODEL_PATH",
            "models/smart-turn-v3.2-cpu.onnx",
        )
    ).resolve()
    smart_turn_threshold: float = float(
        os.getenv("SMART_TURN_THRESHOLD", "0.50")
    )
    smart_turn_max_audio_seconds: float = float(
        os.getenv(
            "SMART_TURN_MAX_AUDIO_SECONDS",
            "8.0",
        )
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
