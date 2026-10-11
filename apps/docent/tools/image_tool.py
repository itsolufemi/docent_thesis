"""Docent configuration of the framework's generic image-loading tool."""

from core_engine.tools.image_tool import create_image_tool
from apps.docent.rag.config import DOCENT_DATA_DIRECTORY
from apps.docent.tools.docent_tool_registry import docent_tool_registry


DOCENT_LOAD_IMAGE_TOOL, load_image = create_image_tool(
    image_root=DOCENT_DATA_DIRECTORY,
    description=(
        "Load an image of an artwork when visual inspection is required to "
        "answer the visitor. Use only an exact image_reference returned by "
        "retrieve_knowledge; do not invent a path or call this tool when "
        "existing textual knowledge is sufficient. The image is made visible "
        "in your next response-generation round."
    ),
)

docent_tool_registry.register(DOCENT_LOAD_IMAGE_TOOL, load_image)
