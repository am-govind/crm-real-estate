import { humanize, PROPERTY_STATUS_COLORS, PROPERTY_STATUSES, type MapPin } from "@landcrm/domain";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { MapView } from "../components/MapView";
import { Card, KV, PageHeader, Select, StatusBadge } from "../components/ui";
import { api } from "../lib/api";

export function MapPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<MapPin | null>(null);
  const pins = useQuery({ queryKey: ["map-pins", status], queryFn: () => api.properties.mapPins({ status: status ? [status] : undefined }) });
  const parcels = useQuery({ queryKey: ["map-layers"], queryFn: api.reports.mapLayers });

  return (
    <div className="stack">
      <PageHeader
        title="Map"
        subtitle="Pins are coloured by deal stage when a deal is active, otherwise by property status. Boundaries show approved geometry only."
        actions={<Select value={status} onChange={(e) => setStatus(e.target.value)} options={PROPERTY_STATUSES} placeholder="All statuses" />}
      />
      <div className="grid map-layout">
        <MapView
          pins={pins.data}
          parcels={parcels.data}
          onPinClick={setSelected}
          onParcelClick={(id) => navigate(`/properties/${id}`)}
        />
        <div className="stack">
          <Card title="Legend">
            <div className="stack small">
              {Object.entries(PROPERTY_STATUS_COLORS).map(([k, c]) => (
                <span key={k} className="row">
                  <span style={{ width: 10, height: 10, borderRadius: 999, background: c, display: "inline-block" }} />
                  {humanize(k)}
                </span>
              ))}
            </div>
          </Card>
          {selected && (
            <Card title={selected.name} actions={<Link to={`/properties/${selected.property_id}`}>Open</Link>}>
              <KV
                items={[
                  ["Code", selected.code],
                  ["Status", <StatusBadge status={selected.status} />],
                  ["Deal stage", selected.deal_stage_name ?? "No active deal"],
                  ["Boundary", selected.has_geometry ? "Approved" : "Not approved yet"],
                  ["Coordinates", `${selected.latitude}, ${selected.longitude}`],
                ]}
              />
              {selected.deal_id && (
                <div style={{ marginTop: 8 }}>
                  <Link to={`/deals/${selected.deal_id}`}>Open deal control center</Link>
                </div>
              )}
            </Card>
          )}
          <div className="muted small">{pins.data?.length ?? 0} properties with coordinates</div>
        </div>
      </div>
    </div>
  );
}
