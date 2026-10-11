"""Docent-specific retrieval configuration and transformations.

Keep package initialization lightweight. In particular, importing a
submodule such as ``apps.docent.rag.config`` must not eagerly import the
document builder, because the builder depends on the retrieval adapter and
the adapter's image service depends on that config module.
"""

from typing import Any


__all__ = ["build_artwork_document"]


def __getattr__(name: str) -> Any:
    """Load the public document builder without creating an import cycle."""
    if name == "build_artwork_document":
        from apps.docent.rag.document_builder import (
            build_artwork_document,
        )

        return build_artwork_document

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )
