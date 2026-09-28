-- PostgreSQL row-level security for tenant isolation (Milestone 8).
-- Apply after the schema migrations. The API sets `app.tenant_id` per transaction
-- (see app.core.db.apply_tenant_guc). The API role must NOT be a superuser or table
-- owner, otherwise RLS is bypassed. The worker processes jobs across tenants and should
-- connect with a separate role that has BYPASSRLS.
--
-- Identity tables (tenant_memberships, roles, role_permissions, tenant_invitations) are
-- read before a tenant is resolved and are protected by service-layer checks instead.

DO $$
DECLARE
  t text;
  tenant_tables text[] := ARRAY[
    'owners', 'properties', 'property_owners', 'deals', 'due_diligence_items', 'negotiation_entries',
    'agreements', 'tasks', 'documents', 'required_document_rules', 'map_uploads', 'map_processing_runs',
    'geometry_versions', 'nearby_features', 'payment_milestones', 'payments', 'site_visits',
    'site_visit_media', 'site_records', 'site_record_revisions', 'scoring_models', 'deal_scores',
    'notifications', 'tenant_sequences', 'tenant_workflow_activations'
  ];
BEGIN
  FOREACH t IN ARRAY tenant_tables LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.tenant_id'', true)::uuid) '
      'WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true)::uuid)', t);
  END LOOP;
END $$;

-- Shared catalogue tables (tenant_id NULL = system row) allow reading system rows.
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['document_classes', 'geo_units', 'audit_events', 'background_jobs'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_or_system ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_or_system ON %I USING (tenant_id IS NULL OR tenant_id = current_setting(''app.tenant_id'', true)::uuid)', t);
  END LOOP;
END $$;

-- Audit log is append-only for the application role.
REVOKE UPDATE, DELETE ON audit_events FROM PUBLIC;
