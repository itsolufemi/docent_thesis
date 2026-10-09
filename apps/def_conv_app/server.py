import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_ROOT = REPOSITORY_ROOT / "framework"

for import_root in (REPOSITORY_ROOT, FRAMEWORK_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

os.environ.setdefault("RUNTIME_LOG_APPLICATION", "core")

from app_factory import create_framework_app
from config import settings
from core_engine.default_profile_definition import (
    default_classifier_profile,
)
from core_engine.services.query_service import default_query_engine


def_conv_app = create_framework_app(
    title="Framework default conversation app",
    query_engine=default_query_engine,
    domain_profile=default_classifier_profile,
)
app = def_conv_app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.backend_host,
        port=settings.backend_port,
        log_level="info",
    )
