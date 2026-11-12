import re

GUNW_PRODUCT = "GUNW"
INSAR_OPERATION = "insar-pair"
COVERAGE_PATH = "/v2/coverage"
GUNW_NAME_PATTERN = r"^NISAR_L2_[A-Za-z0-9_]{1,170}$"
GUNW_TIMES = re.compile(r"_(\d{8})T\d{6}_\d{8}T\d{6}_(\d{8})T\d{6}_\d{8}T\d{6}_")
SERIES_KEY = re.compile(r"^(\d{3})_([AD])_(\d{3})_(\d{4})_([A-Z0-9]{2,4})$")
GUNW_DATE_FORMAT = "%Y%m%d"

DEFAULT_COHERENCE_THRESHOLD = 0.35
MIN_COHERENCE_THRESHOLD = 0.1
MAX_COHERENCE_THRESHOLD = 0.9
INSAR_WINDOW_KM = 5
INSAR_SCENES = 2
PAIR_WINDOW_DEFAULT_DAYS = 180
PAIR_WINDOW_MAX_DAYS = 366
INSAR_MINIMUM_DATES = 2

LAYER_TITLES = {
    "display_coherence_coherence": "Interferometric coherence",
    "display_wrapped_phase_rad_wrapped_phase_rad": "Wrapped phase",
}
INSAR_LIMITATIONS = (
    "Diagnostic evidence from the coherence and the wrapped phase of one NISAR L-band pair, "
    "not a validated displacement measurement.",
    "The phase is wrapped and not corrected for troposphere or ionosphere; no displacement is "
    "reported (losDisplacementCm is null).",
    "No forecast, probability, cause or affected area is reported.",
)
INSAR_WINDOW_LIMITATION = (
    f"Only a {INSAR_WINDOW_KM} km window around the centre of the area is measured."
)
INSAR_NO_DATA_DETAIL = "the pair holds no usable coherence at this point"
INSAR_FAILURE_DETAILS = {
    "archive_timeout": "the archive timed out while the pair was read",
    "archive_auth_unavailable": "the archive refused the credentials of the analysis service",
    "cache_integrity_error": "the analysis service found a damaged cached pair",
    "archive_read_failed": "the archive could not be read for this pair",
}
