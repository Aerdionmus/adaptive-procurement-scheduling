from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NotificationIntentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    decision_id: int
    booking_id: int
    centre_id: int
    farmer_id: int
    notification_type: str
    channel: str
    status: str
    payload: dict[str, Any]
    created_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None
    processing_started_at: datetime | None
    failure_reason: str | None
    provider_reference: str | None


class NotificationDeliveryResponse(BaseModel):
    intent_id: int
    notification_type: str
    channel: str
    status: str
    success: bool
    reference_id: str | None
    failure_reason: str | None
    already_processed: bool = False
