import uuid
from dataclasses import dataclass, field

from app.core.errors import Forbidden


@dataclass(frozen=True)
class RequestContext:
    """Resolved identity for the current request. Roles/permissions always come from the backend."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID | None
    email: str | None = None
    is_system_admin: bool = False
    permissions: frozenset[str] = field(default_factory=frozenset)
    role_keys: frozenset[str] = field(default_factory=frozenset)
    request_id: str | None = None
    ip_address: str | None = None
    auth_time: int | None = None

    def has(self, permission: str) -> bool:
        return self.is_system_admin or permission in self.permissions

    def require(self, *permissions: str) -> None:
        missing = [p for p in permissions if not self.has(p)]
        if missing:
            raise Forbidden("Missing permission", details={"missing": missing})

    def require_tenant(self) -> uuid.UUID:
        if self.tenant_id is None:
            raise Forbidden("A tenant must be selected for this operation")
        return self.tenant_id
