import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    backend_host: str = os.getenv("BACKEND_HOST", "127.0.0.1")
    backend_port: int = int(os.getenv("BACKEND_PORT", 8000))
    environment: str = os.getenv("ENVIRONMENT", "development")

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")

settings = Settings()