import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { useEffect, useState } from "react";

import { Badge, Card, Empty, Heading, Input, Loading, Muted, Row, Screen } from "../../src/components/ui";
import { api } from "../../src/lib/api";
import { syncNow, useOffline } from "../../src/lib/offline";

function useDebounced(value: string, ms = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export default function PropertiesScreen() {
  const [q, setQ] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const term = useDebounced(q.trim());
  const cached = useOffline((s) => s.properties);
  const online = useOffline((s) => s.online);

  const needle = term.toLowerCase();
  const assigned = Object.values(cached)
    .filter((p) => !needle || [p.code, p.name, p.survey_number, p.address].some((f) => f?.toLowerCase().includes(needle)))
    .sort((a, b) => a.code.localeCompare(b.code));

  const search = useQuery({
    queryKey: ["properties", "search", term],
    queryFn: () => api.properties.list({ q: term, limit: 25 }),
    enabled: online && term.length >= 2,
  });
  const assignedIds = new Set(assigned.map((p) => p.id));
  const others = (search.data?.items ?? []).filter((p) => !assignedIds.has(p.id));

  return (
    <Screen
      refreshing={refreshing}
      onRefresh={async () => {
        setRefreshing(true);
        await syncNow({ full: true });
        setRefreshing(false);
      }}
    >
      <Input value={q} onChangeText={setQ} placeholder="Search code, name, survey number" autoCorrect={false} clearButtonMode="while-editing" />
      <Heading>Assigned to me</Heading>
      {assigned.length ? (
        assigned.map((p) => (
          <Card key={p.id} onPress={() => router.push(`/property/${p.id}`)}>
            <Row style={{ justifyContent: "space-between" }}>
              <Heading>{p.code}</Heading>
              <Badge label={p.status} />
            </Row>
            <Muted>{p.name}{p.survey_number ? ` · Survey ${p.survey_number}` : ""}</Muted>
          </Card>
        ))
      ) : (
        <Empty>{term ? "No assigned property matches." : "No properties assigned to you."}</Empty>
      )}

      {term.length >= 2 && online ? (
        <>
          <Heading>Other properties</Heading>
          {search.isLoading ? <Loading /> : null}
          {others.map((p) => (
            <Card key={p.id} onPress={() => router.push(`/property/${p.id}`)}>
              <Row style={{ justifyContent: "space-between" }}>
                <Heading>{p.code}</Heading>
                <Badge label={p.status} />
              </Row>
              <Muted>{p.name}</Muted>
            </Card>
          ))}
          {!search.isLoading && !others.length ? <Empty>No other matches.</Empty> : null}
        </>
      ) : null}
    </Screen>
  );
}
