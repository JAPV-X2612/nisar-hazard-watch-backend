import itertools
import json
import math
from typing import Any

import shapely
from pyproj import Geod, Transformer
from shapely.affinity import translate
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry

from nisar_hazard_watch.constants.sar import (
    AOI_SIDE_KM,
    COORDINATE_DECIMALS,
    IDEAL_NATIVE_PIXELS,
    MAX_NATIVE_PIXELS,
    MAX_POINT_LATITUDE,
    MAX_VERTICES,
    NATIVE_PIXEL_M,
    AoiKind,
)
from nisar_hazard_watch.exceptions.geometry_errors import AreaTooLargeError, InvalidGeometryError
from nisar_hazard_watch.models.geometry import Aoi

GEOD = Geod(ellps="WGS84")
HALF_TURN = 180.0
FULL_TURN = 360.0
MIN_VERTICES = 3
M2_PER_KM2 = 1_000_000.0
WORLD = box(-HALF_TURN, -90.0, HALF_TURN, 90.0)
SUPPORTED_TYPES = ("Polygon", "MultiPolygon")


def aoi_from_point(lon: float, lat: float) -> Aoi:
    """The contract square (10.24 km) centred on the point, built in the local UTM zone."""
    _require_valid_point(lon=lon, lat=lat)
    zone = min(int((lon + HALF_TURN) // 6) + 1, 60)
    epsg = (32600 if lat >= 0 else 32700) + zone
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    to_geographic = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    x, y = to_utm.transform(lon, lat)
    radius = AOI_SIDE_KM * 500.0
    corners_x = [x - radius, x + radius, x + radius, x - radius]
    corners_y = [y - radius, y - radius, y + radius, y + radius]
    lons, lats = to_geographic.transform(corners_x, corners_y)
    ring = list(zip(lons, lats, strict=True))
    square = Polygon(_unwrap_longitudes(ring=[*ring, ring[0]]))
    return _build_aoi(kind=AoiKind.POINT, continuous=[square], warnings=[])


def aoi_from_geojson(geometry: dict[str, Any]) -> Aoi:
    """Validate a drawn Polygon or MultiPolygon, repair it, split it at ±180° and measure it."""
    rings = _rings_of(geometry=geometry)
    warnings: list[str] = []
    continuous: list[BaseGeometry] = []
    for ring in rings:
        polygon = Polygon(_unwrap_longitudes(ring=ring))
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
            warnings.append("geometry was repaired (self-intersection)")
        if polygon.is_empty or polygon.area == 0:
            raise InvalidGeometryError("the polygon has no area")
        continuous.append(polygon)
    return _build_aoi(kind=AoiKind.POLYGON, continuous=continuous, warnings=warnings)


def _require_valid_point(lon: float, lat: float) -> None:
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise InvalidGeometryError("the point coordinates must be finite numbers")
    if not -HALF_TURN <= lon <= HALF_TURN:
        raise InvalidGeometryError(f"longitude {lon!r} is outside [-180, 180]")
    if abs(lat) > MAX_POINT_LATITUDE:
        raise InvalidGeometryError(
            f"latitude {lat!r} is outside the supported ±{MAX_POINT_LATITUDE:g}°"
        )


def _rings_of(geometry: dict[str, Any]) -> list[list[tuple[float, float]]]:
    kind = geometry.get("type") if isinstance(geometry, dict) else None
    if kind not in SUPPORTED_TYPES:
        raise InvalidGeometryError(
            f"unsupported geometry type {kind!r}; use Polygon or MultiPolygon"
        )
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise InvalidGeometryError("the geometry has no coordinates")
    polygons = coordinates if kind == "MultiPolygon" else [coordinates]
    return [_outer_ring(polygon=polygon) for polygon in polygons]


def _outer_ring(polygon: Any) -> list[tuple[float, float]]:
    if not isinstance(polygon, list) or not polygon:
        raise InvalidGeometryError("a polygon needs one ring of coordinates")
    if len(polygon) > 1:
        raise InvalidGeometryError("polygons with holes are not supported")
    ring = polygon[0]
    try:
        points = [(float(lon), float(lat)) for lon, lat in ring]
    except (TypeError, ValueError):
        raise InvalidGeometryError("coordinates must be [longitude, latitude] pairs") from None
    for lon, lat in points:
        if not (math.isfinite(lon) and math.isfinite(lat)):
            raise InvalidGeometryError("coordinates must be finite numbers")
        if not (-HALF_TURN <= lon <= HALF_TURN and -90.0 <= lat <= 90.0):
            raise InvalidGeometryError(f"coordinate ({lon}, {lat}) is outside the valid range")
    if len(points) < 2 or points[0] != points[-1]:
        raise InvalidGeometryError("the ring is not closed: repeat the first vertex at the end")
    unique = len(points) - 1
    if unique < MIN_VERTICES:
        raise InvalidGeometryError(f"a polygon needs at least {MIN_VERTICES} vertices")
    if unique > MAX_VERTICES:
        raise InvalidGeometryError(f"too many vertices ({unique}); the limit is {MAX_VERTICES}")
    return points


def _unwrap_longitudes(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Make consecutive longitudes continuous so a ring that crosses ±180° stays one polygon."""
    unwrapped = [ring[0]]
    offset = 0.0
    for (previous_lon, _), (lon, lat) in itertools.pairwise(ring):
        jump = lon - previous_lon
        if jump > HALF_TURN:
            offset -= FULL_TURN
        elif jump < -HALF_TURN:
            offset += FULL_TURN
        unwrapped.append((lon + offset, lat))
    return unwrapped


def _split_at_antimeridian(polygon: BaseGeometry) -> list[Polygon]:
    west, _, east, _ = polygon.bounds
    if west >= -HALF_TURN and east <= HALF_TURN:
        return _polygons_of(geometry=polygon)
    if east > HALF_TURN:
        beyond_box, shift = box(HALF_TURN, -90.0, 540.0, 90.0), -FULL_TURN
    else:
        beyond_box, shift = box(-540.0, -90.0, -HALF_TURN, 90.0), FULL_TURN
    inside = polygon.intersection(WORLD)
    beyond = translate(polygon.intersection(beyond_box), xoff=shift)
    return _polygons_of(geometry=inside) + _polygons_of(geometry=beyond)


def _polygons_of(geometry: BaseGeometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    return [part for part in getattr(geometry, "geoms", []) if isinstance(part, Polygon)]


def _wrap(lon: float) -> float:
    return ((lon + HALF_TURN) % FULL_TURN) - HALF_TURN


def _build_aoi(kind: AoiKind, continuous: list[BaseGeometry], warnings: list[str]) -> Aoi:
    parts: list[Polygon] = []
    for polygon in continuous:
        parts.extend(_split_at_antimeridian(polygon=polygon))
    if not parts:
        raise InvalidGeometryError("the geometry has no area")
    area_m2 = sum(abs(GEOD.geometry_area_perimeter(part)[0]) for part in parts)
    native_pixels = round(area_m2 / NATIVE_PIXEL_M**2)
    if native_pixels > MAX_NATIVE_PIXELS:
        raise AreaTooLargeError(
            f"the area has about {native_pixels:,} native pixels; "
            f"the limit is {MAX_NATIVE_PIXELS:,} pixels"
        )
    if native_pixels > IDEAL_NATIVE_PIXELS:
        ideal_km2 = IDEAL_NATIVE_PIXELS * NATIVE_PIXEL_M**2 / M2_PER_KM2
        warnings = [*warnings, f"larger than the ideal {ideal_km2:.0f} km² of the contract square"]
    union_west = min(polygon.bounds[0] for polygon in continuous)
    union_east = max(polygon.bounds[2] for polygon in continuous)
    south = min(polygon.bounds[1] for polygon in continuous)
    north = max(polygon.bounds[3] for polygon in continuous)
    geometry = parts[0] if len(parts) == 1 else MultiPolygon(parts)
    return Aoi(
        kind=kind,
        geometry=json.loads(shapely.to_geojson(geometry)),
        wkt=shapely.to_wkt(geometry, rounding_precision=COORDINATE_DECIMALS, trim=True),
        bbox=(_wrap(union_west), south, _wrap(union_east), north),
        area_km2=round(area_m2 / M2_PER_KM2, 3),
        native_pixels=native_pixels,
        warnings=warnings,
    )
