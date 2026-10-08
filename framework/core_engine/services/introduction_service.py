from collections.abc import Callable

from core_engine.schemas.introduction_schemas import (
    IntroductionDefinition,
)


IntroductionProvider = Callable[
    [],
    IntroductionDefinition | None,
]
