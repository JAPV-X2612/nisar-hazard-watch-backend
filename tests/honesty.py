import re
from typing import Any

FORBIDDEN_WORDS = frozenset({"ha", "probability", "depth", "cm", "causal"})
WORD = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def forbidden_keys(payload: Any, path: str = "") -> list[str]:
    """Every key, at any depth, made of a word the science has not validated.

    Split into words because a substring test would flag shape, sha256, phase or change.
    """
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}"
            if {word.lower() for word in WORD.findall(str(key))} & FORBIDDEN_WORDS:
                found.append(here)
            found.extend(forbidden_keys(value, here))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(forbidden_keys(item, f"{path}[]"))
    return found
