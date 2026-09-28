"""Geometry engine boundary.

``PythonGeometryEngine`` computes geodesic measurements on the WGS84 sphere without native
dependencies. A PostGIS engine (``ST_Area(geom::geography)``, ``ST_Perimeter``, ``ST_IsValid``)
can replace it once the database integration lands, without changing callers.
"""

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.errors import ValidationFailed

EARTH_RADIUS_M = 6378137.0
MAX_VERTICES = 20000


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"valid": self.valid, "errors": self.errors, "warnings": self.warnings}


class GeometryEngine(Protocol):
    method: str

    def validate(self, geometry: dict) -> ValidationResult: ...

    def area_sqm(self, geometry: dict) -> float: ...

    def perimeter_m(self, geometry: dict) -> float: ...

    def centroid(self, geometry: dict) -> tuple[float, float]: ...


def _polygons(geometry: dict) -> list[list[list[list[float]]]]:
    t = geometry.get("type")
    if t == "Polygon":
        return [geometry["coordinates"]]
    if t == "MultiPolygon":
        return geometry["coordinates"]
    raise ValidationFailed("Geometry must be a Polygon or MultiPolygon")


def _ring_area(ring: list[list[float]]) -> float:
    """Spherical excess approximation (Chamberlain & Duquette), matching Turf/Leaflet geodesic area."""
    n = len(ring)
    if n < 4:
        return 0.0
    total = 0.0
    for i in range(n - 1):
        lon1, lat1 = map(math.radians, ring[i][:2])
        lon2, lat2 = map(math.radians, ring[i + 1][:2])
        total += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
    return abs(total * EARTH_RADIUS_M**2 / 2.0)


