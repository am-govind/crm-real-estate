/**
 * Offline-first field data. Visits, tasks and assigned properties are cached locally from
 * /sync/pull; every field write is queued in an outbox with a stable client_ref and pushed
 * to /sync/push when online. The server treats replays idempotently, so retries are safe.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import NetInfo from "@react-native-community/netinfo";
import type { SyncOp, SyncPull } from "@landcrm/api-client";
import type { SiteVisit, Task } from "@landcrm/domain";
import * as Crypto from "expo-crypto";
import { useSyncExternalStore } from "react";

import { api } from "./api";

export type CachedProperty = SyncPull["properties"][number];

export interface LocalVisit extends SiteVisit {
  /** True for visits created on this device that the server has not acknowledged yet. */
  pending?: boolean;
}

export interface LocalTask extends Task {
  pending?: boolean;
}

export interface OutboxItem extends SyncOp {
  queued_at: string;
  /** For task.update on a task created offline: sent once the create is acknowledged. */
  task_client_ref?: string;
}

export interface MediaItem {
  client_ref: string;
  visit_id?: string;
  visit_client_ref?: string;
  uri: string;
  name: string;
  type: string;
  caption?: string;
  latitude?: number;
  longitude?: number;
  captured_at: string;
  queued_at: string;
}

export interface FailedItem {
  client_ref: string;
  label: string;
  error: string;
  failed_at: string;
}

interface State {
  since: string | null;
  lastSyncedAt: string | null;
  visits: Record<string, LocalVisit>;
  tasks: Record<string, LocalTask>;
  properties: Record<string, CachedProperty>;
  outbox: OutboxItem[];
  media: MediaItem[];
  failed: FailedItem[];
  /** client_ref -> server id for acknowledged creates. */
  refs: Record<string, string>;
  syncing: boolean;
  online: boolean;
}

const empty = (): State => ({
  since: null, lastSyncedAt: null, visits: {}, tasks: {}, properties: {}, outbox: [], media: [], failed: [], refs: {}, syncing: false, online: true,
});

let state: State = empty();
let storageKey: string | null = null;
const listeners = new Set<() => void>();

function set(patch: Partial<State>, persist = true) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
  if (persist && storageKey) {
    const { syncing: _s, online: _o, ...rest } = state;
    void AsyncStorage.setItem(storageKey, JSON.stringify(rest));
  }
}

export function useOffline<T>(selector: (s: State) => T): T {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => selector(state),
  );
}

export function getOfflineState() {
  return state;
}

/** Loads the cache for a user and tenant; each pair gets its own isolated store. */
export async function openStore(userId: string, tenantId: string) {
  storageKey = `landcrm.offline.${userId}.${tenantId}`;
  const raw = await AsyncStorage.getItem(storageKey);
  state = raw ? { ...empty(), ...(JSON.parse(raw) as Partial<State>) } : empty();
  listeners.forEach((l) => l());
}

export function closeStore() {
  storageKey = null;
  state = empty();
  listeners.forEach((l) => l());
}

export const newRef = () => Crypto.randomUUID();
export const localVisitId = (clientRef: string) => `local:${clientRef}`;
export const isLocalId = (id: string) => id.startsWith("local:");

/** Identifies a visit in a sync op: server id if known, otherwise its client_ref. */
function visitTarget(visit: LocalVisit): Pick<SyncOp, "visit_id" | "visit_client_ref"> {
  if (!isLocalId(visit.id)) return { visit_id: visit.id };
  const ref = visit.client_ref!;
  return state.refs[ref] ? { visit_id: state.refs[ref] } : { visit_client_ref: ref };
}

function enqueue(op: SyncOp & { task_client_ref?: string }, patch: Partial<State> = {}) {
  set({ ...patch, outbox: [...state.outbox, { ...op, queued_at: new Date().toISOString() }] });
  void syncNow();
}

export interface NewVisit {
  property_id?: string;
  deal_id?: string;
  title: string;
  purpose?: string;
  scheduled_start: string;
  scheduled_end?: string;
  meeting_point?: string;
  attendees: { user_id?: string; name?: string; is_assigned?: boolean }[];
}

