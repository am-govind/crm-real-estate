import { router } from "expo-router";
import { useState } from "react";

import { VisitCard } from "../../src/components/items";
import { Button, Choice, Empty, Screen } from "../../src/components/ui";
import { syncNow, useOffline } from "../../src/lib/offline";

type Filter = "upcoming" | "past" | "all";

export default function VisitsScreen() {
  const [filter, setFilter] = useState<Filter>("upcoming");
  const [refreshing, setRefreshing] = useState(false);
  const visitsMap = useOffline((s) => s.visits);

  const all = Object.values(visitsMap);
  const upcoming = (s: string) => s === "scheduled" || s === "in_progress";
  const visits =
    filter === "upcoming"
      ? all.filter((v) => upcoming(v.status)).sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start))
      : (filter === "past" ? all.filter((v) => !upcoming(v.status)) : all).sort((a, b) => b.scheduled_start.localeCompare(a.scheduled_start));

  return (
    <Screen
      refreshing={refreshing}
      onRefresh={async () => {
        setRefreshing(true);
        await syncNow({ full: true });
        setRefreshing(false);
      }}
    >
      <Button title="New visit" onPress={() => router.push("/visit/new")} />
      <Choice<Filter>
        value={filter}
        onChange={setFilter}
        options={[
          { value: "upcoming", label: "Upcoming" },
          { value: "past", label: "Past" },
          { value: "all", label: "All" },
        ]}
      />
      {visits.length ? visits.map((v) => <VisitCard key={v.id} visit={v} />) : <Empty>No visits.</Empty>}
    </Screen>
  );
}
