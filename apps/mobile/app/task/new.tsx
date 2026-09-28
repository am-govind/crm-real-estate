import { useQuery } from "@tanstack/react-query";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert } from "react-native";

import { Button, Choice, Field, Input, Muted, Screen } from "../../src/components/ui";
import { api } from "../../src/lib/api";
import { createTask, useOffline } from "../../src/lib/offline";
import { useSession } from "../../src/lib/session";

type Priority = "low" | "medium" | "high" | "urgent";

export default function NewTaskScreen() {
  const params = useLocalSearchParams<{ visit?: string; property?: string }>();
  const visitId = params.visit ? decodeURIComponent(params.visit) : undefined;
  const { me } = useSession();
  const online = useOffline((s) => s.online);
  const visit = useOffline((s) => (visitId ? s.visits[visitId] : undefined));

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [due, setDue] = useState("");
  const [assignee, setAssignee] = useState<string>(me?.id ?? "");
  const users = useQuery({ queryKey: ["tenant-users"], queryFn: () => api.tenant.users(), enabled: online });

  const save = () => {
    if (!me) return;
    if (!title.trim()) return Alert.alert("Title required");
    if (due && !/^\d{4}-\d{2}-\d{2}$/.test(due)) return Alert.alert("Invalid due date", "Use YYYY-MM-DD.");
    const input = {
      title: title.trim(),
      description: description.trim() || undefined,
      priority,
      due_date: due || undefined,
      assignee_id: assignee || me.id,
      property_id: params.property,
    };
    createTask(input, me.id, visit);
    router.back();
  };

  const assigneeOptions = [
    { value: me?.id ?? "", label: "Me" },
    ...(users.data ?? []).filter((u) => u.id !== me?.id && u.is_active).map((u) => ({ value: u.id, label: u.display_name ?? u.email ?? "User" })),
  ];

  return (
    <Screen>
      {visit ? <Muted>Follow-up for: {visit.title}</Muted> : null}
      <Field label="Title">
        <Input value={title} onChangeText={setTitle} placeholder="Collect 7/12 extract from owner" autoFocus />
      </Field>
      <Field label="Details">
        <Input value={description} onChangeText={setDescription} multiline />
      </Field>
      <Field label="Priority">
        <Choice<Priority>
          value={priority}
          onChange={setPriority}
          options={[
            { value: "low", label: "Low" },
            { value: "medium", label: "Medium" },
            { value: "high", label: "High" },
            { value: "urgent", label: "Urgent" },
          ]}
        />
      </Field>
      <Field label="Due date (YYYY-MM-DD, optional)">
        <Input value={due} onChangeText={setDue} autoCorrect={false} />
      </Field>
      <Field label="Assign to">
        <Choice value={assignee} onChange={setAssignee} options={assigneeOptions} />
        {!online ? <Muted>Assigning to colleagues is available when online.</Muted> : null}
      </Field>
      <Button title="Create task" onPress={save} />
    </Screen>
  );
}
