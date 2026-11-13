import httpx
import pytest

from nisar_hazard_watch.adapters.geocoding.nominatim_geocoder import NominatimGeocoder
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.places import DEFAULT_GEOCODER_URL, GEOCODER_USER_AGENT

pytestmark = pytest.mark.live

TIMEOUT_SECONDS = 15.0
PUNJAB_LONGITUDE_RANGE = (73.0, 74.0)
PUNJAB_LATITUDE_RANGE = (32.0, 33.0)


async def test_the_real_provider_finds_qadirabad_in_punjab() -> None:
    # Arrange
    headers = {"User-Agent": GEOCODER_USER_AGENT.format(version=Settings().version)}
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, headers=headers) as client:
        geocoder = NominatimGeocoder(client=client, base_url=DEFAULT_GEOCODER_URL)

        # Act
        places = await geocoder.search(query="Qadirabad, Punjab", limit=3)

    # Assert
    assert places
    longitude, latitude = places[0].point
    assert PUNJAB_LONGITUDE_RANGE[0] < longitude < PUNJAB_LONGITUDE_RANGE[1]
    assert PUNJAB_LATITUDE_RANGE[0] < latitude < PUNJAB_LATITUDE_RANGE[1]
    assert places[0].bbox is not None
