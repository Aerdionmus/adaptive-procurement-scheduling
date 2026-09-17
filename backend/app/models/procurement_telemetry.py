from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcurementTelemetry(Base):
    __tablename__ = "procurement_telemetry"
    __table_args__ = (
        Index(
            "uq_procurement_telemetry_booking_id",
            "booking_id",
            unique=True,
            postgresql_where="booking_id IS NOT NULL",
            sqlite_where="booking_id IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lot_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id"),
        nullable=True,
        index=True,
    )
    centre_id: Mapped[int] = mapped_column(ForeignKey("procurement_centres.id"), nullable=False, index=True)
    scheduled_slot: Mapped[str | None] = mapped_column(String(100))
    arrival_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queue_size_at_arrival: Mapped[int | None] = mapped_column(Integer)
    registration_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unloading_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unloading_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weighment_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weighment_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    documentation_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    documentation_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resource_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provenance: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="LEGACY",
        server_default="LEGACY",
    )
    no_show: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    cancellation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    completion_status: Mapped[str] = mapped_column(String(50), nullable=False)
