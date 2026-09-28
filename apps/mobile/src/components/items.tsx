import { router } from "expo-router";
import { Pressable, Text, View } from "react-native";
import { colors } from "@landcrm/ui";

import { updateTaskStatus, useOffline, type LocalTask, type LocalVisit } from "../lib/offline";
import { Badge, Card, Heading, Muted, Row, formatDate, formatDateTime } from "./ui";

export function VisitCard({ visit }: { visit: LocalVisit }) {
  const property = useOffline((s) => (visit.property_id ? s.properties[visit.property_id] : undefined));
  return (
    <Card onPress={() => router.push(`/visit/${encodeURIComponent(visit.id)}`)}>
      <Row style={{ justifyContent: "space-between" }}>
        <Heading>{visit.title}</Heading>
        <Badge label={visit.pending ? "not synced" : visit.status} status={visit.pending ? "pending" : visit.status} />
      </Row>
      <Muted>{formatDateTime(visit.scheduled_start)}{visit.meeting_point ? ` · ${visit.meeting_point}` : ""}</Muted>
      {property ? <Muted>{property.code} · {property.name}</Muted> : null}
    </Card>
  );
}

const nextStatus: Record<string, string> = { open: "in_progress", in_progress: "done", blocked: "in_progress" };

export function TaskRow({ task }: { task: LocalTask }) {
  const overdue = !!task.due_date && task.due_date < new Date().toISOString().slice(0, 10) && !["done", "cancelled"].includes(task.status);
  const next = nextStatus[task.status];
  return (
    <Card>
      <Row style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={{ fontSize: 15, fontWeight: "600", color: colors.text, textDecorationLine: task.status === "done" ? "line-through" : "none" }}>
            {task.title}
          </Text>
          <Row>
            <Badge label={task.pending ? "not synced" : task.status} status={task.pending ? "pending" : task.status} />
            {task.priority !== "medium" ? <Badge label={task.priority} status={task.priority === "urgent" || task.priority === "high" ? "overdue" : undefined} /> : null}
            {task.due_date ? <Muted>{overdue ? "Overdue · " : "Due "}{formatDate(task.due_date)}</Muted> : null}
          </Row>
        </View>
        {next ? (
          <Pressable onPress={() => updateTaskStatus(task, next)} style={{ padding: 8 }} accessibilityRole="button">
            <Text style={{ color: colors.primary, fontWeight: "600" }}>{next === "done" ? "Done" : "Start"}</Text>
          </Pressable>
        ) : null}
      </Row>
      {task.description ? <Muted>{task.description}</Muted> : null}
    </Card>
  );
}
