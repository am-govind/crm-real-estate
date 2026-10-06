"""Create the local Land CRM administrator, demo tenant, and sample records."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import app.models  # noqa: F401
from sqlalchemy import select

from app.core.context import RequestContext
from app.core.db import SessionLocal
from app.modules.deals.models import Deal
from app.modules.geography.models import GeoUnit
from app.modules.identity.models import MembershipRole, Role, Tenant, TenantMembership, User
from app.modules.identity.service import create_tenant
from app.modules.owners.models import Owner, OwnerContact
from app.modules.payments.models import PaymentMilestone
from app.modules.properties.models import Property, PropertyOwner
from app.modules.site_visits.models import SiteVisit
from app.modules.tasks.models import Task
from app.modules.workflows.models import TenantWorkflowActivation
from app.modules.workflows.service import ensure_default_template

ADMIN_EMAIL = "developer@example.com"
ISSUER = "urn:landcrm:dev"
TENANT_SLUG = "demo-land"


def first_or_create(session, model, defaults=None, **lookup):
    row = session.scalar(select(model).filter_by(**lookup))
    if row is None:
        values = {**(defaults or {}), **lookup}
        row = model(**values)
        session.add(row)
        session.flush()
    return row


def main() -> None:
    with SessionLocal() as session:
        admin = first_or_create(
            session,
            User,
            defaults={"display_name": "Global Product Administrator", "is_active": True, "is_system_admin": True},
            oidc_issuer=ISSUER,
            oidc_subject=ADMIN_EMAIL,
        )
        admin.email = ADMIN_EMAIL
        admin.is_system_admin = True

        tenant = session.scalar(select(Tenant).where(Tenant.slug == TENANT_SLUG))
        if tenant is None:
            tenant = create_tenant(
                session,
                None,
                name="Demo Land Company",
                slug=TENANT_SLUG,
                country_code="IN",
                default_currency="INR",
            )

        roles = {r.key: r for r in session.scalars(select(Role).where(Role.tenant_id == tenant.id))}
        membership = session.scalar(
            select(TenantMembership).where(TenantMembership.tenant_id == tenant.id, TenantMembership.user_id == admin.id)
        )
        if membership is None:
            membership = TenantMembership(tenant_id=tenant.id, user_id=admin.id, title="Product Administrator")
            session.add(membership)
            session.flush()
        tenant_admin = roles.get("tenant_admin")
        if tenant_admin and not any(mr.role_id == tenant_admin.id for mr in membership.roles):
            membership.roles.append(MembershipRole(role_id=tenant_admin.id))

        template_version = ensure_default_template(session)
        activation = session.scalar(
            select(TenantWorkflowActivation).where(
                TenantWorkflowActivation.tenant_id == tenant.id,
                TenantWorkflowActivation.template_version_id == template_version.id,
            )
        )
        if activation is None:
            activation = TenantWorkflowActivation(
                tenant_id=tenant.id,
                template_version_id=template_version.id,
                is_active=True,
                is_default=True,
                land_types=[],
                config={},
                activated_by_id=admin.id,
            )
            session.add(activation)
            session.flush()

        state = first_or_create(session, GeoUnit, level="state", name="Madhya Pradesh", code="MP", tenant_id=None, parent_id=None)
        district = first_or_create(session, GeoUnit, level="district", name="Bhopal", code="BHOPAL", tenant_id=None, parent_id=state.id)
        tehsil = first_or_create(session, GeoUnit, level="tehsil", name="Huzur", code="HUZUR", tenant_id=None, parent_id=district.id)
        village = first_or_create(session, GeoUnit, level="village", name="Kolar", code="KOLAR", tenant_id=None, parent_id=tehsil.id)

        owner = first_or_create(
            session,
            Owner,
            defaults={
                "tenant_id": tenant.id,
                "owner_type": "individual",
                "readiness": "ready_to_sell",
                "verification_status": "verified",
                "notes": "Demo owner for local development.",
                "created_by_id": admin.id,
            },
            tenant_id=tenant.id,
            code="OWN-000001",
            full_name="Rajesh Sharma",
        )
        first_or_create(session, OwnerContact, kind="phone", value="+91 98765 43210", label="Primary", is_primary=True, owner_id=owner.id)
        first_or_create(session, OwnerContact, kind="email", value="rajesh@example.com", label="Primary", is_primary=True, owner_id=owner.id)

        prop = first_or_create(
            session,
            Property,
            defaults={
                "tenant_id": tenant.id,
                "created_by_id": admin.id,
                "land_type": "commercial",
                "status": "in_pipeline",
                "state_id": state.id,
                "district_id": district.id,
                "tehsil_id": tehsil.id,
                "village_id": village.id,
                "survey_number": "42/3",
                "khasra_number": "118/2",
                "address": "Kolar Road, Bhopal, Madhya Pradesh",
                "pincode": "462042",
                "latitude": Decimal("23.189500"),
                "longitude": Decimal("77.434200"),
                "area_value": Decimal("50"),
                "area_unit": "acre",
                "land_use": "mixed residential and commercial",
                "road_access": "highway_frontage",
                "road_frontage_value": Decimal("180"),
                "road_frontage_unit": "metre",
                "title_status": "under_review",
                "notes": "Demo parcel for testing the acquisition control center.",
            },
            tenant_id=tenant.id,
            code="PROP-000001",
            name="Kolar Road Development Parcel",
        )
        first_or_create(
            session,
            PropertyOwner,
            defaults={
                "tenant_id": tenant.id,
                "share_percent": Decimal("100"),
                "ownership_type": "sole",
                "verification_status": "verified",
                "verified_by_id": admin.id,
                "is_current": True,
                "created_by_id": admin.id,
            },
            property_id=prop.id,
            owner_id=owner.id,
        )

        deal = first_or_create(
            session,
            Deal,
            defaults={
                "tenant_id": tenant.id,
                "created_by_id": admin.id,
                "title": "Acquire Kolar Road Parcel",
                "status": "open",
                "is_active": True,
                "priority": "high",
                "source": "Demo lead",
                "template_version_id": template_version.id,
                "activation_id": activation.id,
                "currency": "INR",
                "asking_price": Decimal("120000000"),
                "expected_price": Decimal("105000000"),
                "next_action": "Collect updated survey report",
                "next_action_due": date.today() + timedelta(days=7),
                "next_action_assignee_id": admin.id,
                "notes": "Demo acquisition deal covering the complete land workflow.",
            },
            tenant_id=tenant.id,
            code="DEAL-000001",
            property_id=prop.id,
        )
        first_or_create(
            session,
            Task,
            defaults={
                "tenant_id": tenant.id,
                "created_by_id": admin.id,
                "title": "Obtain updated survey report",
                "description": "Upload the latest demarcation and survey report.",
                "priority": "high",
                "due_date": date.today() + timedelta(days=7),
                "assignee_id": admin.id,
                "property_id": prop.id,
                "deal_id": deal.id,
            },
            tenant_id=tenant.id,
            client_ref="demo-task-survey",
        )
        first_or_create(
            session,
            SiteVisit,
            defaults={
                "tenant_id": tenant.id,
                "created_by_id": admin.id,
                "property_id": prop.id,
                "deal_id": deal.id,
                "title": "Initial Kolar Road site visit",
                "purpose": "Confirm access, frontage, and visible boundaries.",
                "scheduled_start": datetime.now(timezone.utc) + timedelta(days=2),
                "scheduled_end": datetime.now(timezone.utc) + timedelta(days=2, hours=2),
                "status": "scheduled",
                "meeting_point": "Kolar Road highway entrance",
            },
            tenant_id=tenant.id,
            client_ref="demo-visit-kolar-001",
        )
        first_or_create(
            session,
            PaymentMilestone,
            defaults={
                "tenant_id": tenant.id,
                "created_by_id": admin.id,
                "deal_id": deal.id,
                "kind": "advance",
                "label": "Demonstration advance",
                "position": 1,
                "planned_amount": Decimal("10000000"),
                "currency": "INR",
                "due_date": date.today() + timedelta(days=30),
                "status": "planned",
                "approval_status": "pending_approval",
                "payee_owner_id": owner.id,
                "notes": "Demo payment milestone; no real payment recorded.",
            },
            tenant_id=tenant.id,
            deal_id=deal.id,
            label="Demonstration advance",
        )
        session.commit()
        print(f"Admin: {ADMIN_EMAIL}")
        print(f"Tenant: {tenant.name} ({tenant.slug})")
        print(f"Property: {prop.code} — {prop.name}")
        print(f"Deal: {deal.code} — {deal.title}")


if __name__ == "__main__":
    main()

# Local Git-change test comment; this has no runtime effect.
# Local Git-change test comment; this has no runtime effect.