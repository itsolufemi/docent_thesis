import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_ROOT = REPOSITORY_ROOT / "framework"

for import_root in (REPOSITORY_ROOT, FRAMEWORK_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

os.environ.setdefault("RUNTIME_LOG_APPLICATION", "docent")

from app_factory import create_framework_app
from apps.docent.api.routes_artworks import router as artworks_router
from apps.docent.api.routes_docent_embeddings import (
    router as docent_embeddings_router,
)
from apps.docent.api.routes_docent_index import router as docent_index_router
from apps.docent.api.routes_docent_retrieval import (
    router as docent_retrieval_router,
)
from apps.docent.api.routes_docent_vector import router as docent_vector_router
from apps.docent.config.docent_classifier_profile import (
    docent_classifier_profile,
)
from apps.docent.services.docent_query_service import (
    direct_docent_query_engine,
)
from apps.docent.services.docent_vector_retrieval_service import (
    warm_up_docent_retrieval,
)
from config import settings


docent_warm_up_operations = (
    (("Docent retrieval", warm_up_docent_retrieval),)
    if settings.warm_up_retrieval_on_startup
    else ()
)

app = create_framework_app(
    title="docent backend",
    query_engine=direct_docent_query_engine,
    domain_profile=docent_classifier_profile,
    application_routers=(
        artworks_router,
        docent_retrieval_router,
        docent_index_router,
        docent_embeddings_router,
        docent_vector_router,
    ),
    application_warm_up_operations=docent_warm_up_operations,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.backend_host,
        port=settings.backend_port,
        log_level="info",
    )