def _haversine(a: list[float], b: list[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _segments_intersect(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-15 else (1 if v > 0 else -1)

    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    return o1 != o2 and o3 != o4 and 0 not in (o1, o2, o3, o4)


def _self_intersects(ring: list[list[float]]) -> bool:
    n = len(ring) - 1
    if n > 2000:
        return False
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _segments_intersect(ring[i], ring[i + 1], ring[j], ring[j + 1]):
                return True
    return False


class PythonGeometryEngine:
    method = "spherical-wgs84-python"

    def validate(self, geometry: dict) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        try:
            polys = _polygons(geometry)
        except (ValidationFailed, KeyError, TypeError) as exc:
            return ValidationResult(False, [str(exc) or "Invalid geometry"])
        vertices = 0
        for pi, poly in enumerate(polys):
            if not poly:
                errors.append(f"Polygon {pi} has no rings")
                continue
            for ri, ring in enumerate(poly):
                label = f"polygon {pi} ring {ri}"
                if len(ring) < 4:
                    errors.append(f"{label}: a ring needs at least 4 positions")
                    continue
                vertices += len(ring)
                for pos in ring:
                    if len(pos) < 2 or not all(isinstance(v, (int, float)) for v in pos[:2]):
                        errors.append(f"{label}: invalid position {pos!r}")
                        break
                    lon, lat = pos[0], pos[1]
                    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                        errors.append(f"{label}: coordinate out of range {pos!r} (expected [lng, lat])")
                        break
                if ring[0][:2] != ring[-1][:2]:
                    errors.append(f"{label}: ring is not closed")
                elif _self_intersects(ring):
                    errors.append(f"{label}: ring self-intersects")
        if vertices > MAX_VERTICES:
            errors.append(f"Too many vertices ({vertices} > {MAX_VERTICES})")
        if not errors:
            area = self.area_sqm(geometry)
            if area < 1:
                errors.append("Polygon area is effectively zero")
            elif area > 5e8:
                warnings.append("Polygon is larger than 500 km²; check the coordinate order and CRS")
        return ValidationResult(not errors, errors, warnings)

    def area_sqm(self, geometry: dict) -> float:
        total = 0.0
        for poly in _polygons(geometry):
            if not poly:
                continue
            total += _ring_area(poly[0]) - sum(_ring_area(h) for h in poly[1:])
        return total

    def perimeter_m(self, geometry: dict) -> float:
        total = 0.0
        for poly in _polygons(geometry):
            for ring in poly:
                total += sum(_haversine(ring[i], ring[i + 1]) for i in range(len(ring) - 1))
        return total

    def centroid(self, geometry: dict) -> tuple[float, float]:
        pts = [p for poly in _polygons(geometry) for p in poly[0][:-1]]
        if not pts:
            raise ValidationFailed("Empty geometry")
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


engine: GeometryEngine = PythonGeometryEngine()


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return _haversine([lon1, lat1], [lon2, lat2])


# ---- Parsers ----


def geometry_from_geojson(data: Any) -> list[dict]:
    """Returns Polygon/MultiPolygon geometries from a GeoJSON object of any supported type."""
    if not isinstance(data, dict):
        raise ValidationFailed("GeoJSON must be an object")
    t = data.get("type")
    if t == "FeatureCollection":
        out = []
        for f in data.get("features") or []:
            out.extend(geometry_from_geojson(f))
        return out
    if t == "Feature":
        g = data.get("geometry")
        return geometry_from_geojson(g) if g else []
    if t in ("Polygon", "MultiPolygon"):
        return [{"type": t, "coordinates": data.get("coordinates")}]
    if t == "GeometryCollection":
        out = []
        for g in data.get("geometries") or []:
            out.extend(geometry_from_geojson(g))
        return out
    return []


def _parse_coords(text: str) -> list[list[float]]:
    coords = []
    for token in (text or "").split():
        parts = token.split(",")
        if len(parts) >= 2:
            coords.append([float(parts[0]), float(parts[1])])
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def geometry_from_kml(raw: bytes) -> list[dict]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValidationFailed(f"Invalid KML: {exc}") from exc

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    polygons = []
    for el in root.iter():
        if local(el.tag) != "Polygon":
            continue
        outer, inner = None, []
        for child in el.iter():
            name = local(child.tag)
            if name in ("outerBoundaryIs", "innerBoundaryIs"):
                coords_el = next((c for c in child.iter() if local(c.tag) == "coordinates"), None)
                if coords_el is None:
                    continue
                ring = _parse_coords(coords_el.text or "")
                if name == "outerBoundaryIs":
                    outer = ring
                else:
                    inner.append(ring)
        if outer:
            polygons.append({"type": "Polygon", "coordinates": [outer, *inner]})
    return polygons


# ---- Georeferencing for scanned maps ----


def fit_affine(control_points: list[dict]) -> list[float]:
    """Least-squares affine transform from pixel [x, y] to [lng, lat]. Requires >= 3 points."""
    if len(control_points) < 3:
        raise ValidationFailed("At least three control points are required to georeference")
    rows = [(cp["pixel"][0], cp["pixel"][1], cp["lnglat"][0], cp["lnglat"][1]) for cp in control_points]

    def solve(targets: list[float]) -> list[float]:
        ata = [[0.0] * 3 for _ in range(3)]
        atb = [0.0] * 3
        for (x, y, *_), t in zip(rows, targets, strict=True):
            v = (x, y, 1.0)
            for i in range(3):
                atb[i] += v[i] * t
                for j in range(3):
                    ata[i][j] += v[i] * v[j]
        return _solve3(ata, atb)

    a, b, c = solve([r[2] for r in rows])
    d, e, f = solve([r[3] for r in rows])
    return [a, b, c, d, e, f]


def _solve3(m: list[list[float]], v: list[float]) -> list[float]:
    aug = [row[:] + [v[i]] for i, row in enumerate(m)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValidationFailed("Control points are collinear; choose points spread across the map")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        for r in range(3):
            if r != col:
                factor = aug[r][col] / aug[col][col]
                for k in range(col, 4):
                    aug[r][k] -= factor * aug[col][k]
    return [aug[i][3] / aug[i][i] for i in range(3)]


def apply_affine(transform: list[float], pixel_rings: list[list[list[float]]]) -> dict:
    a, b, c, d, e, f = transform
    rings = []
    for ring in pixel_rings:
        pts = [[a * x + b * y + c, d * x + e * y + f] for x, y in ring]
        if pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        rings.append(pts)
    return {"type": "Polygon", "coordinates": rings}


def affine_residuals_m(transform: list[float], control_points: list[dict]) -> float:
    """Root-mean-square error of the fit in metres, reported as georeference confidence."""
    a, b, c, d, e, f = transform
    errs = []
    for cp in control_points:
        x, y = cp["pixel"]
        lng, lat = a * x + b * y + c, d * x + e * y + f
        errs.append(haversine_m(lng, lat, cp["lnglat"][0], cp["lnglat"][1]) ** 2)
    return math.sqrt(sum(errs) / len(errs))
