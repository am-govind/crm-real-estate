"""System document classes seeded for every installation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.documents.models import DocumentClass

# key, name, category, is_sensitive, default_access_policy, requires_expiry, applies_to
SYSTEM_CLASSES: list[tuple] = [
    ("sale_deed", "Sale deed", "ownership", False, "standard", False, ["property", "deal"]),
    ("previous_sale_deed", "Previous sale deed", "ownership", False, "standard", False, ["property"]),
    ("title_document", "Title document", "ownership", False, "standard", False, ["property"]),
    ("mutation", "Mutation record", "ownership", False, "standard", False, ["property"]),
    ("revenue_record", "Revenue record", "property", False, "standard", False, ["property"]),
    ("khasra", "Khasra", "property", False, "standard", False, ["property"]),
    ("khatauni", "Khatauni / record of rights", "ownership", False, "standard", False, ["property"]),
    ("encumbrance", "Encumbrance certificate", "property", False, "standard", True, ["property", "deal"]),
    ("property_tax", "Property tax record", "property", False, "standard", False, ["property"]),
    ("legal_heir", "Legal-heir certificate", "ownership", False, "restricted", False, ["property", "owner"]),
    ("site_plan", "Site plan", "property", False, "standard", False, ["property"]),
    ("survey_report", "Survey report", "property", False, "standard", False, ["property", "deal"]),
    ("demarcation", "Demarcation report", "property", False, "standard", False, ["property", "deal"]),
    ("land_use", "Land-use certificate", "property", False, "standard", False, ["property"]),
    ("conversion_order", "Conversion order", "property", False, "standard", False, ["property"]),
    ("noc", "No-objection certificate", "property", False, "standard", True, ["property", "deal"]),
    ("legal_opinion", "Legal opinion", "internal", True, "restricted", False, ["deal"]),
    ("valuation_report", "Valuation report", "internal", True, "restricted", False, ["deal"]),
    ("loi_mou", "LOI / MOU", "transaction", False, "standard", False, ["deal"]),
    ("agreement_to_sell", "Agreement to sell", "transaction", False, "standard", False, ["deal"]),
    ("registration", "Registration document", "transaction", False, "standard", False, ["deal"]),
    ("payment_receipt", "Payment receipt", "financial", True, "restricted", False, ["deal"]),
    ("owner_identity", "Owner identity document", "identity", True, "restricted", False, ["owner", "deal"]),
    ("bank_document", "Bank document", "financial", True, "confidential", False, ["owner", "deal"]),
    ("financial_document", "Financial document", "financial", True, "restricted", False, ["deal"]),
    ("internal_confidential", "Confidential internal document", "internal", True, "confidential", False, ["property", "deal"]),
    ("site_map", "Site / layout map", "property", False, "standard", False, ["property"]),
    ("site_photo", "Site photo", "property", False, "standard", False, ["property", "deal"]),
    ("other", "Other", "property", False, "standard", False, ["property", "deal", "owner"]),
]


def ensure_system_classes(session: Session) -> None:
    existing = {c.key: c for c in session.scalars(select(DocumentClass).where(DocumentClass.tenant_id.is_(None)))}
    for key, name, category, sensitive, policy, expiry, applies in SYSTEM_CLASSES:
        if key in existing:
            continue
        session.add(
            DocumentClass(
                tenant_id=None, key=key, name=name, category=category, is_sensitive=sensitive,
                default_access_policy=policy, requires_expiry=expiry, applies_to=applies,
            )
        )
    session.flush()
