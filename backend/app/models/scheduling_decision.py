from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SchedulingDecision(Base):
    __tablename__ = "scheduling_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), nullable=False, index=True)
    centre_id: Mapped[int] = mapped_column(
        ForeignKey("procurement_centres.id"), nullable=False, index=True
    )
    slot_id: Mapped[int] = mapped_column(ForeignKey("procurement_slots.id"), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scheduling_status: Mapped[str] = mapped_column(String(30), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(50), nullable=False)
    estimated_completion_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estimated_wait_minutes: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    farmers_ahead: Mapped[int] = mapped_column(Integer, nullable=False)
    prediction_status: Mapped[str | None] = mapped_column(String(30))
    prediction_provenance: Mapped[str] = mapped_column(String(50), nullable=False)
    recommended_slot_id: Mapped[int | None] = mapped_column(
        ForeignKey("procurement_slots.id")
    )
    recommended_centre_id: Mapped[int | None] = mapped_column(
        ForeignKey("procurement_centres.id")
    )
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    decision_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
