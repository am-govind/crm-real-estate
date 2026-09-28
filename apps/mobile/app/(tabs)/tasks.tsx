import { router } from "expo-router";
import { useState } from "react";

import { TaskRow } from "../../src/components/items";
import { Button, Choice, Empty, Screen } from "../../src/components/ui";
import { syncNow, useOffline } from "../../src/lib/offline";
import { useSession } from "../../src/lib/session";

type Filter = "mine" | "created" | "done";

export default function TasksScreen() {
  const { me, can } = useSession();
  const [filter, setFilter] = useState<Filter>("mine");
  const [refreshing, setRefreshing] = useState(false);
  const tasksMap = useOffline((s) => s.tasks);

  const closed = (s: string) => s === "done" || s === "cancelled";
  const tasks = Object.values(tasksMap)
    .filter((t) =>
      filter === "done" ? closed(t.status) : !closed(t.status) && (filter === "mine" ? t.assignee_id === me?.id : t.created_by_id === me?.id && t.assignee_id !== me?.id),
    )
    .sort((a, b) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999"));

  return (
    <Screen
      refreshing={refreshing}
      onRefresh={async () => {
        setRefreshing(true);
        await syncNow({ full: true });
        setRefreshing(false);
      }}
    >
      {can("task.write") ? <Button title="New task" onPress={() => router.push("/task/new")} /> : null}
      <Choice<Filter>
        value={filter}
        onChange={setFilter}
        options={[
          { value: "mine", label: "Assigned to me" },
          { value: "created", label: "Delegated" },
          { value: "done", label: "Closed" },
        ]}
      />
      {tasks.length ? tasks.map((t) => <TaskRow key={t.id} task={t} />) : <Empty>No tasks.</Empty>}
    </Screen>
  );
}
