import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    backend_host: str = os.getenv("BACKEND_HOST", "127.0.0.1")
    backend_port: int = int(os.getenv("BACKEND_PORT", 8000))
    environment : str = os.getenv("ENVIRONMENT", "development")

settings = Settings()