export function createVisit(input: NewVisit, currentUserId: string): string {
  const ref = newRef();
  const now = new Date().toISOString();
  const local: LocalVisit = {
    id: localVisitId(ref), property_id: input.property_id ?? null, deal_id: input.deal_id ?? null, title: input.title,
    purpose: input.purpose ?? null, scheduled_start: input.scheduled_start, scheduled_end: input.scheduled_end ?? null,
    status: "scheduled", outcome: null, meeting_point: input.meeting_point ?? null, check_in_at: null, check_in_lat: null,
    check_in_lng: null, check_in_accuracy_m: null, check_out_at: null, check_out_lat: null, check_out_lng: null,
    client_ref: ref, created_by_id: currentUserId, created_at: now, updated_at: now, pending: true,
    attendees: input.attendees.map((a, i) => ({
      id: `local:${ref}:${i}`, user_id: a.user_id ?? null, owner_id: null, name: a.name ?? null, contact: null,
      role: "attendee", is_assigned: !!a.is_assigned, attended: null,
    })),
  };
  enqueue({ op: "site_visit.create", client_ref: ref, payload: { ...input } }, { visits: { ...state.visits, [local.id]: local } });
  return local.id;
}

export interface Fix {
  latitude: number;
  longitude: number;
  accuracy_m?: number;
}

export function checkIn(visit: LocalVisit, fix: Fix) {
  const recorded_at = new Date().toISOString();
  const updated: LocalVisit = {
    ...visit, status: "in_progress", check_in_at: visit.check_in_at ?? recorded_at,
    check_in_lat: visit.check_in_lat ?? fix.latitude, check_in_lng: visit.check_in_lng ?? fix.longitude,
    check_in_accuracy_m: visit.check_in_accuracy_m ?? fix.accuracy_m ?? null,
  };
  enqueue(
    { op: "site_visit.check_in", client_ref: newRef(), ...visitTarget(visit), payload: { ...fix, recorded_at } },
    { visits: { ...state.visits, [visit.id]: updated } },
  );
}

export function checkOut(visit: LocalVisit, fix: Fix, outcome?: string) {
  const recorded_at = new Date().toISOString();
  const updated: LocalVisit = {
    ...visit, status: "completed", outcome: outcome ?? visit.outcome, check_out_at: recorded_at, check_out_lat: fix.latitude, check_out_lng: fix.longitude,
  };
  enqueue(
    { op: "site_visit.check_out", client_ref: newRef(), ...visitTarget(visit), payload: { ...fix, recorded_at, outcome } },
    { visits: { ...state.visits, [visit.id]: updated } },
  );
}

export function addNote(visit: LocalVisit, body: string, fix?: Fix | null) {
  enqueue({
    op: "site_visit.note", client_ref: newRef(), ...visitTarget(visit),
    payload: { body, latitude: fix?.latitude, longitude: fix?.longitude, recorded_at: new Date().toISOString() },
  });
}

export function pendingNotes(visit: LocalVisit) {
  const target = visitTarget(visit);
  return state.outbox.filter(
    (o) => o.op === "site_visit.note" && ((target.visit_id && o.visit_id === target.visit_id) || (visit.client_ref && o.visit_client_ref === visit.client_ref)),
  );
}

export function queuePhoto(visit: LocalVisit, photo: { uri: string; name: string; type: string; caption?: string }, fix?: Fix | null) {
  const target = visitTarget(visit);
  const item: MediaItem = {
    client_ref: newRef(), ...target, ...photo, latitude: fix?.latitude, longitude: fix?.longitude,
    captured_at: new Date().toISOString(), queued_at: new Date().toISOString(),
  };
  set({ media: [...state.media, item] });
  void syncNow();
}

export function pendingPhotos(visit: LocalVisit) {
  const target = visitTarget(visit);
  return state.media.filter((m) => (target.visit_id && m.visit_id === target.visit_id) || (visit.client_ref && m.visit_client_ref === visit.client_ref));
}

