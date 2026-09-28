"""Delivery channel adapters. In-app notifications are always stored; other channels are optional."""

import logging
from typing import Protocol

import httpx

log = logging.getLogger("landcrm.notifications")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class PushChannel(Protocol):
    def send(self, tokens: list[str], *, title: str, body: str | None, data: dict) -> None: ...


class EmailChannel(Protocol):
    def send(self, to: str, *, subject: str, body: str) -> None: ...


class ExpoPushChannel:
    def send(self, tokens: list[str], *, title: str, body: str | None, data: dict) -> None:
        if not tokens:
            return
        messages = [{"to": t, "title": title, "body": body or "", "data": data, "sound": "default"} for t in tokens]
        for i in range(0, len(messages), 100):
            try:
                httpx.post(EXPO_PUSH_URL, json=messages[i : i + 100], timeout=10)
            except httpx.HTTPError:
                log.exception("Expo push delivery failed")


class LogEmailChannel:
    """Placeholder email adapter; swap for SES/SendGrid/SMTP without touching callers."""

    def send(self, to: str, *, subject: str, body: str) -> None:
        log.info("email to=%s subject=%s", to, subject)


push_channel: PushChannel = ExpoPushChannel()
email_channel: EmailChannel = LogEmailChannel()
