"""Permission catalogue and default tenant roles. Kept in sync with packages/domain/src/permissions.ts."""

from enum import StrEnum


class P(StrEnum):
    TENANT_MANAGE = "tenant.manage"
    USER_MANAGE = "user.manage"
    ROLE_MANAGE = "role.manage"
    AUDIT_READ = "audit.read"

    OWNER_READ = "owner.read"
    OWNER_WRITE = "owner.write"
    OWNER_VERIFY = "owner.verify"

    PROPERTY_READ = "property.read"
    PROPERTY_READ_ALL = "property.read_all"
    PROPERTY_WRITE = "property.write"
    PROPERTY_ASSIGN = "property.assign"

    DEAL_READ = "deal.read"
    DEAL_READ_ALL = "deal.read_all"
    DEAL_WRITE = "deal.write"
    DEAL_ASSIGN = "deal.assign"
    DEAL_STAGE_MOVE = "deal.stage.move"
    DEAL_STAGE_SKIP = "deal.stage.skip"
    DEAL_CHECKLIST_BYPASS = "deal.checklist.bypass"
    DEAL_ACTIVE_OVERRIDE = "deal.active_override"

    DUE_DILIGENCE_REVIEW = "due_diligence.review"

    WORKFLOW_CONFIGURE = "workflow.configure"

    TASK_READ = "task.read"
    TASK_WRITE = "task.write"

    DOCUMENT_READ = "document.read"
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_REVIEW = "document.review"
    DOCUMENT_SENSITIVE_READ = "document.sensitive.read"
    DOCUMENT_SENSITIVE_UPLOAD = "document.sensitive.upload"
    DOCUMENT_GRANT = "document.grant"
    DOCUMENT_CONFIGURE = "document.configure"

    GEOMETRY_DRAFT = "geometry.draft"
    GEOMETRY_APPROVE = "geometry.approve"

    PAYMENT_READ = "payment.read"
    PAYMENT_WRITE = "payment.write"
    PAYMENT_APPROVE = "payment.approve"

    SITE_VISIT_READ = "site_visit.read"
    SITE_VISIT_WRITE = "site_visit.write"

    INVENTORY_READ = "inventory.read"
    INVENTORY_WRITE = "inventory.write"
    INVENTORY_APPROVE = "inventory.approve"

    SCORING_CONFIGURE = "scoring.configure"
    REPORT_READ = "report.read"
    GEOGRAPHY_MANAGE = "geography.manage"


ALL_PERMISSIONS: frozenset[str] = frozenset(p.value for p in P)

_READ_CORE = {
    P.OWNER_READ, P.PROPERTY_READ, P.DEAL_READ, P.TASK_READ, P.DOCUMENT_READ,
    P.PAYMENT_READ, P.SITE_VISIT_READ, P.INVENTORY_READ, P.REPORT_READ,
}

DEFAULT_ROLES: dict[str, dict] = {
    "tenant_admin": {"name": "Tenant administrator", "permissions": set(ALL_PERMISSIONS)},
    "management": {
        "name": "Management",
        "permissions": _READ_CORE | {
            P.PROPERTY_READ_ALL, P.DEAL_READ_ALL, P.AUDIT_READ, P.DEAL_STAGE_SKIP, P.DEAL_ACTIVE_OVERRIDE,
            P.DEAL_CHECKLIST_BYPASS, P.DEAL_STAGE_MOVE, P.DEAL_ASSIGN, P.PROPERTY_ASSIGN, P.PAYMENT_APPROVE,
            P.INVENTORY_APPROVE, P.DOCUMENT_SENSITIVE_READ,
        },
    },
    "acquisition": {
        "name": "Acquisition",
        "permissions": _READ_CORE | {
            P.OWNER_WRITE, P.PROPERTY_WRITE, P.DEAL_WRITE, P.DEAL_STAGE_MOVE, P.TASK_WRITE,
            P.DOCUMENT_UPLOAD, P.DOCUMENT_SENSITIVE_UPLOAD, P.GEOMETRY_DRAFT, P.SITE_VISIT_WRITE,
            P.INVENTORY_WRITE,
        },
    },
    "legal_reviewer": {
        "name": "Legal reviewer",
        "permissions": _READ_CORE | {
            P.OWNER_VERIFY, P.DUE_DILIGENCE_REVIEW, P.DOCUMENT_REVIEW, P.DOCUMENT_SENSITIVE_READ,
            P.GEOMETRY_APPROVE, P.TASK_WRITE,
        },
    },
    "technical_reviewer": {
        "name": "Technical reviewer",
        "permissions": _READ_CORE | {
            P.DUE_DILIGENCE_REVIEW, P.DOCUMENT_REVIEW, P.GEOMETRY_DRAFT, P.GEOMETRY_APPROVE, P.TASK_WRITE,
        },
    },
    "finance": {
        "name": "Finance",
        "permissions": _READ_CORE | {
            P.PAYMENT_WRITE, P.PAYMENT_APPROVE, P.DOCUMENT_UPLOAD, P.DOCUMENT_SENSITIVE_READ,
            P.DOCUMENT_SENSITIVE_UPLOAD,
        },
    },
}
