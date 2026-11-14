from enum import StrEnum

CASES_PATH = "/v2/cases"
CASES_CACHE_TTL_SECONDS = 600.0
# After a failed read, the gateway is left alone this long (a cold /v2/cases can take 12 s).
CASES_RETRY_AFTER_SECONDS = 60.0
CASE_ID_PATTERN = r"^[a-z0-9_-]{1,40}$"
CASES_UNAVAILABLE_DETAIL = "the known cases are unavailable"
# Never relay a case silently without caveats: used when the gateway sends no limitations.
CASE_FALLBACK_LIMITATIONS = (
    "Diagnostic evidence measured ahead of time from NISAR L-band radar, not a validated "
    "classifier.",
    "The analysis service sent no limitations for this case; read every value with care.",
    "No forecast, probability, cause, area in hectares or displacement is reported.",
)

# Words that mark a value the science has not validated (area, probability, depth, displacement,
# cause, and their units); a key made of any of them is never relayed.
FORBIDDEN_EVIDENCE_WORDS = frozenset(
    {
        "area",
        "attribution",
        "causal",
        "cause",
        "cm",
        "depth",
        "displacement",
        "flooded",
        "ha",
        "hectares",
        "inundated",
        "inundation",
        "km2",
        "mm",
        "probabilities",
        "probability",
    }
)


class CaseStatus(StrEnum):
    """The values the gateway sends today; status stays a free string so a new one still relays."""

    PARTIAL = "partial"
    COMPLETE = "complete"
    NOT_DISPLACEMENT_READY = "not_displacement_ready"
    EVALUATED = "evaluated"
