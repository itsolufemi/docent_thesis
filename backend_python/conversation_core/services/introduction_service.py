from collections.abc import Callable

from conversation_core.schemas.introduction_schemas import (
    IntroductionDefinition,
)


IntroductionProvider = Callable[
    [],
    IntroductionDefinition | None,
]
