import { router } from "expo-router";
import { useState } from "react";
import { Alert, Pressable, Text } from "react-native";
import { colors } from "@landcrm/ui";

import { TaskRow, VisitCard } from "../../src/components/items";
import { Body, Button, Card, Empty, Heading, Muted, Row, Screen, Title, formatDateTime } from "../../src/components/ui";
import { dismissFailure, getOfflineState, syncNow, useOffline } from "../../src/lib/offline";
import { useSession } from "../../src/lib/session";

const isToday = (iso: string) => new Date(iso).toDateString() === new Date().toDateString();

export default function TodayScreen() {
  const { me, signOut } = useSession();
  const [refreshing, setRefreshing] = useState(false);
  const visitsMap = useOffline((s) => s.visits);
  const tasksMap = useOffline((s) => s.tasks);
  const failed = useOffline((s) => s.failed);
  const lastSyncedAt = useOffline((s) => s.lastSyncedAt);
  const syncing = useOffline((s) => s.syncing);

  const visits = Object.values(visitsMap)
    .filter((v) => v.status === "in_progress" || (v.status === "scheduled" && isToday(v.scheduled_start)))
    .sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start));
  const today = new Date().toISOString().slice(0, 10);
  const tasks = Object.values(tasksMap)
    .filter((t) => t.assignee_id === me?.id && !["done", "cancelled"].includes(t.status) && !!t.due_date && t.due_date <= today)
    .sort((a, b) => (a.due_date ?? "").localeCompare(b.due_date ?? ""));

  const refresh = async () => {
    setRefreshing(true);
    await syncNow({ full: true });
    setRefreshing(false);
  };

  const confirmSignOut = () => {
    const { outbox, media } = getOfflineState();
    const pending = outbox.length + media.length;
    if (!pending) return void signOut();
    Alert.alert("Unsynced changes", `${pending} change(s) have not synced yet and will be lost if you sign out.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out anyway", style: "destructive", onPress: () => void signOut() },
    ]);
  };

  return (
    <Screen onRefresh={refresh} refreshing={refreshing}>
      <Title>Hello{me?.display_name ? `, ${me.display_name.split(" ")[0]}` : ""}</Title>
      <Muted>{syncing ? "Syncing…" : `Last synced ${formatDateTime(lastSyncedAt)}`}</Muted>

      {failed.length ? (
        <Card>
          <Heading>Changes rejected by the server</Heading>
          {failed.map((f) => (
            <Row key={f.client_ref} style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
              <Body>
                {f.label}: {f.error}
              </Body>
              <Pressable onPress={() => dismissFailure(f.client_ref)}>
                <Text style={{ color: colors.primary }}>Dismiss</Text>
              </Pressable>
            </Row>
          ))}
        </Card>
      ) : null}

      <Row style={{ justifyContent: "space-between" }}>
        <Heading>Today's visits</Heading>
        <Pressable onPress={() => router.push("/visit/new")}>
          <Text style={{ color: colors.primary, fontWeight: "600" }}>+ New visit</Text>
        </Pressable>
      </Row>
      {visits.length ? visits.map((v) => <VisitCard key={v.id} visit={v} />) : <Empty>No visits today.</Empty>}

      <Heading>Due and overdue tasks</Heading>
      {tasks.length ? tasks.map((t) => <TaskRow key={t.id} task={t} />) : <Empty>Nothing due.</Empty>}

      <Button kind="secondary" title="Sign out" onPress={confirmSignOut} />
    </Screen>
  );
}
