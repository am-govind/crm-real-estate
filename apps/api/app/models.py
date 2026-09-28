"""Imports every module's models so SQLAlchemy metadata (and Alembic autogenerate) sees all tables."""

from app.core import jobs as _jobs  # noqa: F401
from app.core import sequences as _sequences  # noqa: F401
from app.core.db import Base
from app.modules.audit import models as _audit  # noqa: F401
from app.modules.deals import models as _deals  # noqa: F401
from app.modules.documents import models as _documents  # noqa: F401
from app.modules.geography import models as _geography  # noqa: F401
from app.modules.identity import models as _identity  # noqa: F401
from app.modules.inventory import models as _inventory  # noqa: F401
from app.modules.maps import models as _maps  # noqa: F401
from app.modules.notifications import models as _notifications  # noqa: F401
from app.modules.owners import models as _owners  # noqa: F401
from app.modules.payments import models as _payments  # noqa: F401
from app.modules.properties import models as _properties  # noqa: F401
from app.modules.scoring import models as _scoring  # noqa: F401
from app.modules.site_visits import models as _site_visits  # noqa: F401
from app.modules.tasks import models as _tasks  # noqa: F401
from app.modules.workflows import models as _workflows  # noqa: F401

metadata = Base.metadata
