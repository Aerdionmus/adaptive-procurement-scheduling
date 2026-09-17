from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class NotificationIntentType(str, enum.Enum):
    FARMER_SLOT_AT_RISK = "FARMER_SLOT_AT_RISK"
    FARMER_NEW_SLOT_PROPOSED = "FARMER_NEW_SLOT_PROPOSED"
    FARMER_ALTERNATE_CENTRE_PROPOSED = "FARMER_ALTERNATE_CENTRE_PROPOSED"


class NotificationIntentChannel(str, enum.Enum):
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"
    IVR = "IVR"
    IN_APP = "IN_APP"


class NotificationIntentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class NotificationIntent(Base):
    __tablename__ = "notification_intents"
    __table_args__ = (
        UniqueConstraint(
            "decision_id",
            "notification_type",
            "channel",
            name="uq_notification_intent_decision_type_channel",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("scheduling_decisions.id"), nullable=False, index=True
    )
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id"), nullable=False, index=True
    )
    centre_id: Mapped[int] = mapped_column(
        ForeignKey("procurement_centres.id"), nullable=False, index=True
    )
    farmer_id: Mapped[int] = mapped_column(
        ForeignKey("farmers.id"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationIntentType] = mapped_column(
        Enum(NotificationIntentType, name="notification_intent_type"),
        nullable=False,
    )
    channel: Mapped[NotificationIntentChannel] = mapped_column(
        Enum(NotificationIntentChannel, name="notification_intent_channel"),
        nullable=False,
    )
    status: Mapped[NotificationIntentStatus] = mapped_column(
        Enum(NotificationIntentStatus, name="notification_intent_status"),
        nullable=False,
        default=NotificationIntentStatus.PENDING,
        server_default=NotificationIntentStatus.PENDING.value,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
