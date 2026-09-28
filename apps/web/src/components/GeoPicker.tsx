import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { useMe } from "../lib/auth";
import { Field, Select } from "./ui";

export const GEO_LEVELS = ["state", "district", "tehsil", "village"] as const;
export type GeoLevel = (typeof GEO_LEVELS)[number];
export type GeoValue = Partial<Record<`${GeoLevel}_id`, string>>;

function LevelSelect({ level, parentId, value, onChange }: { level: GeoLevel; parentId?: string; value?: string; onChange: (id: string) => void }) {
  const me = useMe();
  const needsParent = level !== "state";
  const units = useQuery({
    queryKey: ["geo-units", level, parentId],
    queryFn: () => api.geo.list({ level, parent_id: parentId }),
    enabled: !needsParent || !!parentId,
  });
  return (
    <Field label={me.terminology[level]}>
      <Select
        value={value ?? ""}
        disabled={needsParent && !parentId}
        onChange={(e) => onChange(e.target.value)}
        placeholder="—"
        options={(units.data ?? []).map((u) => ({ value: u.id, label: u.local_name ? `${u.name} (${u.local_name})` : u.name }))}
      />
    </Field>
  );
}

export function GeoPicker({ value, onChange }: { value: GeoValue; onChange: (v: GeoValue) => void }) {
  return (
    <div className="grid grid-4">
      {GEO_LEVELS.map((level, i) => {
        const parentLevel = i > 0 ? GEO_LEVELS[i - 1] : undefined;
        return (
          <LevelSelect
            key={level}
            level={level}
            parentId={parentLevel ? value[`${parentLevel}_id`] : undefined}
            value={value[`${level}_id`]}
            onChange={(id) => {
              const next: GeoValue = { ...value, [`${level}_id`]: id || undefined };
              for (const lower of GEO_LEVELS.slice(i + 1)) next[`${lower}_id`] = undefined;
              onChange(next);
            }}
          />
        );
      })}
    </div>
  );
}
