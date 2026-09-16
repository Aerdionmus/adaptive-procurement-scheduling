from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core import clock
from app.models import Booking, ProcurementTelemetry
from app.repositories import procurement_telemetry as telemetry_repository
from app.repositories import queue as queue_repository
from app.schemas.procurement_telemetry import ProcurementTelemetryCreate


def _queue_size_at_arrival(session: Session, centre_id: int) -> int:
    return len(queue_repository.list_live_queue(session, centre_id))


def _get_or_create(
    session: Session,
    booking: Booking,
    *,
    arrival_time: datetime | None = None,
    queue_size_at_arrival: int | None = None,
) -> ProcurementTelemetry:
    existing = telemetry_repository.get_telemetry_for_booking(session, booking.id)
    if existing is not None:
        return existing
    data = ProcurementTelemetryCreate(
        lot_id=str(booking.id),
        booking_id=booking.id,
        centre_id=booking.centre_id,
        scheduled_slot=str(booking.slot_id),
        arrival_time=arrival_time or clock.utcnow(),
        queue_size_at_arrival=(
            _queue_size_at_arrival(session, booking.centre_id)
            if queue_size_at_arrival is None
            else queue_size_at_arrival
        ),
        provenance="REAL_OBSERVED",
        completion_status="IN_PROGRESS",
    )
    return telemetry_repository.create_telemetry(session, data)


def record_check_in(
    session: Session,
    booking: Booking,
    *,
    arrival_time: datetime,
    queue_size_at_arrival: int,
) -> ProcurementTelemetry:
    return _get_or_create(
        session,
        booking,
        arrival_time=arrival_time,
        queue_size_at_arrival=queue_size_at_arrival,
    )


def record_completion(
    session: Session,
    booking: Booking,
    *,
    completion_time: datetime,
) -> ProcurementTelemetry:
    telemetry = _get_or_create(session, booking)
    telemetry.completion_time = completion_time
    telemetry.completion_status = "COMPLETED"
    return telemetry


def record_no_show(session: Session, booking: Booking) -> ProcurementTelemetry:
    telemetry = _get_or_create(session, booking)
    telemetry.no_show = True
    telemetry.completion_status = "NO_SHOW"
    return telemetry


def record_cancellation(session: Session, booking: Booking) -> ProcurementTelemetry:
    # Reserved for a real cancellation workflow; none currently emits it.
    telemetry = _get_or_create(session, booking)
    telemetry.cancellation = True
    telemetry.completion_status = "CANCELLED"
    return telemetry
