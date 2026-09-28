"""Map provider boundary. Public OSM services are rate-limited and not assumed to be unlimited;
production deployments should point these URLs at self-hosted or commercial endpoints."""

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.modules.maps.geometry import haversine_m


@dataclass
class NearbyResult:
    kind: str
    name: str | None
    distance_m: float
    latitude: float | None
    longitude: float | None
    ref: str | None = None
    confidence: str = "medium"
    raw: dict = field(default_factory=dict)


@dataclass
class GeocodeResult:
    label: str
    latitude: float
    longitude: float
    raw: dict = field(default_factory=dict)


class MapProvider(Protocol):
    name: str

    def nearby(self, lat: float, lon: float, *, radius_m: int = 20000) -> list[NearbyResult]: ...

    def geocode(self, query: str, *, country: str | None = None) -> list[GeocodeResult]: ...


class NullMapProvider:
    name = "none"

    def nearby(self, lat: float, lon: float, *, radius_m: int = 20000) -> list[NearbyResult]:
        return []

    def geocode(self, query: str, *, country: str | None = None) -> list[GeocodeResult]:
        return []


HIGHWAY_CLASSES = {"motorway", "trunk", "primary"}
ROAD_CLASSES = {"secondary", "tertiary", "unclassified", "residential"}
PLACE_CLASSES = {"city", "town"}


class OSMMapProvider:
    name = "osm"

    def __init__(self) -> None:
        s = get_settings()
        self._overpass = s.overpass_url
        self._nominatim = s.nominatim_url.rstrip("/")
        self._headers = {"User-Agent": s.map_user_agent}

    def nearby(self, lat: float, lon: float, *, radius_m: int = 20000) -> list[NearbyResult]:
        road_radius = min(radius_m, 5000)
        query = f"""
        [out:json][timeout:25];
        (
          way(around:{radius_m},{lat},{lon})["highway"~"^(motorway|trunk|primary)$"];
          way(around:{road_radius},{lat},{lon})["highway"~"^(secondary|tertiary|unclassified|residential)$"];
          node(around:{radius_m * 2},{lat},{lon})["place"~"^(city|town)$"];
        );
        out center tags 200;
        """
        resp = httpx.post(self._overpass, data={"data": query}, headers=self._headers, timeout=30)
        resp.raise_for_status()
        results: list[NearbyResult] = []
        for el in resp.json().get("elements", []):
            tags = el.get("tags", {})
            plat = el.get("lat") or (el.get("center") or {}).get("lat")
            plon = el.get("lon") or (el.get("center") or {}).get("lon")
            if plat is None or plon is None:
                continue
            dist = haversine_m(lon, lat, plon, plat)
            hw = tags.get("highway")
            if hw in HIGHWAY_CLASSES:
                kind = "highway"
            elif hw in ROAD_CLASSES:
                kind = "road"
            elif tags.get("place") in PLACE_CLASSES:
                kind = tags["place"]
            else:
                continue
            results.append(
                NearbyResult(
                    kind=kind, name=tags.get("name") or tags.get("ref"), ref=tags.get("ref"), distance_m=round(dist, 1),
                    latitude=plat, longitude=plon,
                    confidence="low" if el.get("type") == "way" else "medium",
                    raw={"osm_type": el.get("type"), "osm_id": el.get("id"), "tags": tags},
                )
            )
        best: dict[tuple, NearbyResult] = {}
        for r in results:
            key = (r.kind, r.name or r.ref or r.raw.get("osm_id"))
            if key not in best or r.distance_m < best[key].distance_m:
                best[key] = r
        return sorted(best.values(), key=lambda r: r.distance_m)[:50]

    def geocode(self, query: str, *, country: str | None = None) -> list[GeocodeResult]:
        params = {"q": query, "format": "jsonv2", "limit": 5}
        if country:
            params["countrycodes"] = country.lower()
        resp = httpx.get(f"{self._nominatim}/search", params=params, headers=self._headers, timeout=15)
        resp.raise_for_status()
        return [
            GeocodeResult(label=r["display_name"], latitude=float(r["lat"]), longitude=float(r["lon"]), raw=r)
            for r in resp.json()
        ]


@lru_cache
def get_map_provider() -> MapProvider:
    return OSMMapProvider() if get_settings().map_provider == "osm" else NullMapProvider()
