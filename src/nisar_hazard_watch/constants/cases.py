CASES_PATH = "/v2/cases"
CASES_CACHE_TTL_SECONDS = 600.0
CASE_ID_PATTERN = r"^[a-z0-9_-]{1,40}$"
CASES_UNAVAILABLE_DETAIL = "the known cases are unavailable"

# Words that mark a value the science has not validated (area in hectares, probability, depth,
# displacement in cm, cause); a key made of any of them is never relayed.
FORBIDDEN_EVIDENCE_WORDS = frozenset({"ha", "probability", "depth", "cm", "causal"})
