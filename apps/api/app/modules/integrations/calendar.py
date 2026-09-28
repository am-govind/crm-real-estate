"""Calendar integration boundary. V1 schedules internally; Google Calendar / Outlook adapters plug in here."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class CalendarEvent:
    internal_id: str
    title: str
    starts_at: datetime
    ends_at: datetime | None
    location: str | None
    attendee_emails: list[str]
    description: str | None = None


class CalendarProvider(Protocol):
    name: str

    def upsert(self, event: CalendarEvent, *, external_ref: str | None) -> str | None:
        """Creates/updates the event and returns the provider's external reference."""

    def cancel(self, *, external_ref: str) -> None: ...


class InternalCalendar:
    name = "internal"

    def upsert(self, event: CalendarEvent, *, external_ref: str | None) -> str | None:
        return None

    def cancel(self, *, external_ref: str) -> None:
        return None


calendar_provider: CalendarProvider = InternalCalendar()
