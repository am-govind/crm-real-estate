import type {
  Agreement,
  AuditEvent,
  CrmDocument,
  DDSummary,
  Deal,
  DealListItem,
  DealScore,
  DealStage,
  DocumentClass,
  DocumentCompleteness,
  DueDiligenceItem,
  FinancialSummary,
  GeoJSONPolygon,
  GeoUnit,
  GeometryVersion,
  MapPin,
  MapUpload,
  MatchCandidate,
  Me,
  NearbyFeature,
  NegotiationEntry,
  Notification,
  Owner,
  OwnershipSnapshot,
  OwnershipSummary,
  Page,
  Payment,
  PaymentMilestone,
  Property,
  PropertyOwner,
  SiteData,
  SiteDetail,
  SiteRecord,
  SiteRevision,
  SiteVisit,
  SiteVisitDetail,
  SiteVisitMedia,
  SiteVisitNote,
  StageTransition,
  Task,
  UserSummary,
  WorkflowActivation,
  WorkflowTemplate,
  WorkflowVersion,
} from "@landcrm/domain";

import { Http, type ClientOptions, type Query } from "./http";

export { ApiError, buildQuery } from "./http";
export type { ClientOptions, Query } from "./http";

type Body = Record<string, unknown>;
const V1 = "/api/v1";

