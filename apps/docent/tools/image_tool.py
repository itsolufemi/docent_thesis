"""Docent configuration of the framework's generic image-loading tool."""

from core_engine.tools.image_tool import create_image_tool
from apps.docent.rag.config import DOCENT_DATA_DIRECTORY
from apps.docent.tools.docent_tool_registry import docent_tool_registry


DOCENT_IMAGE_REFERENCE_DESCRIPTION = (
    "Relative path to an artwork image, not a painting identifier. "
    "First copy the exact 'image_reference' supplied in retrieve_knowledge "
    "evidence, e.g. 'images/802.jpg'. If that path is not present in the "
    "current context but an established artwork reference is available as "
    "'painting:N', construct 'images/N.jpg' (e.g. 'painting:802' means "
    "'images/802.jpg'). Never pass 'painting:802' itself; do not invent an "
    "artwork index or guess a file extension when evidence specifies one. "
    "A constructed path may be missing; heed the tool's error if so."
)

DOCENT_IMAGE_TOOL_DESCRIPTION = (
    "Inspect an artwork reproduction when answering requires visual evidence. "
    "This includes counting people or objects; identifying colours, motifs, "
    "flowers, clothing patterns, arrangements, relative positions or other "
    "fine visual details not established by the catalogue. For instance, "
    "'How many figures are in the Venus painting?' and 'What flowers are "
    "printed on Mrs Hoare's dress?' warrant image inspection. "
    "If the visitor asks about history, provenance, artist or other facts "
    "already established in text, use retrieval instead; do not load an "
    "image unnecessarily. For a newly named artwork, retrieve its identity "
    "and image_reference first. For follow-ups, use the established artwork "
    "reference or image_reference from previous turns without redundant "
    "retrieval. Use the exact image_reference from retrieve_knowledge when "
    "available; otherwise, for a known 'painting:N' reference, construct "
    "'images/N.jpg'. The argument MUST be a path such as 'images/802.jpg', "
    "NEVER 'painting:802'. If loading fails, do not claim to have seen the "
    "image or replace missing visual evidence with a fabricated observation. "
    "After successful loading, inspect the attached image and answer the "
    "visitor's specific question directly, qualifying details you cannot "
    "distinguish in the reproduction."
)

DOCENT_LOAD_IMAGE_TOOL, load_image = create_image_tool(
    image_root=DOCENT_DATA_DIRECTORY,
    description=DOCENT_IMAGE_TOOL_DESCRIPTION,
    reference_description=DOCENT_IMAGE_REFERENCE_DESCRIPTION,
)

docent_tool_registry.register(DOCENT_LOAD_IMAGE_TOOL, load_image)
