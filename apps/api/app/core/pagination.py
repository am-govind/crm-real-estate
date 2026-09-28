from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class PageParams:
    def __init__(self, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        self.limit = limit
        self.offset = offset


def paginate(session: Session, stmt: Select, params: PageParams) -> tuple[list, int]:
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.scalars(stmt.limit(params.limit).offset(params.offset)).all()
    return list(rows), total
