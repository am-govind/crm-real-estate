import type { FeatureCollection } from "@landcrm/api-client";
import type { GeoJSONPolygon, MapPin } from "@landcrm/domain";
import maplibregl, { type GeoJSONSource, type LngLatBoundsLike } from "maplibre-gl";
import { useEffect, useRef } from "react";

import { MAP_STYLE_URL } from "../lib/api";

interface Props {
  pins?: MapPin[];
  parcels?: FeatureCollection;
  /** Polygon being drafted (lng/lat ring, not closed). */
  draft?: [number, number][];
  onMapClick?: (lngLat: [number, number]) => void;
  onPinClick?: (pin: MapPin) => void;
  onParcelClick?: (propertyId: string) => void;
  small?: boolean;
  center?: [number, number];
}

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

function boundsOf(points: [number, number][]): LngLatBoundsLike | null {
  if (points.length === 0) return null;
  let [minX, minY, maxX, maxY] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y] of points) {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  return [
    [minX, minY],
    [maxX, maxY],
  ];
}

function ringsOf(g: GeoJSONPolygon): [number, number][] {
  const polys = (g.type === "Polygon" ? [g.coordinates] : g.coordinates) as number[][][][];
  return polys.flatMap((p) => (p[0] ?? []).map((c) => [c[0]!, c[1]!] as [number, number]));
}

export function MapView({ pins, parcels, draft, onMapClick, onPinClick, onParcelClick, small, center }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loaded = useRef(false);
  const handlers = useRef({ onMapClick, onPinClick, onParcelClick });
  handlers.current = { onMapClick, onPinClick, onParcelClick };
  const pinsRef = useRef<MapPin[]>([]);
  pinsRef.current = pins ?? [];
  const fitted = useRef(false);

  useEffect(() => {
    const map = new maplibregl.Map({
      container: ref.current!,
      style: MAP_STYLE_URL,
      center: center ?? [78.9629, 22.5937],
      zoom: center ? 14 : 4,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }));
    map.on("load", () => {
      map.addSource("parcels", { type: "geojson", data: EMPTY as never });
      map.addLayer({ id: "parcels-fill", type: "fill", source: "parcels", paint: { "fill-color": ["coalesce", ["get", "color"], "#2563eb"], "fill-opacity": 0.25 } });
      map.addLayer({ id: "parcels-line", type: "line", source: "parcels", paint: { "line-color": ["coalesce", ["get", "color"], "#2563eb"], "line-width": 2 } });
      map.addSource("pins", { type: "geojson", data: EMPTY as never });
      map.addLayer({
        id: "pins",
        type: "circle",
        source: "pins",
        paint: { "circle-radius": 7, "circle-color": ["get", "color"], "circle-stroke-color": "#fff", "circle-stroke-width": 2 },
      });
      map.addSource("draft", { type: "geojson", data: EMPTY as never });
      map.addLayer({ id: "draft-line", type: "line", source: "draft", paint: { "line-color": "#f59e0b", "line-width": 2, "line-dasharray": [2, 1] } });
      map.addLayer({ id: "draft-pts", type: "circle", source: "draft", filter: ["==", "$type", "Point"], paint: { "circle-radius": 4, "circle-color": "#f59e0b" } });

      map.on("click", "pins", (e) => {
        const id = e.features?.[0]?.properties?.property_id as string | undefined;
        const pin = pinsRef.current.find((p) => p.property_id === id);
        if (pin) handlers.current.onPinClick?.(pin);
      });
      map.on("click", "parcels-fill", (e) => {
        const id = e.features?.[0]?.properties?.property_id as string | undefined;
        if (id) handlers.current.onParcelClick?.(id);
      });
      map.on("click", (e) => handlers.current.onMapClick?.([e.lngLat.lng, e.lngLat.lat]));
      for (const layer of ["pins", "parcels-fill"]) {
        map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
      }
      loaded.current = true;
      map.fire("landcrm:data");
    });
    mapRef.current = map;
    return () => {
      loaded.current = false;
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      if (!loaded.current) return;
      (map.getSource("pins") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: (pins ?? []).map((p) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: [Number(p.longitude), Number(p.latitude)] },
          properties: { property_id: p.property_id, color: p.color, name: p.name },
        })),
      });
      (map.getSource("parcels") as GeoJSONSource).setData((parcels ?? EMPTY) as never);
      const ring = draft ?? [];
      (map.getSource("draft") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: [
          ...ring.map((c) => ({ type: "Feature" as const, geometry: { type: "Point" as const, coordinates: c }, properties: {} })),
          ...(ring.length > 1
            ? [{ type: "Feature" as const, geometry: { type: "LineString" as const, coordinates: [...ring, ring[0]!] }, properties: {} }]
            : []),
        ],
      });
      if (!fitted.current) {
        const pts: [number, number][] = [
          ...(pins ?? []).map((p) => [Number(p.longitude), Number(p.latitude)] as [number, number]),
          ...(parcels?.features ?? []).flatMap((f) => ringsOf(f.geometry)),
        ];
        const b = boundsOf(pts);
        if (b) {
          map.fitBounds(b, { padding: 40, maxZoom: 16, duration: 0 });
          fitted.current = true;
        }
      }
    };
    apply();
    map.on("landcrm:data", apply);
    return () => {
      map.off("landcrm:data", apply);
    };
  }, [pins, parcels, draft]);

  return <div ref={ref} className={`map ${small ? "map-sm" : ""}`} />;
}