export function createApiClient(opts: ClientOptions) {
  const http = new Http(opts);
  const v = (p: string) => `${V1}${p}`;

  return {
    http,
    auth: {
      loginUrl: (returnTo?: string) => http.url("/auth/login", { return_to: returnTo }),
      logout: () => http.post<{ end_session_url: string | null }>("/auth/logout"),
    },
    me: () => http.get<Me>(v("/me")),
    permissions: () => http.get<string[]>(v("/permissions")),

    tenant: {
      get: () => http.get<Tenant>(v("/tenant")),
      updateSettings: (settings: Body) => http.patch(v("/tenant/settings"), { settings }),
      users: () => http.get<UserSummary[]>(v("/tenant/users")),
      members: () => http.get<{ membership_id: string; user: UserSummary; is_active: boolean; title: string | null; role_keys: string[] }[]>(v("/tenant/members")),
      updateMember: (id: string, body: Body) => http.patch(v(`/tenant/members/${id}`), body),
      invitations: () => http.get<{ id: string; email: string; role_keys: string[]; accepted_at: string | null; created_at: string }[]>(v("/tenant/invitations")),
      invite: (email: string, role_keys: string[]) => http.post(v("/tenant/invitations"), { email, role_keys }),
      roles: () => http.get<{ id: string; key: string; name: string; description: string | null; is_builtin: boolean; permissions: string[] }[]>(v("/tenant/roles")),
      createRole: (body: Body) => http.post(v("/tenant/roles"), body),
      updateRole: (id: string, body: Body) => http.put(v(`/tenant/roles/${id}`), body),
    },

    admin: {
      tenants: () => http.get<Tenant[]>(v("/admin/tenants")),
      createTenant: (body: { name: string; slug: string; country_code?: string; default_currency?: string; admin_email?: string }) =>
        http.post<Tenant>(v("/admin/tenants"), body),
    },

    audit: (q: Query) => http.get<Page<AuditEvent>>(v("/audit"), q),
    geo: {
      list: (q: Query) => http.get<GeoUnit[]>(v("/geo-units"), q),
      create: (body: Body) => http.post<GeoUnit>(v("/geo-units"), body),
    },

    owners: {
      list: (q?: Query) => http.get<Page<Owner>>(v("/owners"), q),
      get: (id: string) => http.get<Owner>(v(`/owners/${id}`)),
      create: (body: Body) => http.post<Owner>(v("/owners"), body),
      update: (id: string, body: Body) => http.patch<Owner>(v(`/owners/${id}`), body),
      verify: (id: string, status: string, note?: string) => http.post<Owner>(v(`/owners/${id}/verification`), { status, note }),
      addContact: (id: string, body: Body) => http.post(v(`/owners/${id}/contacts`), body),
      removeContact: (id: string, contactId: string) => http.del(v(`/owners/${id}/contacts/${contactId}`)),
    },

    properties: {
      list: (q?: Query) => http.get<Page<Property>>(v("/properties"), q),
      get: (id: string) => http.get<Property>(v(`/properties/${id}`)),
      create: (body: Body) => http.post<Property>(v("/properties"), body),
      update: (id: string, body: Body) => http.patch<Property>(v(`/properties/${id}`), body),
      mapPins: (q?: Query) => http.get<MapPin[]>(v("/properties/map-pins"), q),
      owners: (id: string, includeHistory = false) => http.get<PropertyOwner[]>(v(`/properties/${id}/owners`), { include_history: includeHistory }),
      ownershipSummary: (id: string) => http.get<OwnershipSummary>(v(`/properties/${id}/ownership-summary`)),
      addOwner: (id: string, body: Body) => http.post<PropertyOwner>(v(`/properties/${id}/owners`), body),
      endOwner: (id: string, poId: string, reason: string, valid_to?: string) => http.post(v(`/properties/${id}/owners/${poId}/end`), { reason, valid_to }),
      verifyOwner: (id: string, poId: string, status: string, note?: string) => http.post(v(`/properties/${id}/owners/${poId}/verification`), { status, note }),
      assignments: (id: string) => http.get<{ id: string; user_id: string; role: string }[]>(v(`/properties/${id}/assignments`)),
      assign: (id: string, user_id: string, role = "member") => http.post(v(`/properties/${id}/assignments`), { user_id, role }),
      unassign: (id: string, userId: string) => http.del(v(`/properties/${id}/assignments/${userId}`)),
    },

    workflows: {
      templates: () => http.get<WorkflowTemplate[]>(v("/workflow-templates")),
      version: (id: string) => http.get<WorkflowVersion>(v(`/workflow-versions/${id}`)),
      activations: () => http.get<WorkflowActivation[]>(v("/workflow-activations")),
      activate: (body: Body) => http.post<WorkflowActivation>(v("/workflow-activations"), body),
      updateActivation: (id: string, body: Body) => http.patch<WorkflowActivation>(v(`/workflow-activations/${id}`), body),
      admin: {
        createTemplate: (body: Body) => http.post<WorkflowTemplate>(v("/admin/workflow-templates"), body),
        createVersion: (templateId: string, body: Body) => http.post<WorkflowVersion>(v(`/admin/workflow-templates/${templateId}/versions`), body),
        updateDraft: (versionId: string, body: Body) => http.put<WorkflowVersion>(v(`/admin/workflow-versions/${versionId}`), body),
        publish: (versionId: string) => http.post<WorkflowVersion>(v(`/admin/workflow-versions/${versionId}/publish`)),
        retire: (versionId: string) => http.post<WorkflowVersion>(v(`/admin/workflow-versions/${versionId}/retire`)),
      },
    },

    deals: {
      list: (q?: Query) => http.get<Page<DealListItem>>(v("/deals"), q),
      get: (id: string) => http.get<Deal>(v(`/deals/${id}`)),
      create: (body: Body) => http.post<Deal>(v("/deals"), body),
      update: (id: string, body: Body) => http.patch<Deal>(v(`/deals/${id}`), body),
      stages: (id: string) => http.get<DealStage[]>(v(`/deals/${id}/stages`)),
      transition: (id: string, body: { target_stage_key: string; reason?: string; bypass_incomplete_checklist?: boolean }) =>
        http.post<Deal>(v(`/deals/${id}/transitions`), body),
      transitions: (id: string) => http.get<StageTransition[]>(v(`/deals/${id}/transitions`)),
      close: (id: string, outcome: string, reason: string) => http.post<Deal>(v(`/deals/${id}/close`), { outcome, reason }),
      reopen: (id: string, reason: string, override_active_deal = false) => http.post<Deal>(v(`/deals/${id}/reopen`), { reason, override_active_deal }),
      updateChecklist: (id: string, itemId: string, body: Body) => http.patch<DealStage[]>(v(`/deals/${id}/checklist/${itemId}`), body),
      bypassChecklist: (id: string, itemId: string, reason: string) => http.post<DealStage[]>(v(`/deals/${id}/checklist/${itemId}/bypass`), { reason }),
      assignments: (id: string) => http.get<{ id: string; user_id: string; role: string }[]>(v(`/deals/${id}/assignments`)),
      assign: (id: string, user_id: string, role = "member") => http.post(v(`/deals/${id}/assignments`), { user_id, role }),
      unassign: (id: string, userId: string) => http.del(v(`/deals/${id}/assignments/${userId}`)),
      snapshots: (id: string) => http.get<OwnershipSnapshot[]>(v(`/deals/${id}/ownership-snapshots`)),
      confirmOwnership: (id: string, note?: string) => http.post<OwnershipSnapshot>(v(`/deals/${id}/ownership-snapshots`), { note }),
      dueDiligence: (id: string) => http.get<DueDiligenceItem[]>(v(`/deals/${id}/due-diligence`)),
      dueDiligenceSummary: (id: string) => http.get<DDSummary[]>(v(`/deals/${id}/due-diligence/summary`)),
      createDD: (id: string, body: Body) => http.post<DueDiligenceItem>(v(`/deals/${id}/due-diligence`), body),
      updateDD: (id: string, itemId: string, body: Body) => http.patch<DueDiligenceItem>(v(`/deals/${id}/due-diligence/${itemId}`), body),
      negotiations: (id: string) => http.get<NegotiationEntry[]>(v(`/deals/${id}/negotiations`)),
      addNegotiation: (id: string, body: Body) => http.post<NegotiationEntry>(v(`/deals/${id}/negotiations`), body),
      agreements: (id: string) => http.get<Agreement[]>(v(`/deals/${id}/agreements`)),
      createAgreement: (id: string, body: Body) => http.post<Agreement>(v(`/deals/${id}/agreements`), body),
      updateAgreement: (id: string, agreementId: string, body: Body) => http.patch<Agreement>(v(`/deals/${id}/agreements/${agreementId}`), body),
      audit: (id: string) => http.get<{ id: string; action: string; actor_id: string | null; changes: Record<string, unknown>; metadata: Record<string, unknown>; occurred_at: string }[]>(v(`/deals/${id}/audit`)),
      score: (id: string) => http.get<DealScore | null>(v(`/deals/${id}/score`)),
      computeScore: (id: string) => http.post<DealScore>(v(`/deals/${id}/score`)),
      financials: (id: string) => http.get<FinancialSummary>(v(`/deals/${id}/financials`)),
      milestones: (id: string) => http.get<PaymentMilestone[]>(v(`/deals/${id}/payment-milestones`)),
      createMilestone: (id: string, body: Body) => http.post<PaymentMilestone>(v(`/deals/${id}/payment-milestones`), body),
      updateMilestone: (id: string, mId: string, body: Body) => http.patch<PaymentMilestone>(v(`/deals/${id}/payment-milestones/${mId}`), body),
      decideMilestone: (id: string, mId: string, decision: string, note?: string) => http.post<PaymentMilestone>(v(`/deals/${id}/payment-milestones/${mId}/decision`), { decision, note }),
      cancelMilestone: (id: string, mId: string, reason: string) => http.post<PaymentMilestone>(v(`/deals/${id}/payment-milestones/${mId}/cancel`), { reason }),
      payments: (id: string) => http.get<Payment[]>(v(`/deals/${id}/payments`)),
      recordPayment: (id: string, body: Body) => http.post<Payment>(v(`/deals/${id}/payments`), body),
      decidePayment: (id: string, pId: string, decision: string, note?: string) => http.post<Payment>(v(`/deals/${id}/payments/${pId}/decision`), { decision, note }),
      reversePayment: (id: string, pId: string, reason: string) => http.post<Payment>(v(`/deals/${id}/payments/${pId}/reverse`), { reason }),
    },

    tasks: {
      list: (q?: Query) => http.get<Page<Task>>(v("/tasks"), q),
      create: (body: Body) => http.post<Task>(v("/tasks"), body),
      update: (id: string, body: Body) => http.patch<Task>(v(`/tasks/${id}`), body),
    },

    documents: {
      classes: () => http.get<DocumentClass[]>(v("/document-classes")),
      createClass: (body: Body) => http.post<DocumentClass>(v("/document-classes"), body),
      rules: () => http.get<{ id: string; scope: string; class_id: string; land_types: string[]; is_active: boolean; document_class: DocumentClass }[]>(v("/required-document-rules")),
      createRule: (body: Body) => http.post(v("/required-document-rules"), body),
      deactivateRule: (id: string) => http.del(v(`/required-document-rules/${id}`)),
      list: (q?: Query) => http.get<Page<CrmDocument>>(v("/documents"), q),
      get: (id: string) => http.get<CrmDocument>(v(`/documents/${id}`)),
      upload: (form: FormData) => http.upload<CrmDocument>(v("/documents"), form),
      update: (id: string, body: Body) => http.patch<CrmDocument>(v(`/documents/${id}`), body),
      addVersion: (id: string, form: FormData) => http.upload<CrmDocument>(v(`/documents/${id}/versions`), form),
      downloadUrl: (id: string, versionNo: number) => http.downloadUrl(v(`/documents/${id}/versions/${versionNo}/download`)),
      review: (id: string, decision: string, note?: string) => http.post<CrmDocument>(v(`/documents/${id}/review`), { decision, note }),
      reviews: (id: string) => http.get<{ id: string; decision: string; note: string | null; reviewer_id: string; reviewed_at: string }[]>(v(`/documents/${id}/reviews`)),
      grants: (id: string) => http.get<{ id: string; user_id: string; reason: string; expires_at: string | null; revoked_at: string | null }[]>(v(`/documents/${id}/grants`)),
      grant: (id: string, body: Body) => http.post(v(`/documents/${id}/grants`), body),
      revoke: (id: string, userId: string) => http.del(v(`/documents/${id}/grants/${userId}`)),
      completeness: (q: { property_id?: string; deal_id?: string }) => http.get<DocumentCompleteness>(v("/documents/completeness"), q),
    },

    maps: {
      uploads: (propertyId: string) => http.get<MapUpload[]>(v(`/properties/${propertyId}/map-uploads`)),
      upload: (propertyId: string, form: FormData) => http.upload<MapUpload>(v(`/properties/${propertyId}/map-uploads`), form),
      uploadFileUrl: (uploadId: string) => http.downloadUrl(v(`/map-uploads/${uploadId}/file`)),
      reprocess: (uploadId: string) => http.post<MapUpload>(v(`/map-uploads/${uploadId}/reprocess`)),
      geometries: (propertyId: string) => http.get<GeometryVersion[]>(v(`/properties/${propertyId}/geometries`)),
      activeGeometry: (propertyId: string) => http.get<Feature>(v(`/properties/${propertyId}/geometry/active`)),
      createGeometry: (propertyId: string, body: Body) => http.post<GeometryVersion>(v(`/properties/${propertyId}/geometries`), body),
      submit: (id: string) => http.post<GeometryVersion>(v(`/geometries/${id}/submit`)),
      approve: (id: string, note?: string) => http.post<GeometryVersion>(v(`/geometries/${id}/approve`), { note }),
      reject: (id: string, note: string) => http.post<GeometryVersion>(v(`/geometries/${id}/reject`), { note }),
      nearby: (propertyId: string) => http.get<NearbyFeature[]>(v(`/properties/${propertyId}/nearby`)),
      refreshNearby: (propertyId: string) => http.post(v(`/properties/${propertyId}/nearby/refresh`)),
      geocode: (q: string) => http.get<{ label: string; latitude: number; longitude: number; source: string }[]>(v("/geocode"), { q }),
    },

    siteVisits: {
      list: (q?: Query) => http.get<Page<SiteVisit>>(v("/site-visits"), q),
      get: (id: string) => http.get<SiteVisitDetail>(v(`/site-visits/${id}`)),
      create: (body: Body) => http.post<SiteVisitDetail>(v("/site-visits"), body),
      update: (id: string, body: Body) => http.patch<SiteVisitDetail>(v(`/site-visits/${id}`), body),
      checkIn: (id: string, body: Body) => http.post<SiteVisitDetail>(v(`/site-visits/${id}/check-in`), body),
      checkOut: (id: string, body: Body) => http.post<SiteVisitDetail>(v(`/site-visits/${id}/check-out`), body),
      addNote: (id: string, body: Body) => http.post<SiteVisitNote>(v(`/site-visits/${id}/notes`), body),
      uploadMedia: (id: string, form: FormData) => http.upload<SiteVisitMedia>(v(`/site-visits/${id}/media`), form),
      mediaUrl: (id: string, mediaId: string) => http.downloadUrl(v(`/site-visits/${id}/media/${mediaId}/file`)),
      followUp: (id: string, body: Body) => http.post<Task>(v(`/site-visits/${id}/follow-up-tasks`), body),
    },

    inventory: {
      nextSiteId: () => http.get<{ site_code: string }>(v("/inventory/next-site-id")),
      matches: (data: SiteData, exclude_site_id?: string) => http.post<MatchCandidate[]>(v("/inventory/match-suggestions"), { data, exclude_site_id }),
      search: (q?: Query) => http.get<Page<SiteRecord>>(v("/inventory/sites"), q),
      get: (id: string) => http.get<SiteDetail>(v(`/inventory/sites/${id}`)),
      create: (body: { confirmed_site_code: string; confirmed_new: true; considered_candidates: string[]; data: SiteData; change_note?: string }) =>
        http.post<SiteDetail>(v("/inventory/sites"), body),
      proposeRevision: (id: string, body: { data: SiteData; change_note: string; considered_candidates?: string[] }) =>
        http.post<SiteDetail>(v(`/inventory/sites/${id}/revisions`), body),
      queue: (status = "pending") => http.get<SiteRevision[]>(v("/inventory/revisions"), { status }),
      approve: (revisionId: string, note?: string) => http.post<SiteDetail>(v(`/inventory/revisions/${revisionId}/approve`), { note }),
      reject: (revisionId: string, note: string) => http.post<SiteDetail>(v(`/inventory/revisions/${revisionId}/reject`), { note }),
    },

    scoring: {
      factors: () => http.get<{ key: string; label: string }[]>(v("/scoring/factors")),
      model: () => http.get<{ id: string; name: string; is_active: boolean; factors: { key: string; weight: number; params: Record<string, unknown> }[] }>(v("/scoring/model")),
      updateModel: (body: Body) => http.put(v("/scoring/model"), body),
    },

    reports: {
      controlCenter: (dealId: string) => http.get<ControlCenter>(v(`/reports/deals/${dealId}/control-center`)),
      pipeline: (q?: Query) => http.get<Pipeline>(v("/reports/pipeline"), q),
      dashboard: () => http.get<Dashboard>(v("/reports/dashboard")),
      mapLayers: () => http.get<FeatureCollection<ParcelFeatureProps>>(v("/reports/map-layers")),
    },

    notifications: {
      list: (q?: Query) => http.get<Page<Notification>>(v("/notifications"), q),
      read: (id: string) => http.post(v(`/notifications/${id}/read`)),
      readAll: () => http.post(v("/notifications/read-all")),
      registerDevice: (token: string, platform: "ios" | "android" | "web") => http.post(v("/devices"), { token, platform }),
      unregisterDevice: (token: string) => http.del(v(`/devices/${encodeURIComponent(token)}`)),
    },

    sync: {
      push: (ops: SyncOp[]) => http.post<SyncResult[]>(v("/sync/push"), { ops }),
      pull: (since?: string) => http.get<SyncPull>(v("/sync/pull"), { since }),
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  country_code: string;
  default_currency: string;
  is_active: boolean;
  settings: Record<string, unknown>;
}

export interface Feature<P = object> {
  type: "Feature";
  geometry: GeoJSONPolygon;
  properties: P;
}

export interface FeatureCollection<P = object> {
  type: "FeatureCollection";
  features: Feature<P>[];
}

export interface ParcelFeatureProps {
  property_id: string;
  code: string;
  name: string;
  status: string;
  color: string;
  area_sqm: string | null;
  derived: true;
}

export interface SyncOp {
  op: "site_visit.create" | "site_visit.check_in" | "site_visit.check_out" | "site_visit.note" | "task.create" | "task.update";
  client_ref: string;
  visit_id?: string;
  visit_client_ref?: string;
  task_id?: string;
  payload: Record<string, unknown>;
}

export interface SyncResult {
  client_ref: string;
  status: "applied" | "error";
  id: string | null;
  error: string | null;
}

export interface SyncPull {
  server_time: string;
  site_visits: SiteVisit[];
  tasks: Task[];
  properties: { id: string; code: string; name: string; status: string; latitude: string | null; longitude: string | null; survey_number: string | null; address: string | null; updated_at: string }[];
}

export interface ControlCenter {
  deal: { id: string; code: string; title: string; status: string; priority: string; is_active: boolean; started_at: string; active_override_reason: string | null };
  property: {
    id: string; code: string; name: string; land_type: string; status: string; survey_number: string | null; khasra_number: string | null;
    location: Record<string, string | undefined>; area: { value: string | null; unit: string | null; sqm_derived: string | null };
    latitude: string | null; longitude: string | null; road_access: string; title_status: string; land_use: string | null;
    geometry: { id: string; version: number; area_sqm: string | null; perimeter_m: string | null; derived: true; reviewed_at: string | null } | null;
  };
  stage: {
    current: { key: string; name: string; category: string; color: string | null } | null;
    days_in_stage: number | null; sla_days: number | null; is_overdue: boolean;
    progress: { total_stages: number; completed_stages: number; bypassed_stages: number; percent: number; current_position: number | null };
    stages: { key: string; name: string; status: string; color: string | null }[];
  };
  owners: {
    summary: OwnershipSummary;
    items: { owner_id: string; name: string; share_percent: string | null; ownership_type: string; ownership_verification: string; identity_verification: string; readiness: string }[];
  };
  documents: DocumentCompleteness | null;
  due_diligence: Record<string, DDSummary>;
  financials: FinancialSummary | null;
  next_action: { action: string | null; due_date: string | null; assignee: { id: string; name: string | null } | null; is_overdue: boolean };
  open_tasks: { id: string; title: string; priority: string; status: string; due_date: string | null; assignee_id: string | null }[];
  upcoming_visits: { id: string; title: string; scheduled_start: string; status: string }[];
  score: { total: number; coverage: number; computed_at: string; breakdown: DealScore["breakdown"] } | null;
}

export interface Pipeline {
  activation_id: string | null;
  template_version_id?: string;
  stages: {
    key: string; name: string; color: string | null; category: string; sla_days: number | null; count: number; value: string;
    deals: { deal_id: string; code: string; title: string; priority: string; property_id: string; property_name: string; amount: string | null; currency: string; days_in_stage: number | null; is_stuck: boolean; next_action: string | null; next_action_due: string | null }[];
  }[];
  totals: { deals?: number; value?: string };
}

export interface Dashboard {
  deals: { by_status: Record<string, number>; active: number; pipeline_value: string; won_this_month: number; by_stage: { stage: string; color: string | null; count: number }[] };
  properties: { total: number };
  payments: { due_next_30_days: number; due_next_30_days_amount: string; overdue_milestones: number };
  tasks: { overdue: number; mine_open: number };
  documents: { pending_review: number; expiring_30_days: number; expired: number };
  geometry: { awaiting_review: number };
  inventory: { approved: number; pending_approval: number };
  site_visits: { upcoming_7_days: number };
}