export interface NewTask {
  title: string;
  description?: string;
  priority?: string;
  due_date?: string;
  assignee_id?: string;
  property_id?: string;
  deal_id?: string;
}

export function createTask(input: NewTask, currentUserId: string, visit?: LocalVisit) {
  const ref = newRef();
  const now = new Date().toISOString();
  const target = visit ? visitTarget(visit) : {};
  const payload: Record<string, unknown> = {
    ...input,
    property_id: input.property_id ?? visit?.property_id ?? undefined,
    deal_id: input.deal_id ?? visit?.deal_id ?? undefined,
    site_visit_id: target.visit_id,
  };
  const local: LocalTask = {
    id: `local:${ref}`, title: input.title, description: input.description ?? null, status: "open", priority: input.priority ?? "medium",
    due_date: input.due_date ?? null, assignee_id: input.assignee_id ?? currentUserId, property_id: (payload.property_id as string) ?? null,
    deal_id: (payload.deal_id as string) ?? null, deal_stage_id: null, site_visit_id: target.visit_id ?? visit?.id ?? null,
    completed_at: null, created_by_id: currentUserId, client_ref: ref, created_at: now, updated_at: now, pending: true,
  };
  enqueue(
    { op: "task.create", client_ref: ref, visit_client_ref: target.visit_client_ref, payload },
    { tasks: { ...state.tasks, [local.id]: local } },
  );
}

export function updateTaskStatus(task: LocalTask, status: string) {
  const updated: LocalTask = { ...task, status, completed_at: status === "done" ? new Date().toISOString() : null };
  const serverId = isLocalId(task.id) ? state.refs[task.client_ref ?? ""] : task.id;
  const target = serverId ? { task_id: serverId } : { task_client_ref: task.client_ref ?? undefined };
  enqueue({ op: "task.update", client_ref: newRef(), ...target, payload: { status } }, { tasks: { ...state.tasks, [task.id]: updated } });
}

export function dismissFailure(clientRef: string) {
  set({ failed: state.failed.filter((f) => f.client_ref !== clientRef) });
}

function describe(op: SyncOp) {
  const labels: Record<SyncOp["op"], string> = {
    "site_visit.create": "Create visit", "site_visit.check_in": "Check in", "site_visit.check_out": "Check out",
    "site_visit.note": "Visit note", "task.create": "Create task", "task.update": "Update task",
  };
  const title = (op.payload.title as string | undefined) ?? (op.payload.body as string | undefined)?.slice(0, 40);
  return title ? `${labels[op.op]}: ${title}` : labels[op.op];
}

async function pushOutbox() {
  for (;;) {
    const batch = state.outbox.filter((o) => !o.task_client_ref).slice(0, 100);
    if (!batch.length) break;
    const results = await api.sync.push(batch.map(({ queued_at: _q, task_client_ref: _t, ...op }) => op));
    const done = new Set<string>();
    const refs = { ...state.refs };
    const failed = [...state.failed];
    for (const r of results) {
      done.add(r.client_ref);
      const op = batch.find((b) => b.client_ref === r.client_ref);
      if (r.status === "applied" && r.id) {
        if (op?.op === "site_visit.create" || op?.op === "task.create") refs[r.client_ref] = r.id;
      } else if (r.status === "error" && op) {
        failed.push({ client_ref: r.client_ref, label: describe(op), error: r.error ?? "Rejected by server", failed_at: new Date().toISOString() });
      }
    }
    // Later ops may still reference a visit or task by client_ref; point them at the server id now.
    const failedRefs = new Set(failed.map((f) => f.client_ref));
    const outbox = state.outbox
      .filter((o) => !done.has(o.client_ref) && !(o.task_client_ref && failedRefs.has(o.task_client_ref)))
      .map((o) => {
        if (o.task_client_ref && refs[o.task_client_ref]) return { ...o, task_id: refs[o.task_client_ref], task_client_ref: undefined };
        if (o.visit_client_ref && refs[o.visit_client_ref] && o.op !== "task.create") return { ...o, visit_id: refs[o.visit_client_ref], visit_client_ref: undefined };
        return o;
      });
    const media = state.media.filter((m) => !(m.visit_client_ref && failedRefs.has(m.visit_client_ref))).map((m) => (m.visit_client_ref && refs[m.visit_client_ref] ? { ...m, visit_id: refs[m.visit_client_ref], visit_client_ref: undefined } : m));
    set({ outbox, media, refs, failed });
    if (done.size === 0) break;
  }
}

