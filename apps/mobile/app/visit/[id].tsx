import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, Image, Pressable, Text, View } from "react-native";
import { colors } from "@landcrm/ui";

import { TaskRow } from "../../src/components/items";
import { Badge, Body, Button, Card, Empty, Field, Heading, Input, Loading, Muted, Row, Screen, formatDateTime } from "../../src/components/ui";
import { api } from "../../src/lib/api";
import { currentFix } from "../../src/lib/location";
import {
  addNote, checkIn, checkOut, isLocalId, pendingNotes, pendingPhotos, queuePhoto, syncNow, useOffline, type LocalVisit,
} from "../../src/lib/offline";
import { useSession } from "../../src/lib/session";
import { getAccessToken, getTenantId } from "../../src/lib/tokens";

function useAuthHeaders() {
  const [headers, setHeaders] = useState<Record<string, string> | null>(null);
  useEffect(() => {
    void getAccessToken().then((token) => {
      const h: Record<string, string> = {};
      if (token) h.Authorization = `Bearer ${token}`;
      const tenant = getTenantId();
      if (tenant) h["X-Tenant-Id"] = tenant;
      setHeaders(h);
    });
  }, []);
  return headers;
}

export default function VisitScreen() {
  const { id: rawId = "" } = useLocalSearchParams<{ id: string }>();
  const id = decodeURIComponent(rawId);
  const { me, can } = useSession();
  const queryClient = useQueryClient();
  const online = useOffline((s) => s.online);

  // A locally created visit is replaced by its server copy once synced; follow it.
  const cached = useOffline((s): LocalVisit | undefined => {
    const direct = s.visits[id];
    if (direct && !(isLocalId(id) && direct.client_ref && s.refs[direct.client_ref])) return direct;
    const ref = isLocalId(id) ? id.slice("local:".length) : null;
    const serverId = ref ? s.refs[ref] : null;
    return (serverId && s.visits[serverId]) || direct;
  });
  const serverId = useOffline((s) => (isLocalId(id) ? s.refs[id.slice("local:".length)] : id));
  // Re-render when queued notes or photos change; pendingNotes/pendingPhotos read the store directly.
  useOffline((s) => s.outbox);
  useOffline((s) => s.media);

  const detail = useQuery({
    queryKey: ["visit", serverId],
    queryFn: () => api.siteVisits.get(serverId!),
    enabled: !!serverId && online,
  });
  const visit: LocalVisit | undefined = cached ?? detail.data;
  const tasksMap = useOffline((s) => s.tasks);
  const followUps = Object.values(tasksMap).filter((t) => t.site_visit_id && (t.site_visit_id === serverId || t.site_visit_id === id));
  const property = useOffline((s) => (visit?.property_id ? s.properties[visit.property_id] : undefined));

  const [note, setNote] = useState("");
  const [outcome, setOutcome] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const headers = useAuthHeaders();

  if (!visit) return detail.isLoading ? <Loading /> : <Empty>Visit not available offline.</Empty>;

  const writable = can("site_visit.write");
  const withFix = async (label: string, fn: (fix: Awaited<ReturnType<typeof currentFix>>) => void, required: boolean) => {
    setBusy(label);
    try {
      const fix = await currentFix();
      if (!fix && required) {
        Alert.alert("Location needed", "Allow location access to check in or out of a site visit.");
        return;
      }
      fn(fix);
    } finally {
      setBusy(null);
    }
  };

  const takePhoto = async (fromCamera: boolean) => {
    const perm = fromCamera ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return Alert.alert("Permission needed", "Allow access to attach photos.");
    const opts: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], quality: 0.7, exif: false };
    const res = fromCamera ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
    if (res.canceled || !res.assets[0]) return;
    const asset = res.assets[0];
    const fix = await currentFix().catch(() => null);
    queuePhoto(
      visit,
      { uri: asset.uri, name: asset.fileName ?? `visit-${Date.now()}.jpg`, type: asset.mimeType ?? "image/jpeg" },
      fix,
    );
  };

  const cancelVisit = () =>
    Alert.alert("Cancel visit?", "Attendees will see it as cancelled.", [
      { text: "Keep", style: "cancel" },
      {
        text: "Cancel visit",
        style: "destructive",
        onPress: async () => {
          try {
            await api.siteVisits.update(serverId!, { status: "cancelled" });
            await syncNow();
            void queryClient.invalidateQueries({ queryKey: ["visit", serverId] });
          } catch (err) {
            Alert.alert("Could not cancel", (err as Error).message);
          }
        },
      },
    ]);

  const notesQueued = pendingNotes(visit);
  const photosQueued = pendingPhotos(visit);
  const attendees = detail.data?.attendees ?? visit.attendees;

  return (
    <Screen
      onRefresh={async () => {
        await syncNow();
        void detail.refetch();
      }}
    >
      <Stack.Screen options={{ title: visit.title }} />
      <Card>
        <Row style={{ justifyContent: "space-between" }}>
          <Heading>{visit.title}</Heading>
          <Badge label={visit.pending ? "not synced" : visit.status} status={visit.pending ? "pending" : visit.status} />
        </Row>
        <Muted>Scheduled {formatDateTime(visit.scheduled_start)}{visit.scheduled_end ? ` – ${formatDateTime(visit.scheduled_end)}` : ""}</Muted>
        {visit.meeting_point ? <Body>Meet at: {visit.meeting_point}</Body> : null}
        {visit.purpose ? <Body>{visit.purpose}</Body> : null}
        {property || visit.property_id ? (
          <Pressable onPress={() => router.push(`/property/${visit.property_id}`)}>
            <Text style={{ color: colors.primary }}>{property ? `${property.code} · ${property.name}` : "Open property"}</Text>
          </Pressable>
        ) : null}
        {visit.check_in_at ? <Muted>Checked in {formatDateTime(visit.check_in_at)}</Muted> : null}
        {visit.check_out_at ? <Muted>Checked out {formatDateTime(visit.check_out_at)}</Muted> : null}
        {visit.outcome ? <Body>Outcome: {visit.outcome}</Body> : null}
      </Card>

      {detail.data?.conflicts.length ? (
        <Card>
          <Heading>Schedule conflicts</Heading>
          {detail.data.conflicts.map((c) => (
            <Muted key={c.visit_id}>{c.title} · {formatDateTime(c.scheduled_start)}</Muted>
          ))}
        </Card>
      ) : null}

      {writable && visit.status === "scheduled" ? (
        <Button title="Check in here" busy={busy === "in"} onPress={() => withFix("in", (fix) => checkIn(visit, fix!), true)} />
      ) : null}
      {writable && visit.status === "in_progress" ? (
        <Card>
          <Field label="Outcome">
            <Input value={outcome} onChangeText={setOutcome} placeholder="What was agreed or observed?" multiline />
          </Field>
          <Button title="Check out" busy={busy === "out"} onPress={() => withFix("out", (fix) => checkOut(visit, fix!, outcome.trim() || undefined), true)} />
        </Card>
      ) : null}

      <Heading>Attendees</Heading>
      <Card>
        {attendees.length ? (
          attendees.map((a) => (
            <Row key={a.id}>
              <Body>{a.user_id === me?.id ? "You" : a.name ?? (a.owner_id ? "Owner" : "Team member")}</Body>
              {a.is_assigned ? <Badge label="assigned" status="info" /> : null}
              {a.attended != null ? <Badge label={a.attended ? "attended" : "absent"} status={a.attended ? "completed" : "missing"} /> : null}
            </Row>
          ))
        ) : (
          <Muted>No attendees listed.</Muted>
        )}
      </Card>

      <Heading>Notes</Heading>
      {writable && visit.status !== "cancelled" ? (
        <Card>
          <Input value={note} onChangeText={setNote} placeholder="Add a field note" multiline />
          <Button
            title="Add note"
            disabled={!note.trim()}
            busy={busy === "note"}
            onPress={() =>
              withFix("note", (fix) => {
                addNote(visit, note.trim(), fix);
                setNote("");
              }, false)
            }
          />
        </Card>
      ) : null}
      {notesQueued.map((n) => (
        <Card key={n.client_ref}>
          <Body>{String(n.payload.body)}</Body>
          <Muted>Waiting to sync · {formatDateTime(n.payload.recorded_at as string)}</Muted>
        </Card>
      ))}
      {(detail.data?.notes ?? []).map((n) => (
        <Card key={n.id}>
          <Body>{n.body}</Body>
          <Muted>{formatDateTime(n.recorded_at)}</Muted>
        </Card>
      ))}
      {!notesQueued.length && !detail.data?.notes.length ? <Muted>{online ? "No notes yet." : "Saved notes load when you are online."}</Muted> : null}

      <Heading>Photos</Heading>
      {writable && visit.status !== "cancelled" ? (
        <Row>
          <View style={{ flex: 1 }}>
            <Button kind="secondary" title="Take photo" onPress={() => void takePhoto(true)} />
          </View>
          <View style={{ flex: 1 }}>
            <Button kind="secondary" title="From library" onPress={() => void takePhoto(false)} />
          </View>
        </Row>
      ) : null}
      <Row>
        {photosQueued.map((p) => (
          <View key={p.client_ref}>
            <Image source={{ uri: p.uri }} style={{ width: 96, height: 96, borderRadius: 8, opacity: 0.6 }} />
            <Muted>Queued</Muted>
          </View>
        ))}
        {headers
          ? (detail.data?.media ?? [])
              .filter((m) => m.content_type.startsWith("image/"))
              .map((m) => (
                <Image key={m.id} source={{ uri: api.siteVisits.mediaUrl(detail.data!.id, m.id), headers }} style={{ width: 96, height: 96, borderRadius: 8 }} />
              ))
          : null}
      </Row>

      <Row style={{ justifyContent: "space-between" }}>
        <Heading>Follow-up tasks</Heading>
        {can("task.write") ? (
          <Pressable onPress={() => router.push(`/task/new?visit=${encodeURIComponent(id)}`)}>
            <Text style={{ color: colors.primary, fontWeight: "600" }}>+ Add</Text>
          </Pressable>
        ) : null}
      </Row>
      {followUps.length ? followUps.map((t) => <TaskRow key={t.id} task={t} />) : <Muted>No follow-up tasks.</Muted>}

      {writable && online && serverId && visit.status === "scheduled" ? <Button kind="danger" title="Cancel visit" onPress={cancelVisit} /> : null}
    </Screen>
  );
}
