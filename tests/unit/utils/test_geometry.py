import math

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import shape

from nisar_hazard_watch.constants.sar import (
    AOI_SIDE_KM,
    IDEAL_NATIVE_PIXELS,
    MAX_POLYGONS,
    MAX_VERTICES,
    AoiKind,
)
from nisar_hazard_watch.exceptions.geometry_errors import AreaTooLargeError, InvalidGeometryError
from nisar_hazard_watch.utils.geometry import (
    aoi_center,
    aoi_from_geojson,
    aoi_from_point,
    window_pixels,
)

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


def _multi(*boxes: tuple[float, float, float, float]) -> dict:
    parts = [[[(w, s), (e, s), (e, n), (w, n), (w, s)]] for w, s, e, n in boxes]
    return {"type": "MultiPolygon", "coordinates": parts}


SQUARE = (73.70, 32.30, 73.75, 32.34)


def test_a_multipolygon_is_accepted_and_its_parts_are_summed() -> None:
    # Arrange
    far_apart = _multi(SQUARE, (74.00, 32.30, 74.05, 32.34))
    single = aoi_from_geojson(geometry=_box(*SQUARE))

    # Act
    aoi = aoi_from_geojson(geometry=far_apart)

    # Assert
    assert aoi.geometry["type"] == "MultiPolygon"
    assert aoi.area_km2 == pytest.approx(2 * single.area_km2, rel=0.01)


def test_overlapping_parts_are_merged_so_the_area_is_not_counted_twice() -> None:
    # Arrange
    duplicated = _multi(SQUARE, SQUARE)
    single = aoi_from_geojson(geometry=_box(*SQUARE))

    # Act
    aoi = aoi_from_geojson(geometry=duplicated)

    # Assert
    assert aoi.area_km2 == pytest.approx(single.area_km2, rel=0.001)
    assert aoi.native_pixels == single.native_pixels


def test_partially_overlapping_parts_give_their_union() -> None:
    # Arrange
    shifted = (73.725, 32.30, 73.775, 32.34)
    overlapping = _multi(SQUARE, shifted)
    single = aoi_from_geojson(geometry=_box(*SQUARE))

    # Act
    aoi = aoi_from_geojson(geometry=overlapping)

    # Assert
    assert single.area_km2 < aoi.area_km2 < 2 * single.area_km2
    assert aoi.geometry["type"] == "Polygon"


def test_a_self_intersecting_polygon_keeps_both_of_its_lobes() -> None:
    # Arrange
    bow_tie = _polygon((0.0, 0.0), (0.1, 0.1), (0.1, 0.0), (0.0, 0.1))
    expected_km2 = 0.5 * 0.1 * 0.05 * 2 * 111.32 * 110.57

    # Act
    aoi = aoi_from_geojson(geometry=bow_tie)

    # Assert
    assert aoi.area_km2 == pytest.approx(expected_km2, rel=0.05)
    assert aoi.geometry["type"] == "MultiPolygon"


def test_a_polygon_touching_the_antimeridian_keeps_180_as_its_east_edge() -> None:
    # Arrange
    geometry = _box(179.9, 0.0, 180.0, 0.05)

    # Act
    aoi = aoi_from_geojson(geometry=geometry)

    # Assert
    assert aoi.bbox == pytest.approx((179.9, 0.0, 180.0, 0.05))


def test_too_many_polygons_are_rejected() -> None:
    # Arrange
    many = _multi(*[(i * 0.01, 0.0, i * 0.01 + 0.005, 0.005) for i in range(MAX_POLYGONS + 1)])

    # Act / Assert
    with pytest.raises(expected_exception=InvalidGeometryError, match="too many polygons"):
        aoi_from_geojson(geometry=many)


def test_the_vertex_limit_applies_to_all_the_parts_together() -> None:
    # Arrange
    per_part = MAX_VERTICES // 2 + 5

    def ring(offset: float) -> list:
        points = [
            (
                offset + 0.004 * math.cos(2 * math.pi * i / per_part),
                0.004 * math.sin(2 * math.pi * i / per_part),
            )
            for i in range(per_part)
        ]
        return [[*points, points[0]]]

    geometry = {"type": "MultiPolygon", "coordinates": [ring(0.0), ring(0.05)]}

    # Act / Assert
    with pytest.raises(expected_exception=InvalidGeometryError, match="in total"):
        aoi_from_geojson(geometry=geometry)


def test_the_centre_of_a_point_square_is_the_point() -> None:
    # Arrange
    aoi = aoi_from_point(lon=QADIRABAD_LON, lat=QADIRABAD_LAT)

    # Act
    longitude, latitude = aoi_center(aoi=aoi)

    # Assert
    assert longitude == pytest.approx(QADIRABAD_LON, abs=0.001)
    assert latitude == pytest.approx(QADIRABAD_LAT, abs=0.001)


def test_the_centre_of_an_area_across_the_antimeridian_is_on_the_antimeridian() -> None:
    # Arrange
    aoi = aoi_from_point(lon=179.99, lat=10.0)

    # Act
    longitude, _ = aoi_center(aoi=aoi)

    # Assert
    assert abs(longitude) == pytest.approx(179.99, abs=0.01)


def test_the_contract_square_needs_the_full_native_window() -> None:
    # Arrange
    aoi = aoi_from_point(lon=QADIRABAD_LON, lat=QADIRABAD_LAT)

    # Act
    pixels, truncated = window_pixels(aoi=aoi)

    # Assert
    assert pixels == 1024
    assert truncated is False


def test_a_small_area_gets_a_small_window_and_a_big_one_is_flagged_as_cut() -> None:
    # Arrange
    small = aoi_from_geojson(geometry=_box(73.70, 32.30, 73.71, 32.31))
    big = aoi_from_geojson(geometry=_box(73.0, 32.0, 73.17, 32.17))

    # Act
    small_pixels, small_cut = window_pixels(aoi=small)
    big_pixels, big_cut = window_pixels(aoi=big)

    # Assert
    assert small_pixels % 8 == 0
    assert small_pixels < 200
    assert small_cut is False
    assert big_pixels == 1024
    assert big_cut is True
