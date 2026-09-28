from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.jobs import BackgroundJob, job_handler
from app.modules.deals.models import DealAssignment
from app.modules.notifications.service import notify
from app.modules.payments.models import PaymentMilestone
from app.modules.payments.service import refresh_milestone_status


@job_handler("payments.overdue_check")
def overdue_check(session: Session, job: BackgroundJob) -> dict:
    rows = session.scalars(
        select(PaymentMilestone).where(
            PaymentMilestone.status.in_(("planned", "partially_paid")),
            PaymentMilestone.due_date.is_not(None),
            PaymentMilestone.due_date < date.today(),
        )
    ).all()
    flagged = 0
    for m in rows:
        refresh_milestone_status(session, m)
        if m.status != "overdue":
            continue
        flagged += 1
        users = set(session.scalars(select(DealAssignment.user_id).where(DealAssignment.deal_id == m.deal_id)))
        users.add(m.created_by_id)
        notify(
            session, tenant_id=m.tenant_id, user_ids=users, kind="payment.overdue",
            title=f"Payment milestone overdue: {m.label}", body=f"Due {m.due_date.isoformat()}",
            link=f"/deals/{m.deal_id}?tab=finance", entity_type="payment_milestone", entity_id=str(m.id),
            dedupe_key=f"milestone-overdue:{m.id}:{m.due_date.isoformat()}", push=True,
        )
    session.commit()
    return {"checked": len(rows), "overdue": flagged}
