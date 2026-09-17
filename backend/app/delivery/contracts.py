from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.models import NotificationIntentChannel, NotificationIntentType


@dataclass(frozen=True)
class DeliveryRequest:
    intent_id: int
    channel: NotificationIntentChannel
    notification_type: NotificationIntentType
    payload: dict[str, Any]


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    reference_id: str | None = None
    failure_reason: str | None = None


class DeliveryAdapter(Protocol):
    def deliver(self, request: DeliveryRequest) -> DeliveryResult:
        ...