async function uploadMedia() {
  for (const item of [...state.media]) {
    if (!item.visit_id) continue;
    const form = new FormData();
    form.append("file", { uri: item.uri, name: item.name, type: item.type } as unknown as Blob);
    form.append("client_ref", item.client_ref);
    form.append("captured_at", item.captured_at);
    if (item.caption) form.append("caption", item.caption);
    if (item.latitude != null) form.append("latitude", String(item.latitude));
    if (item.longitude != null) form.append("longitude", String(item.longitude));
    try {
      await api.siteVisits.uploadMedia(item.visit_id, form);
      set({ media: state.media.filter((m) => m.client_ref !== item.client_ref) });
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status && status >= 400 && status < 500 && status !== 401 && status !== 429) {
        set({
          media: state.media.filter((m) => m.client_ref !== item.client_ref),
          failed: [...state.failed, { client_ref: item.client_ref, label: `Photo ${item.name}`, error: (err as Error).message, failed_at: new Date().toISOString() }],
        });
      } else {
        throw err;
      }
    }
  }
}

async function pull(full: boolean) {
  const data = await api.sync.pull(full ? undefined : state.since ?? undefined);
  const visits: Record<string, LocalVisit> = full ? {} : { ...state.visits };
  const tasks: Record<string, LocalTask> = full ? {} : { ...state.tasks };
  const properties: Record<string, CachedProperty> = full ? {} : { ...state.properties };
  for (const v of data.site_visits) visits[v.id] = v;
  for (const t of data.tasks) tasks[t.id] = t;
  for (const p of data.properties) properties[p.id] = p;
  const serverRefs = new Set([...data.site_visits.map((v) => v.client_ref), ...data.tasks.map((t) => t.client_ref)].filter(Boolean));
  // Keep local rows the server has not confirmed yet; drop the ones it now returns.
  for (const [id, v] of Object.entries(state.visits)) {
    if (v.pending) {
      if (serverRefs.has(v.client_ref) || state.refs[v.client_ref ?? ""]) delete visits[id];
      else visits[id] = v;
    }
  }
  for (const [id, t] of Object.entries(state.tasks)) {
    if (t.pending) {
      if (serverRefs.has(t.client_ref) || state.refs[t.client_ref ?? ""]) delete tasks[id];
      else tasks[id] = t;
    }
  }
  set({ visits, tasks, properties, since: data.server_time, lastSyncedAt: new Date().toISOString() });
}

let inFlight: Promise<void> | null = null;

/** Push queued work, upload photos, then pull changes. Safe to call often; concurrent calls share one run. */
export function syncNow(opts: { full?: boolean } = {}): Promise<void> {
  if (!storageKey) return Promise.resolve();
  inFlight ??= (async () => {
    const net = await NetInfo.fetch();
    const online = net.isConnected !== false && net.isInternetReachable !== false;
    set({ online }, false);
    if (!online) return;
    set({ syncing: true }, false);
    try {
      await pushOutbox();
      await uploadMedia();
      await pull(!!opts.full || !state.since);
    } finally {
      set({ syncing: false }, false);
    }
  })()
    .catch(() => undefined)
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

/** Re-sync on reconnect and on a timer while the app is open. */
export function startBackgroundSync(intervalMs = 60_000) {
  const unsubscribe = NetInfo.addEventListener((s) => {
    const online = s.isConnected !== false && s.isInternetReachable !== false;
    const wasOffline = !state.online;
    set({ online }, false);
    if (online && wasOffline) void syncNow();
  });
  const timer = setInterval(() => void syncNow(), intervalMs);
  return () => {
    unsubscribe();
    clearInterval(timer);
  };
}
