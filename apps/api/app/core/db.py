import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Uuid, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, declared_attr, mapped_column, sessionmaker

from app.core.config import get_settings

JSONType = JSON().with_variant(JSONB(), "postgresql")
MoneyType = Numeric(18, 2, asdecimal=True)
MeasureType = Numeric(20, 6, asdecimal=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {
        dict: JSONType,
        list: JSONType,
        Decimal: MoneyType,
        datetime: DateTime(timezone=True),
    }


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class TenantScopedMixin:
    """Every tenant-owned record carries a tenant boundary."""

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(Uuid, ForeignKey("tenants.id"), index=True, nullable=False)


class ActorMixin:
    @declared_attr
    def created_by_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(Uuid, ForeignKey("users.id"), nullable=True)


def uuid_fk(target: str, *, nullable: bool = True, index: bool = True, ondelete: str | None = None):
    return mapped_column(Uuid, ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index)


def short_str(length: int = 255):
    return String(length)


_settings = get_settings()
_connect_args = {"check_same_thread": False} if _settings.is_sqlite else {}
engine = create_engine(_settings.database_url, connect_args=_connect_args, pool_pre_ping=True, future=True)

if _settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_fk_on(dbapi_conn, _):  # pragma: no cover - driver hook
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def apply_tenant_guc(session: Session, tenant_id: uuid.UUID | None) -> None:
    """Sets the PostgreSQL row-level-security tenant variable for the current transaction."""
    if session.bind is None or session.bind.dialect.name != "postgresql" or tenant_id is None:
        return
    from sqlalchemy import text

    session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)})
