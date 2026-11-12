DEFAULT_GEOCODER_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's policy asks for an identifying agent; the repository is the contact.
GEOCODER_USER_AGENT = (
    "NISAR-Hazard-Watch/{version} (+https://github.com/JAPV-X2612/nisar-hazard-watch-backend)"
)
GEOCODER_LANGUAGE = "en"
GEOCODER_RESPONSE_FORMAT = "jsonv2"
PLACES_ATTRIBUTION = "© OpenStreetMap contributors"
MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 100
DEFAULT_PLACE_LIMIT = 6
MAX_PLACE_LIMIT = 10
CACHE_TTL_SECONDS = 86_400.0
EMPTY_CACHE_TTL_SECONDS = 3_600.0
CACHE_MAX_ENTRIES = 1024
# Nominatim allows one request per second at most.
PROVIDER_MIN_INTERVAL_SECONDS = 1.1
MAX_QUEUE_WAIT_SECONDS = 6.0
