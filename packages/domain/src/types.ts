import type { Measurement } from "./measure";

export type UUID = string;
export type ISODate = string;
export type ISODateTime = string;
/** Decimal serialized as string. Never parse to number for arithmetic. */
export type Money = string;
export type DecimalString = string;

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export interface Me {
  id: UUID;
  email: string | null;
  display_name: string | null;
  is_system_admin: boolean;
  tenant_id: UUID | null;
  permissions: string[];
  role_keys: string[];
  memberships: { tenant_id: UUID; tenant_name: string; role_keys: string[] }[];
  terminology: Record<"state" | "district" | "tehsil" | "village", string>;
}

export interface UserSummary {
  id: UUID;
  email: string | null;
  display_name: string | null;
  is_active: boolean;
}

export interface GeoUnit {
  id: UUID;
  tenant_id: UUID | null;
  parent_id: UUID | null;
  level: "state" | "district" | "tehsil" | "village";
  name: string;
  local_name: string | null;
  code: string | null;
}

export interface OwnerContact {
  id: UUID;
  kind: "phone" | "email" | "whatsapp" | "address" | "other";
  value: string;
  label: string | null;
  is_primary: boolean;
}

export interface Owner {
  id: UUID;
  code: string;
  owner_type: string;
  full_name: string;
  local_name: string | null;
  relation_name: string | null;
  date_of_birth: ISODate | null;
  verification_status: "unverified" | "pending" | "verified" | "rejected";
  verified_by_id: UUID | null;
  verified_at: ISODateTime | null;
  verification_note: string | null;
  readiness: "unknown" | "not_interested" | "considering" | "ready_to_sell";
  notes: string | null;
  custom_fields: Record<string, unknown>;
  contacts: OwnerContact[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Property {
  id: UUID;
  code: string;
  name: string;
  land_type: string;
  status: string;
  state_id: UUID | null;
  district_id: UUID | null;
  tehsil_id: UUID | null;
  village_id: UUID | null;
  survey_number: string | null;
  khasra_number: string | null;
  khata_number: string | null;
  address: string | null;
  pincode: string | null;
  latitude: DecimalString | null;
  longitude: DecimalString | null;
  active_geometry_id: UUID | null;
  area_value: DecimalString | null;
  area_unit: string | null;
  area_sqm_derived: DecimalString | null;
  land_use: string | null;
  road_access: string;
  road_frontage_value: DecimalString | null;
  road_frontage_unit: string | null;
  title_status: string;
  notes: string | null;
  custom_fields: Record<string, unknown>;
  created_by_id: UUID | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface PropertyOwner {
  id: UUID;
  property_id: UUID;
  owner_id: UUID;
  owner: Owner;
  ownership_type: string;
  share_percent: DecimalString | null;
  record_reference: string | null;
  source_document_id: UUID | null;
  valid_from: ISODate | null;
  valid_to: ISODate | null;
  is_current: boolean;
  ended_reason: string | null;
  verification_status: string;
  verified_by_id: UUID | null;
  verified_at: ISODateTime | null;
  supersedes_id: UUID | null;
  created_at: ISODateTime;
}

export interface OwnershipSummary {
  total_share_percent: DecimalString;
  current_owner_count: number;
  verified_owner_count: number;
  is_complete: boolean;
  warnings: string[];
}

export interface MapPin {
  property_id: UUID;
  code: string;
  name: string;
  latitude: DecimalString;
  longitude: DecimalString;
  status: string;
  deal_id: UUID | null;
  deal_stage_key: string | null;
  deal_stage_name: string | null;
  color: string;
  has_geometry: boolean;
}

export interface Deal {
  id: UUID;
  code: string;
  property_id: UUID;
  title: string;
  status: "open" | "on_hold" | "won" | "lost" | "cancelled";
  is_active: boolean;
  priority: string;
  source: string | null;
  template_version_id: UUID;
  activation_id: UUID | null;
  current_stage_id: UUID | null;
  stage_entered_at: ISODateTime | null;
  active_override_reason: string | null;
  currency: string;
  asking_price: Money | null;
  expected_price: Money | null;
  negotiated_price: Money | null;
  next_action: string | null;
  next_action_due: ISODate | null;
  next_action_assignee_id: UUID | null;
  started_at: ISODateTime;
  closed_at: ISODateTime | null;
  close_reason: string | null;
  notes: string | null;
  custom_fields: Record<string, unknown>;
  created_by_id: UUID | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface DealListItem extends Deal {
  property_name: string;
  property_code: string;
  current_stage_key: string | null;
  current_stage_name: string | null;
}

export interface ChecklistItem {
  id: UUID;
  key: string;
  label: string;
  is_required: boolean;
  is_hidden: boolean;
  status: "pending" | "done" | "not_applicable" | "bypassed";
  note: string | null;
  document_id: UUID | null;
  document_class_key: string | null;
  completed_by_id: UUID | null;
  completed_at: ISODateTime | null;
}

export interface DealStage {
  id: UUID;
  stage_definition_id: UUID;
  key: string;
  name: string;
  category: string;
  color: string | null;
  position: number;
  status: "pending" | "active" | "completed" | "bypassed";
  is_terminal: boolean;
  is_skippable: boolean;
  sla_days: number | null;
  entered_at: ISODateTime | null;
  completed_at: ISODateTime | null;
  bypass_reason: string | null;
  checklist: ChecklistItem[];
}

export interface StageTransition {
  id: UUID;
  from_stage_id: UUID | null;
  to_stage_id: UUID;
  direction: "start" | "forward" | "backward" | "skip";
  reason: string | null;
  bypassed_stage_ids: UUID[];
  bypassed_checklist_item_ids: UUID[];
  actor_id: UUID | null;
  occurred_at: ISODateTime;
}

export interface OwnershipSnapshot {
  id: UUID;
  reason: "deal_start" | "ownership_confirmed";
  owners: Record<string, unknown>[];
  summary: OwnershipSummary;
  note: string | null;
  taken_by_id: UUID | null;
  taken_at: ISODateTime;
}

export interface DueDiligenceItem {
  id: UUID;
  deal_id: UUID;
  category: "legal" | "technical" | "revenue" | "survey";
  title: string;
  status: string;
  severity: string | null;
  findings: string | null;
  assignee_id: UUID | null;
  reviewer_id: UUID | null;
  reviewed_at: ISODateTime | null;
  document_ids: UUID[];
  due_date: ISODate | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface DDSummary {
  category: string;
  status: string;
  total: number;
  clear: number;
  issues: number;
  open: number;
}

export interface NegotiationEntry {
  id: UUID;
  party: string;
  kind: string;
  amount: Money | null;
  terms: string | null;
  occurred_at: ISODateTime;
  recorded_by_id: UUID | null;
}

export interface Agreement {
  id: UUID;
  deal_id: UUID;
  kind: string;
  status: string;
  reference_number: string | null;
  amount: Money | null;
  signed_on: ISODate | null;
  registered_on: ISODate | null;
  valid_until: ISODate | null;
  document_id: UUID | null;
  key_terms: Record<string, unknown>;
  notes: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Task {
  id: UUID;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  due_date: ISODate | null;
  assignee_id: UUID | null;
  property_id: UUID | null;
  deal_id: UUID | null;
  deal_stage_id: UUID | null;
  site_visit_id: UUID | null;
  completed_at: ISODateTime | null;
  created_by_id: UUID | null;
  client_ref: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface DocumentClass {
  id: UUID;
  tenant_id: UUID | null;
  key: string;
  name: string;
  category: string;
  is_sensitive: boolean;
  default_access_policy: string;
  requires_expiry: boolean;
  applies_to: string[];
  description: string | null;
}

export interface DocumentVersion {
  id: UUID;
  version_no: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  note: string | null;
  uploaded_by_id: UUID | null;
  uploaded_at: ISODateTime;
}

export interface CrmDocument {
  id: UUID;
  class_id: UUID;
  class_key: string;
  class_name: string;
  category: string;
  is_sensitive: boolean;
  is_redacted: boolean;
  title: string | null;
  description: string | null;
  property_id: UUID | null;
  deal_id: UUID | null;
  owner_id: UUID | null;
  site_visit_id: UUID | null;
  access_policy: "standard" | "restricted" | "confidential";
  review_status: "pending_review" | "approved" | "rejected" | "needs_changes";
  reviewer_id: UUID | null;
  reviewed_at: ISODateTime | null;
  review_note: string | null;
  current_version_no: number;
  expiry_date: ISODate | null;
  renewal_due_date: ISODate | null;
  reference_number: string | null;
  issued_on: ISODate | null;
  created_by_id: UUID | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  versions: DocumentVersion[];
}

export interface DocumentCompleteness {
  received: number;
  required: number;
  label: string;
  percent: number;
  missing: CompletenessItem[];
  items: CompletenessItem[];
}

export interface CompletenessItem {
  class_key: string;
  class_name: string;
  category: string;
  status: "missing" | "received" | "approved" | "rejected" | "bypassed";
  document_ids: UUID[];
  has_expired: boolean;
}

export interface MapUpload {
  id: UUID;
  property_id: UUID;
  file_kind: "geojson" | "kml" | "pdf" | "image";
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  description: string | null;
  uploaded_by_id: UUID | null;
  uploaded_at: ISODateTime;
  processing_status: string | null;
  processing_message: string | null;
}

export interface GeometryVersion {
  id: UUID;
  property_id: UUID;
  version_no: number;
  geojson: GeoJSONPolygon;
  source: string;
  source_upload_id: UUID | null;
  source_page: number | null;
  georeference: Record<string, unknown>;
  status: "draft" | "submitted" | "approved" | "rejected" | "superseded";
  area_sqm: DecimalString | null;
  perimeter_m: DecimalString | null;
  calc_method: string | null;
  validation: { valid: boolean; errors: string[]; warnings: string[] };
  confidence: string | null;
  notes: string | null;
  created_by_id: UUID | null;
  submitted_at: ISODateTime | null;
  reviewed_by_id: UUID | null;
  reviewed_at: ISODateTime | null;
  review_note: string | null;
  created_at: ISODateTime;
  is_active: boolean;
  notice: string;
}

export interface GeoJSONPolygon {
  type: "Polygon" | "MultiPolygon";
  coordinates: number[][][] | number[][][][];
}

export interface NearbyFeature {
  id: UUID;
  kind: string;
  name: string | null;
  ref: string | null;
  distance_m: number;
  latitude: number | null;
  longitude: number | null;
  source: string;
  confidence: string;
  fetched_at: ISODateTime;
  derived: true;
}

export interface PaymentMilestone {
  id: UUID;
  deal_id: UUID;
  kind: string;
  label: string;
  position: number;
  planned_amount: Money;
  currency: string;
  due_date: ISODate | null;
  status: string;
  approval_status: string;
  approved_by_id: UUID | null;
  approved_at: ISODateTime | null;
  approval_note: string | null;
  payee_owner_id: UUID | null;
  notes: string | null;
  created_by_id: UUID | null;
  created_at: ISODateTime;
}

export interface Payment {
  id: UUID;
  deal_id: UUID;
  milestone_id: UUID | null;
  amount: Money;
  currency: string;
  paid_on: ISODate;
  mode: string;
  reference: string | null;
  payee_owner_id: UUID | null;
  receipt_document_id: UUID | null;
  status: "recorded" | "approved" | "rejected" | "reversed";
  recorded_by_id: UUID;
  approved_by_id: UUID | null;
  approved_at: ISODateTime | null;
  decision_note: string | null;
  reversal_reason: string | null;
  reversed_at: ISODateTime | null;
  notes: string | null;
  created_at: ISODateTime;
}

export interface FinancialSummary {
  currency: string;
  asking_price: Money | null;
  expected_price: Money | null;
  negotiated_price: Money | null;
  balance_basis: string | null;
  planned_total: Money;
  unplanned_amount: Money | null;
  advance_planned: Money;
  advance_paid: Money;
  paid_total: Money;
  pending_approval_total: Money;
  balance_amount: Money | null;
  overdue_milestones: number;
  next_due: { milestone_id: UUID; label: string; due_date: ISODate; planned_amount: Money } | null;
}

export interface SiteVisitAttendee {
  id: UUID;
  user_id: UUID | null;
  owner_id: UUID | null;
  name: string | null;
  contact: string | null;
  role: string;
  is_assigned: boolean;
  attended: boolean | null;
}

export interface SiteVisit {
  id: UUID;
  property_id: UUID | null;
  deal_id: UUID | null;
  title: string;
  purpose: string | null;
  scheduled_start: ISODateTime;
  scheduled_end: ISODateTime | null;
  status: "scheduled" | "in_progress" | "completed" | "cancelled" | "missed";
  outcome: string | null;
  meeting_point: string | null;
  check_in_at: ISODateTime | null;
  check_in_lat: number | null;
  check_in_lng: number | null;
  check_in_accuracy_m: number | null;
  check_out_at: ISODateTime | null;
  check_out_lat: number | null;
  check_out_lng: number | null;
  client_ref: string | null;
  created_by_id: UUID | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  attendees: SiteVisitAttendee[];
}

export interface SiteVisitNote {
  id: UUID;
  body: string;
  author_id: UUID | null;
  latitude: number | null;
  longitude: number | null;
  client_ref: string | null;
  recorded_at: ISODateTime;
  created_at: ISODateTime;
}

export interface SiteVisitMedia {
  id: UUID;
  kind: "photo" | "video" | "audio";
  filename: string;
  content_type: string;
  size_bytes: number;
  caption: string | null;
  latitude: number | null;
  longitude: number | null;
  captured_at: ISODateTime | null;
  uploaded_by_id: UUID | null;
  uploaded_at: ISODateTime;
  client_ref: string | null;
}

export interface SiteVisitDetail extends SiteVisit {
  notes: SiteVisitNote[];
  media: SiteVisitMedia[];
  conflicts: { visit_id: UUID; title: string; scheduled_start: ISODateTime }[];
}

export interface Edge {
  name: string;
  length: Measurement;
  direction?: string | null;
  notes?: string | null;
}

export interface SiteSource {
  document_id?: UUID | null;
  map_upload_id?: UUID | null;
  page_number?: number | null;
  map_label?: string | null;
  region_reference?: string | null;
  layout_reference?: string | null;
}

export interface SiteLocation {
  property_id?: UUID | null;
  project_name?: string | null;
  state_id?: UUID | null;
  district_id?: UUID | null;
  tehsil_id?: UUID | null;
  village_id?: UUID | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  description?: string | null;
}

interface SiteCommon {
  status: string;
  source: SiteSource;
  location: SiteLocation;
  notes?: string | null;
}

export interface LandPlotData extends SiteCommon {
  property_type: "land_plot";
  plot_label?: string | null;
  area?: Measurement | null;
  length?: Measurement | null;
  width?: Measurement | null;
  frontage?: Measurement | null;
  cut_dimensions: Edge[];
  edges: Edge[];
  road_access?: { road_type?: string | null; road_width?: Measurement | null; access_notes?: string | null } | null;
}

export interface ResidentialUnitData extends SiteCommon {
  property_type: "apartment" | "studio_flat";
  unit_number?: string | null;
  floor?: string | null;
  total_area?: Measurement | null;
  carpet_area?: Measurement | null;
  built_up_area?: Measurement | null;
  super_built_up_area?: Measurement | null;
  rooms?: number | null;
  bathrooms?: number | null;
}

export interface CommercialUnitData extends SiteCommon {
  property_type: "commercial_unit";
  unit_number?: string | null;
  floor?: string | null;
  total_area?: Measurement | null;
  carpet_area?: Measurement | null;
  built_up_area?: Measurement | null;
  frontage?: Measurement | null;
  access?: string | null;
  usage_type?: string | null;
}

export type SiteData = LandPlotData | ResidentialUnitData | CommercialUnitData;

export interface SiteRevision {
  id: UUID;
  site_record_id: UUID;
  revision_no: number;
  change_type: "create" | "update";
  data: SiteData;
  derived: Record<string, unknown>;
  match_decision: { decision: "new" | "update"; considered_candidates: UUID[] };
  change_note: string | null;
  status: "pending" | "approved" | "rejected" | "superseded";
  submitted_by_id: UUID;
  submitted_at: ISODateTime;
  reviewed_by_id: UUID | null;
  reviewed_at: ISODateTime | null;
  review_note: string | null;
}

export interface SiteRecord {
  id: UUID;
  site_code: string;
  property_type: string;
  approval_state: "pending" | "approved" | "rejected";
  active_revision_id: UUID | null;
  pending_revision_id: UUID | null;
  status: string | null;
  property_id: UUID | null;
  source_document_id: UUID | null;
  source_map_upload_id: UUID | null;
  plot_label: string | null;
  unit_number: string | null;
  project_name: string | null;
  location_text: string | null;
  latitude: number | null;
  longitude: number | null;
  area_value: DecimalString | null;
  area_unit: string | null;
  area_sqm_derived: DecimalString | null;
  rooms: number | null;
  bathrooms: number | null;
  floor: string | null;
  usage_type: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface SiteDetail extends SiteRecord {
  active_revision: SiteRevision | null;
  pending_revision: SiteRevision | null;
  history: SiteRevision[];
}

export interface MatchCandidate {
  site_id: UUID;
  site_code: string;
  score: number;
  reasons: string[];
  approval_state: string;
}

export interface ScoreFactor {
  key: string;
  label: string;
  weight: number;
  score: number | null;
  fact: string | null;
  explanation: string;
  missing: boolean;
}

export interface DealScore {
  id: UUID | null;
  deal_id: UUID;
  model_id: UUID;
  total: number;
  coverage: number;
  breakdown: ScoreFactor[];
  computed_at: ISODateTime | null;
}

export interface Notification {
  id: UUID;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  entity_type: string | null;
  entity_id: string | null;
  read_at: ISODateTime | null;
  created_at: ISODateTime;
}

export interface WorkflowStageDef {
  id: UUID;
  key: string;
  name: string;
  description: string | null;
  position: number;
  category: string;
  color: string | null;
  is_terminal: boolean;
  is_skippable: boolean;
  sla_days: number | null;
  checklist: { id: UUID; key: string; label: string; is_required: boolean; document_class_key: string | null }[];
}

export interface WorkflowVersion {
  id: UUID;
  template_id: UUID;
  version: number;
  status: "draft" | "published" | "retired";
  notes: string | null;
  published_at: ISODateTime | null;
  stages: WorkflowStageDef[];
}

export interface WorkflowTemplate {
  id: UUID;
  key: string;
  name: string;
  description: string | null;
  land_types: string[];
  is_archived: boolean;
  versions: { id: UUID; version: number; status: string; published_at: ISODateTime | null }[];
}

export interface WorkflowActivation {
  id: UUID;
  template_version_id: UUID;
  is_active: boolean;
  is_default: boolean;
  land_types: string[];
  config: { stage_labels?: Record<string, string>; sla_days?: Record<string, number>; hidden_optional_items?: string[] };
  created_at: ISODateTime;
  template_version: WorkflowVersion;
}

export interface AuditEvent {
  id: UUID;
  actor_id: UUID | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  changes: Record<string, unknown>;
  metadata_: Record<string, unknown>;
  request_id: string | null;
  occurred_at: ISODateTime;
}
