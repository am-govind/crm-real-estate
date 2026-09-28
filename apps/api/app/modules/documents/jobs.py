from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.jobs import BackgroundJob, job_handler
from app.modules.deals.models import DealAssignment
from app.modules.documents.models import Document
from app.modules.notifications.service import notify
from app.modules.properties.models import PropertyAssignment


@job_handler("documents.expiry_reminders")
def send_expiry_reminders(session: Session, job: BackgroundJob) -> dict:
    """Notifies uploaders and assignees about documents expiring soon or already expired."""
    horizon = date.today() + timedelta(days=get_settings().document_expiry_reminder_days)
    docs = session.scalars(
        select(Document).where(
            Document.is_archived.is_(False),
            Document.expiry_date.is_not(None),
            Document.expiry_date <= horizon,
        )
    ).all()
    sent = 0
    for doc in docs:
        recipients = {doc.created_by_id, doc.reviewer_id}
        if doc.deal_id:
            recipients.update(session.scalars(select(DealAssignment.user_id).where(DealAssignment.deal_id == doc.deal_id)))
        elif doc.property_id:
            recipients.update(session.scalars(select(PropertyAssignment.user_id).where(PropertyAssignment.property_id == doc.property_id)))
        expired = doc.expiry_date < date.today()
        bucket = "expired" if expired else "expiring"
        created = notify(
            session,
            tenant_id=doc.tenant_id,
            user_ids=recipients,
            kind=f"document.{bucket}",
            title=f"{doc.title} {'has expired' if expired else 'expires on ' + doc.expiry_date.isoformat()}",
            body="Renew or replace this document to keep the record complete.",
            link=f"/documents/{doc.id}",
            entity_type="document",
            entity_id=str(doc.id),
            dedupe_key=f"doc-expiry:{doc.id}:{doc.expiry_date.isoformat()}:{bucket}",
            push=True,
        )
        sent += len(created)
    session.commit()
    return {"documents": len(docs), "notifications": sent}
