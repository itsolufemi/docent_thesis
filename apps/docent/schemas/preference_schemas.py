from __future__ import annotations

from math import isclose
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.docent.config.preference_config import (
    DEFAULT_INTERESTS,
)


DocentInterestCategory = Literal[
    "interpretation",
    "technique",
    "historical_social_context",
    "narrative",
    "artist_context",
]
DocentInterestStrength = Literal["weak", "medium", "strong"]


class DocentPreferenceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interests: dict[DocentInterestCategory, float] = Field(
        default_factory=lambda: dict(DEFAULT_INTERESTS)
    )

    @model_validator(mode="after")
    def validate_interest_distribution(self) -> DocentPreferenceState:
        expected = set(DEFAULT_INTERESTS)
        actual = set(self.interests)

        if actual != expected:
            raise ValueError(
                "Interest weights must contain exactly the configured "
                "Docent interest categories."
            )

        if any(value < 0 for value in self.interests.values()):
            raise ValueError("Interest weights cannot be negative.")

        if not isclose(
            sum(self.interests.values()),
            1.0,
            rel_tol=0,
            abs_tol=1e-9,
        ):
            raise ValueError("Interest weights must sum to 1.0.")

        return self


class DocentInterestSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: DocentInterestCategory
    strength: DocentInterestStrength


class DocentPreferenceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interest_signals: list[DocentInterestSignal] = Field(
        default_factory=list
    )

    def is_empty(self) -> bool:
        return not self.interest_signals
