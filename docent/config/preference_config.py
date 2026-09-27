from __future__ import annotations


DEFAULT_INTERESTS = {
    "interpretation": 0.20,
    "technique": 0.20,
    "historical_social_context": 0.20,
    "narrative": 0.20,
    "artist_context": 0.20,
}

# Experimental tuning value. A strong signal adds this amount to its
# category before all interest weights are renormalised.
INTEREST_UPDATE_RATE = 0.25

INTEREST_SIGNAL_MULTIPLIERS = {
    "weak": 0.25,
    "medium": 0.50,
    "strong": 1.00,
}
