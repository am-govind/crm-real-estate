import uuid

from sqlalchemy import ForeignKey, Integer, String, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base

SEQUENCE_FORMATS = {
    "site": ("SITE-", 6),
    "property": ("PROP-", 6),
    "deal": ("DEAL-", 6),
    "owner": ("OWN-", 6),
}


class TenantSequence(Base):
    __tablename__ = "tenant_sequences"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, default=1)


def format_code(name: str, value: int) -> str:
    prefix, width = SEQUENCE_FORMATS[name]
    return f"{prefix}{value:0{width}d}"


def peek(session: Session, tenant_id: uuid.UUID, name: str) -> str:
    seq = session.get(TenantSequence, (tenant_id, name))
    return format_code(name, seq.next_value if seq else 1)


def take(session: Session, tenant_id: uuid.UUID, name: str) -> str:
    """Allocates the next code. Uses a row lock on PostgreSQL to stay unique under concurrency."""
    seq = session.scalar(
        select(TenantSequence)
        .where(TenantSequence.tenant_id == tenant_id, TenantSequence.name == name)
        .with_for_update()
    )
    if seq is None:
        seq = TenantSequence(tenant_id=tenant_id, name=name, next_value=1)
        session.add(seq)
        session.flush()
    value = seq.next_value
    seq.next_value = value + 1
    session.flush()
    return format_code(name, value)
