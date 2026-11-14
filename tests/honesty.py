import re
from typing import Any

# Kept apart from the production denylist on purpose, and wider: a copy could not catch its gaps.
FORBIDDEN_WORDS = frozenset(
    {
        "accuracy",
        "acre",
        "acres",
        "affected",
        "cm",
        "damage",
        "damaged",
        "detected",
        "detection",
        "flooded",
        "forecast",
        "ha",
        "km",
        "km2",
        "likelihood",
        "m2",
        "mm",
        "risk",
        "severity",
        "submerged",
        "subsidence",
        "uplift",
        "velocity",
        "volume",
    }
)
# Any word that starts with one of these: probability, probabilities, inundated, hectares...
FORBIDDEN_PREFIXES = (
    "area",
    "attribut",
    "caus",
    "deform",
    "depth",
    "displac",
    "hectar",
    "inundat",
    "probab",
)
WORD = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def _is_forbidden(key: str) -> bool:
    words = {word.lower() for word in WORD.findall(key)}
    return bool(words & FORBIDDEN_WORDS) or any(
        word.startswith(FORBIDDEN_PREFIXES) for word in words
    )


def forbidden_keys(payload: Any, path: str = "") -> list[str]:
    """Every key, at any depth, made of a word the science has not validated.

    Split into words because a substring test would flag shape, sha256, phase or change.
    """
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}"
            if _is_forbidden(str(key)):
                found.append(here)
            found.extend(forbidden_keys(value, here))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(forbidden_keys(item, f"{path}[]"))
    return found
