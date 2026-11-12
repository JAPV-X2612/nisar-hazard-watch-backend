from enum import StrEnum


class FireContextStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "notConfigured"


class FirmsProduct(StrEnum):
    VIIRS_SNPP_SP = "VIIRS_SNPP_SP"
    VIIRS_SNPP_NRT = "VIIRS_SNPP_NRT"
    VIIRS_NOAA20_SP = "VIIRS_NOAA20_SP"
    VIIRS_NOAA20_NRT = "VIIRS_NOAA20_NRT"


FIRMS_AREA_PATH = "/api/area/csv/{map_key}/{product}/{west},{south},{east},{north}/{days}/{start}"
FIRMS_MAX_DAY_RANGE = 5
FIRMS_MAX_WINDOW_DAYS = 40
FIRMS_CONCURRENCY = 4
FIRMS_BODY_LOG_CHARS = 80
FIRMS_SERVER_ERROR_FLOOR = 500
FIRMS_CSV_FIRST_COLUMN = "latitude"
FIRMS_DATETIME_FORMAT = "%Y-%m-%d %H%M"
FIRMS_LOW_CONFIDENCE = "low"

COLUMN_LATITUDE = "latitude"
COLUMN_LONGITUDE = "longitude"
COLUMN_DATE = "acq_date"
COLUMN_TIME = "acq_time"
COLUMN_SATELLITE = "satellite"
COLUMN_CONFIDENCE = "confidence"
COLUMN_FRP = "frp"

FIRE_CONTEXT_SOURCE = "NASA FIRMS · VIIRS 375 m active-fire detections"
WILDFIRE_LIMITATION = (
    "A radar change over burnt land is consistent with vegetation loss; "
    "it does not establish a fire as the cause."
)
NOTE_DETECTIONS = (
    "Independent thermal evidence, separate from the radar: active-fire detections inside the "
    "area between the two radar passes. It does not establish the cause of the radar change "
    "and no burned area is reported."
)
NOTE_NO_DETECTIONS = (
    "No active-fire detections were found inside the area between the two radar passes. "
    "Thermal sensors miss small, short or cloud-covered fires, so this does not rule a fire out."
)
NOTE_UNAVAILABLE = "Fire context could not be retrieved, so the verdict is radar-only."
NOTE_NOT_CONFIGURED = "Fire context is not configured on this server, so the verdict is radar-only."
NOTE_NO_ASSESSMENT_WINDOW = (
    "Fire context needs a baseline pass and a target pass; the verdict is radar-only."
)
NOTE_TRUNCATED_WINDOW = " Only the last {days} days before the target pass were searched."
