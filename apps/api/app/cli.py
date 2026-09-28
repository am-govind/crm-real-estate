"""Operational commands.

    python -m app.cli init-db            # local/SQLite only: create tables from models
    python -m app.cli seed               # system document classes + default workflow template
    python -m app.cli create-tenant --name "Acme Land" --slug acme --admin-email admin@acme.test
    python -m app.cli system-admin --email you@example.com
"""

import argparse
import sys

from sqlalchemy import select

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.modules.documents.catalog import ensure_system_classes
from app.modules.identity.models import TenantInvitation, User
from app.modules.identity.service import create_tenant
from app.modules.workflows.models import TenantWorkflowActivation
from app.modules.workflows.service import ensure_default_template


def init_db() -> None:
    if not get_settings().is_sqlite:
        sys.exit("init-db is for local SQLite only; use Alembic migrations for PostgreSQL")
    Base.metadata.create_all(engine)
    print("Tables created")


def seed() -> None:
    with SessionLocal() as s:
        ensure_system_classes(s)
        version = ensure_default_template(s)
        s.commit()
        print(f"Seeded document classes and workflow version {version.id}")


def create_tenant_cmd(name: str, slug: str, admin_email: str | None) -> None:
    with SessionLocal() as s:
        version = ensure_default_template(s)
        tenant = create_tenant(s, None, name=name, slug=slug)
        s.add(TenantWorkflowActivation(tenant_id=tenant.id, template_version_id=version.id, is_default=True))
        if admin_email:
            s.add(TenantInvitation(tenant_id=tenant.id, email=admin_email.lower(), role_keys=["tenant_admin"]))
        s.commit()
        print(f"Tenant {tenant.slug} created: {tenant.id}")


def system_admin(email: str) -> None:
    with SessionLocal() as s:
        user = s.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            sys.exit("User not found; sign in once first so the account is provisioned")
        user.is_system_admin = True
        s.commit()
        print(f"{email} is now a system administrator")


def main() -> None:
    parser = argparse.ArgumentParser(prog="landcrm")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    sub.add_parser("seed")
    t = sub.add_parser("create-tenant")
    t.add_argument("--name", required=True)
    t.add_argument("--slug", required=True)
    t.add_argument("--admin-email")
    a = sub.add_parser("system-admin")
    a.add_argument("--email", required=True)
    args = parser.parse_args()

    if args.cmd == "init-db":
        init_db()
    elif args.cmd == "seed":
        seed()
    elif args.cmd == "create-tenant":
        create_tenant_cmd(args.name, args.slug, args.admin_email)
    elif args.cmd == "system-admin":
        system_admin(args.email)


if __name__ == "__main__":
    main()
