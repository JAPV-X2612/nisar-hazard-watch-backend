import math

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import shape

from nisar_hazard_watch.constants.sar import (
    AOI_SIDE_KM,
    IDEAL_NATIVE_PIXELS,
    MAX_VERTICES,
    AoiKind,
)
from nisar_hazard_watch.exceptions.geometry_errors import AreaTooLargeError, InvalidGeometryError
from nisar_hazard_watch.utils.geometry import aoi_from_geojson, aoi_from_point

QADIRABAD_LON, QADIRABAD_LAT = 73.713, 32.329
EXPECTED_SQUARE_KM2 = AOI_SIDE_KM**2
AREA_TOLERANCE_KM2 = 0.5


def _polygon(*ring: tuple[float, float]) -> dict:
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


def _box(west: float, south: float, east: float, north: float) -> dict:
    return _polygon((west, south), (east, south), (east, north), (west, north))


def test_a_point_becomes_a_square_of_the_contract_size() -> None:
    # Arrange
    lon, lat = QADIRABAD_LON, QADIRABAD_LAT

    # Act
    aoi = aoi_from_point(lon=lon, lat=lat)

    # Assert
    west, south, east, north = aoi.bbox
    assert aoi.kind is AoiKind.POINT
    assert aoi.area_km2 == pytest.approx(EXPECTED_SQUARE_KM2, abs=AREA_TOLERANCE_KM2)
    assert west < lon < east
    assert south < lat < north
    assert aoi.native_pixels == pytest.approx(IDEAL_NATIVE_PIXELS, rel=0.06)
    assert aoi.warnings == []


def test_a_point_square_has_the_same_size_at_any_latitude() -> None:
    # Arrange
    latitudes = [-60.0, 0.0, 45.0, 70.0]

    # Act
    areas = [aoi_from_point(lon=10.0, lat=lat).area_km2 for lat in latitudes]

    # Assert
    assert all(area == pytest.approx(EXPECTED_SQUARE_KM2, abs=AREA_TOLERANCE_KM2) for area in areas)


def test_a_point_next_to_the_antimeridian_is_split_without_losing_area() -> None:
    # Arrange
    lon, lat = 179.99, 10.0

    # Act
    aoi = aoi_from_point(lon=lon, lat=lat)

    # Assert
    assert aoi.geometry["type"] == "MultiPolygon"
    assert len(aoi.geometry["coordinates"]) == 2
    assert aoi.area_km2 == pytest.approx(EXPECTED_SQUARE_KM2, abs=AREA_TOLERANCE_KM2)


@pytest.mark.parametrize(argnames="lat", argvalues=[85.0, -85.0, 91.0])
def test_points_outside_the_supported_latitudes_are_rejected(lat: float) -> None:
    # Arrange
    lon = 0.0

    # Act / Assert
    with pytest.raises(expected_exception=InvalidGeometryError):
        aoi_from_point(lon=lon, lat=lat)


def test_a_rectangle_crossing_the_antimeridian_is_split_and_measured_on_the_sphere() -> None:
    # Arrange
    ring = _polygon((179.95, 0.0), (-179.95, 0.0), (-179.95, 0.05), (179.95, 0.05))

    # Act
    aoi = aoi_from_geojson(geometry=ring)

    # Assert
    assert aoi.geometry["type"] == "MultiPolygon"
    assert len(aoi.geometry["coordinates"]) == 2
    expected = 0.1 * 111.32 * 0.05 * 110.57
    assert aoi.area_km2 == pytest.approx(expected, rel=0.03)
    assert aoi.kind is AoiKind.POLYGON


def test_a_polygon_round_trips_through_wkt_and_keeps_its_bbox() -> None:
    # Arrange
    geometry = _box(73.70, 32.30, 73.75, 32.34)

    # Act
    aoi = aoi_from_geojson(geometry=geometry)

    # Assert
    parsed = shapely_wkt.loads(aoi.wkt)
    assert math.isclose(parsed.area, shape(aoi.geometry).area, rel_tol=1e-6)
    assert aoi.bbox == pytest.approx((73.70, 32.30, 73.75, 32.34))


def test_a_polygon_larger_than_the_ideal_is_accepted_with_a_warning() -> None:
    # Arrange
    geometry = _box(0.0, 0.0, 0.135, 0.135)

    # Act
    aoi = aoi_from_geojson(geometry=geometry)

    # Assert
    assert aoi.native_pixels > IDEAL_NATIVE_PIXELS
    assert any("ideal" in warning for warning in aoi.warnings)


def test_a_polygon_beyond_the_pixel_cap_is_rejected() -> None:
    # Arrange
    geometry = _box(0.0, 0.0, 0.25, 0.25)

    # Act / Assert
    with pytest.raises(expected_exception=AreaTooLargeError, match="pixels"):
        aoi_from_geojson(geometry=geometry)


def test_an_open_ring_is_rejected() -> None:
    # Arrange
    geometry = {"type": "Polygon", "coordinates": [[(0, 0), (0.1, 0), (0.1, 0.1), (0, 0.1)]]}

    # Act / Assert
    with pytest.raises(expected_exception=InvalidGeometryError, match="closed"):
        aoi_from_geojson(geometry=geometry)


def test_a_ring_with_fewer_than_three_vertices_is_rejected() -> None:
    # Arrange
    geometry = {"type": "Polygon", "coordinates": [[(0, 0), (0.1, 0.1), (0, 0)]]}

    # Act / Assert
    with pytest.raises(expected_exception=InvalidGeometryError, match="at least 3"):
        aoi_from_geojson(geometry=geometry)


def test_a_ring_with_too_many_vertices_is_rejected() -> None:
    # Arrange
    count = MAX_VERTICES + 5
    ring = [
        (0.01 * math.cos(2 * math.pi * i / count), 0.01 * math.sin(2 * math.pi * i / count))
        for i in range(count)
    ]
    geometry = {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}

    # Act / Assert
    with pytest.raises(expected_exception=InvalidGeometryError, match="vertices"):
        aoi_from_geojson(geometry=geometry)


def test_a_self_intersecting_polygon_is_repaired_with_a_warning() -> None:
    # Arrange
    bow_tie = _polygon((0.0, 0.0), (0.1, 0.1), (0.1, 0.0), (0.0, 0.1))

    # Act
    aoi = aoi_from_geojson(geometry=bow_tie)

    # Assert
    assert aoi.area_km2 > 0
    assert any("repaired" in warning for warning in aoi.warnings)


@pytest.mark.parametrize(
    argnames="geometry",
    argvalues=[
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        {"type": "Polygon"},
        {"type": "Polygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[(200, 0), (201, 0), (201, 1), (200, 0)]]},
        {"type": "Polygon", "coordinates": [[(0, 0), (0.1, float("nan")), (0.1, 0.1), (0, 0)]]},
        {
            "type": "Polygon",
            "coordinates": [
                [(0, 0), (0.1, 0), (0.1, 0.1), (0, 0.1), (0, 0)],
                [(0.02, 0.02), (0.04, 0.02), (0.04, 0.04), (0.02, 0.02)],
            ],
        },
    ],
)
def test_unsupported_or_malformed_geometries_are_rejected(geometry: dict) -> None:
    # Arrange
    payload = geometry

    # Act / Assert
    with pytest.raises(expected_exception=InvalidGeometryError):
        aoi_from_geojson(geometry=payload)
