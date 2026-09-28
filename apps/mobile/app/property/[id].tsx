import { useQuery } from "@tanstack/react-query";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { Linking, Platform, Pressable, Text } from "react-native";
import { colors } from "@landcrm/ui";

import { TaskRow, VisitCard } from "../../src/components/items";
import { Badge, Body, Button, Card, Empty, Heading, Loading, Muted, Row, Screen } from "../../src/components/ui";
import { api } from "../../src/lib/api";
import { useOffline } from "../../src/lib/offline";
import { useSession } from "../../src/lib/session";

function openInMaps(lat: string, lng: string, label: string) {
  const q = encodeURIComponent(label);
  const url = Platform.OS === "ios" ? `maps:0,0?q=${q}&ll=${lat},${lng}` : `geo:${lat},${lng}?q=${lat},${lng}(${q})`;
  void Linking.openURL(url).catch(() => Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${lat},${lng}`));
}

export default function PropertyScreen() {
  const { id = "" } = useLocalSearchParams<{ id: string }>();
  const { can } = useSession();
  const online = useOffline((s) => s.online);
  const cached = useOffline((s) => s.properties[id]);
  const visitsMap = useOffline((s) => s.visits);
  const tasksMap = useOffline((s) => s.tasks);

  const full = useQuery({ queryKey: ["property", id], queryFn: () => api.properties.get(id), enabled: online });
  const owners = useQuery({
    queryKey: ["property-owners", id],
    queryFn: () => api.properties.owners(id),
    enabled: online && can("owner.read"),
  });

  const p = full.data ?? cached;
  if (!p) return full.isLoading ? <Loading /> : <Empty>Property not available offline.</Empty>;

  const visits = Object.values(visitsMap)
    .filter((v) => v.property_id === id)
    .sort((a, b) => b.scheduled_start.localeCompare(a.scheduled_start));
  const tasks = Object.values(tasksMap).filter((t) => t.property_id === id && !["done", "cancelled"].includes(t.status));

  return (
    <Screen onRefresh={() => void Promise.all([full.refetch(), owners.refetch()])}>
      <Stack.Screen options={{ title: p.code }} />
      <Card>
        <Row style={{ justifyContent: "space-between" }}>
          <Heading>{p.name}</Heading>
          <Badge label={p.status} />
        </Row>
        <Muted>{p.code}{p.survey_number ? ` · Survey ${p.survey_number}` : ""}</Muted>
        {full.data?.khasra_number ? <Muted>Khasra {full.data.khasra_number}</Muted> : null}
        {p.address ? <Body>{p.address}</Body> : null}
        {full.data?.area_value ? (
          <Body>
            Area: {full.data.area_value} {full.data.area_unit}
          </Body>
        ) : null}
        {full.data ? <Muted>Road access: {full.data.road_access.replace(/_/g, " ")} · Title: {full.data.title_status.replace(/_/g, " ")}</Muted> : null}
        {p.latitude && p.longitude ? (
          <Pressable onPress={() => openInMaps(p.latitude!, p.longitude!, p.name)}>
            <Text style={{ color: colors.primary, fontWeight: "600" }}>Navigate to site</Text>
          </Pressable>
        ) : null}
      </Card>

      {can("site_visit.write") ? <Button title="Schedule visit" onPress={() => router.push(`/visit/new?property=${id}`)} /> : null}

      {can("owner.read") ? (
        <>
          <Heading>Owners</Heading>
          {!online ? <Muted>Owner details load when you are online.</Muted> : null}
          {(owners.data ?? [])
            .filter((o) => o.is_current)
            .map((o) => (
              <Card key={o.id}>
                <Row style={{ justifyContent: "space-between" }}>
                  <Body>{o.owner.full_name}</Body>
                  <Badge label={o.verification_status} />
                </Row>
                <Muted>
                  {o.ownership_type.replace(/_/g, " ")}
                  {o.share_percent ? ` · ${o.share_percent}%` : ""}
                </Muted>
                {o.owner.contacts
                  .filter((c) => c.kind === "phone" || c.kind === "whatsapp")
                  .map((c) => (
                    <Pressable key={c.id} onPress={() => void Linking.openURL(`tel:${c.value.replace(/[^\d+]/g, "")}`)}>
                      <Text style={{ color: colors.primary }}>
                        {c.label ?? c.kind}: {c.value}
                      </Text>
                    </Pressable>
                  ))}
              </Card>
            ))}
          {online && owners.data && !owners.data.some((o) => o.is_current) ? <Muted>No current owners recorded.</Muted> : null}
        </>
      ) : null}

      <Heading>Visits</Heading>
      {visits.length ? visits.map((v) => <VisitCard key={v.id} visit={v} />) : <Muted>No visits on this device for this property.</Muted>}

      <Row style={{ justifyContent: "space-between" }}>
        <Heading>Open tasks</Heading>
        {can("task.write") ? (
          <Pressable onPress={() => router.push(`/task/new?property=${id}`)}>
            <Text style={{ color: colors.primary, fontWeight: "600" }}>+ Add</Text>
          </Pressable>
        ) : null}
      </Row>
      {tasks.length ? tasks.map((t) => <TaskRow key={t.id} task={t} />) : <Muted>No open tasks.</Muted>}
    </Screen>
  );
}
