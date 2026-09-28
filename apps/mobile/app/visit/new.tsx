import { useQuery } from "@tanstack/react-query";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert, Pressable, Text } from "react-native";
import { colors } from "@landcrm/ui";

import { Button, Card, Choice, Field, Input, Muted, Row, Screen } from "../../src/components/ui";
import { api } from "../../src/lib/api";
import { createVisit, useOffline } from "../../src/lib/offline";
import { useSession } from "../../src/lib/session";

const pad = (n: number) => String(n).padStart(2, "0");
const localDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function parseLocal(date: string, time: string): Date | null {
  const m = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const t = time.match(/^(\d{1,2}):(\d{2})$/);
  if (!m || !t) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(t[1]), Number(t[2]));
  return Number.isNaN(d.getTime()) ? null : d;
}

export default function NewVisitScreen() {
  const params = useLocalSearchParams<{ property?: string }>();
  const { me } = useSession();
  const online = useOffline((s) => s.online);
  const propertiesMap = useOffline((s) => s.properties);
  const properties = Object.values(propertiesMap).sort((a, b) => a.code.localeCompare(b.code));

  const soon = new Date(Date.now() + 60 * 60 * 1000);
  const [propertyId, setPropertyId] = useState(params.property ?? "");
  const [title, setTitle] = useState("Site visit");
  const [purpose, setPurpose] = useState("");
  const [date, setDate] = useState(localDate(soon));
  const [time, setTime] = useState(`${pad(soon.getHours())}:00`);
  const [duration, setDuration] = useState<"60" | "120" | "240">("120");
  const [meetingPoint, setMeetingPoint] = useState("");
  const [colleagues, setColleagues] = useState<string[]>([]);
  const [externals, setExternals] = useState("");
  const [filter, setFilter] = useState("");

  const users = useQuery({ queryKey: ["tenant-users"], queryFn: () => api.tenant.users(), enabled: online });
  const otherProperty = useQuery({
    queryKey: ["property", propertyId],
    queryFn: () => api.properties.get(propertyId),
    enabled: online && !!propertyId && !propertiesMap[propertyId],
  });

  const needle = filter.trim().toLowerCase();
  const shown = properties.filter((p) => !needle || p.code.toLowerCase().includes(needle) || p.name.toLowerCase().includes(needle)).slice(0, 20);
  const selectedLabel = propertiesMap[propertyId]
    ? `${propertiesMap[propertyId]!.code} · ${propertiesMap[propertyId]!.name}`
    : otherProperty.data
      ? `${otherProperty.data.code} · ${otherProperty.data.name}`
      : null;

  const save = () => {
    if (!me) return;
    const start = parseLocal(date, time);
    if (!propertyId) return Alert.alert("Choose a property", "A site visit must be linked to a property.");
    if (!title.trim()) return Alert.alert("Title required");
    if (!start) return Alert.alert("Invalid date or time", "Use YYYY-MM-DD and HH:MM.");
    const end = new Date(start.getTime() + Number(duration) * 60_000);
    const id = createVisit(
      {
        property_id: propertyId,
        title: title.trim(),
        purpose: purpose.trim() || undefined,
        scheduled_start: start.toISOString(),
        scheduled_end: end.toISOString(),
        meeting_point: meetingPoint.trim() || undefined,
        attendees: [
          { user_id: me.id, is_assigned: true },
          ...colleagues.filter((u) => u !== me.id).map((u) => ({ user_id: u, is_assigned: true })),
          ...externals.split(",").map((n) => n.trim()).filter(Boolean).map((name) => ({ name })),
        ],
      },
      me.id,
    );
    router.replace(`/visit/${encodeURIComponent(id)}`);
  };

  return (
    <Screen>
      <Field label="Property">
        {selectedLabel ? (
          <Row style={{ justifyContent: "space-between" }}>
            <Text style={{ fontSize: 15, fontWeight: "600" }}>{selectedLabel}</Text>
            {!params.property ? (
              <Pressable onPress={() => setPropertyId("")}>
                <Text style={{ color: colors.primary }}>Change</Text>
              </Pressable>
            ) : null}
          </Row>
        ) : (
          <>
            <Input value={filter} onChangeText={setFilter} placeholder="Filter assigned properties" />
            {shown.map((p) => (
              <Card key={p.id} onPress={() => setPropertyId(p.id)}>
                <Text style={{ fontWeight: "600" }}>{p.code}</Text>
                <Muted>{p.name}</Muted>
              </Card>
            ))}
            {!shown.length ? <Muted>No assigned properties. Open a property from search to schedule a visit for it.</Muted> : null}
          </>
        )}
      </Field>
      <Field label="Title">
        <Input value={title} onChangeText={setTitle} />
      </Field>
      <Field label="Purpose">
        <Input value={purpose} onChangeText={setPurpose} multiline placeholder="Boundary check, owner meeting…" />
      </Field>
      <Row>
        <Field label="Date (YYYY-MM-DD)">
          <Input value={date} onChangeText={setDate} style={{ minWidth: 140 }} autoCorrect={false} />
        </Field>
        <Field label="Time (HH:MM)">
          <Input value={time} onChangeText={setTime} style={{ minWidth: 90 }} autoCorrect={false} />
        </Field>
      </Row>
      <Field label="Duration">
        <Choice
          value={duration}
          onChange={setDuration}
          options={[
            { value: "60", label: "1 hour" },
            { value: "120", label: "2 hours" },
            { value: "240", label: "Half day" },
          ]}
        />
      </Field>
      <Field label="Meeting point">
        <Input value={meetingPoint} onChangeText={setMeetingPoint} placeholder="Village chowk, gate no. 2…" />
      </Field>
      <Field label="Colleagues">
        {online ? (
          <Row>
            {(users.data ?? [])
              .filter((u) => u.id !== me?.id && u.is_active)
              .map((u) => {
                const on = colleagues.includes(u.id);
                return (
                  <Pressable
                    key={u.id}
                    onPress={() => setColleagues(on ? colleagues.filter((c) => c !== u.id) : [...colleagues, u.id])}
                    style={{ borderWidth: 1, borderColor: on ? colors.primary : colors.border, backgroundColor: on ? colors.primary : colors.surface, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 4 }}
                  >
                    <Text style={{ color: on ? colors.primaryText : colors.text }}>{u.display_name ?? u.email}</Text>
                  </Pressable>
                );
              })}
          </Row>
        ) : (
          <Muted>Colleagues can be added when you are online. You are assigned automatically.</Muted>
        )}
      </Field>
      <Field label="Other attendees (comma separated names)">
        <Input value={externals} onChangeText={setExternals} placeholder="Owner's son, local surveyor" />
      </Field>
      <Button title="Schedule visit" onPress={save} />
      {!online ? <Muted>You are offline. The visit is saved on this device and synced automatically.</Muted> : null}
    </Screen>
  );
}
